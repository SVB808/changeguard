from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GitHubAPIError(RuntimeError):
    pass


REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class GitHubChangedFile:
    filename: str
    status: str
    patch: str | None = None
    previous_filename: str | None = None


@dataclass(frozen=True)
class GitHubPullRequest:
    repo_full_name: str
    number: int
    base_sha: str
    head_sha: str
    files: list[GitHubChangedFile]


class GitHubClient:
    """Small read-only GitHub REST client used for public PR analysis.

    Authentication is optional for public repositories. When GITHUB_TOKEN is set,
    the token is used to increase rate limits and enables future private-repo support.
    """

    def __init__(self, token: str | None = None, timeout_seconds: int = 15) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://api.github.com"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "changeguard/0.1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get_json(self, path: str) -> Any:
        request = Request(
            f"{self.base_url}{path}",
            headers=self._headers(),
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                message = payload.get("message", str(exc))
            except (json.JSONDecodeError, UnicodeDecodeError):
                message = str(exc)
            raise GitHubAPIError(
                f"GitHub API returned HTTP {exc.code}: {message}"
            ) from exc
        except URLError as exc:
            raise GitHubAPIError(f"Could not reach GitHub API: {exc.reason}") from exc

    @staticmethod
    def _validate_repo(repo_full_name: str) -> None:
        if not REPO_PATTERN.fullmatch(repo_full_name):
            raise GitHubAPIError(
                "Repository must use owner/name format, e.g. spring-projects/spring-petclinic"
            )

    def get_pull_request(self, repo_full_name: str, number: int) -> GitHubPullRequest:
        self._validate_repo(repo_full_name)
        if number <= 0:
            raise GitHubAPIError("Pull request number must be positive")

        metadata = self._get_json(f"/repos/{repo_full_name}/pulls/{number}")

        files: list[GitHubChangedFile] = []
        page = 1
        while True:
            payload = self._get_json(
                f"/repos/{repo_full_name}/pulls/{number}/files?per_page=100&page={page}"
            )
            if not isinstance(payload, list):
                raise GitHubAPIError("Unexpected GitHub response while listing PR files")

            for item in payload:
                files.append(
                    GitHubChangedFile(
                        filename=item["filename"],
                        status=item.get("status", "changed"),
                        patch=item.get("patch"),
                        previous_filename=item.get("previous_filename"),
                    )
                )

            if len(payload) < 100:
                break
            page += 1

        return GitHubPullRequest(
            repo_full_name=repo_full_name,
            number=number,
            base_sha=metadata["base"]["sha"],
            head_sha=metadata["head"]["sha"],
            files=files,
        )
