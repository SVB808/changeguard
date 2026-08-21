from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class GitHubAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_rate_limited(self) -> bool:
        return self.status_code == 403 and "rate limit" in str(self).lower()


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
                f"GitHub API returned HTTP {exc.code}: {message}",
                status_code=exc.code,
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

    def list_repository_paths(self, repo_full_name: str, ref: str) -> list[str]:
        """List blob paths for an exact Git ref using GitHub's recursive tree API."""
        self._validate_repo(repo_full_name)
        encoded_ref = quote(ref, safe="")
        payload = self._get_json(
            f"/repos/{repo_full_name}/git/trees/{encoded_ref}?recursive=1"
        )

        if not isinstance(payload, dict) or not isinstance(payload.get("tree"), list):
            raise GitHubAPIError("Unexpected GitHub response while listing repository tree")
        if payload.get("truncated"):
            raise GitHubAPIError(
                "GitHub returned a truncated repository tree; dependency analysis cannot continue safely"
            )

        paths: list[str] = []
        for item in payload["tree"]:
            if item.get("type") == "blob" and isinstance(item.get("path"), str):
                paths.append(item["path"])
        return paths

    def get_file_text(
        self,
        repo_full_name: str,
        path: str,
        ref: str,
    ) -> str | None:
        """Fetch one text file at an exact Git ref.

        Returns None when the path does not exist at that ref. This is expected for
        the base side of added files and the head side of deleted files.
        """
        self._validate_repo(repo_full_name)
        encoded_path = quote(path, safe="/")
        encoded_ref = quote(ref, safe="")

        try:
            payload = self._get_json(
                f"/repos/{repo_full_name}/contents/{encoded_path}?ref={encoded_ref}"
            )
        except GitHubAPIError as exc:
            if exc.status_code == 404:
                return None
            raise

        if not isinstance(payload, dict) or payload.get("type") != "file":
            raise GitHubAPIError(
                f"Expected a file while fetching {path} at {ref[:12]}"
            )

        encoding = payload.get("encoding")
        content = payload.get("content")
        if encoding != "base64" or not isinstance(content, str):
            raise GitHubAPIError(
                f"Unsupported GitHub content encoding for {path} at {ref[:12]}"
            )

        try:
            return base64.b64decode(content).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubAPIError(
                f"Could not decode {path} at {ref[:12]} as UTF-8 text"
            ) from exc
