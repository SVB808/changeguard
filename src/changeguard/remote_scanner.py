from __future__ import annotations

from changeguard.classifier import classify
from changeguard.git_client import RawGitChange
from changeguard.github_client import GitHubClient
from changeguard.models import ChangeManifest


GITHUB_STATUS_TO_GIT = {
    "added": "A",
    "modified": "M",
    "removed": "D",
    "renamed": "R100",
    "copied": "C100",
    "changed": "M",
    "unchanged": "M",
}


def scan_pull_request(
    repo_full_name: str,
    pr_number: int,
    client: GitHubClient | None = None,
) -> ChangeManifest:
    client = client or GitHubClient()
    pull_request = client.get_pull_request(repo_full_name, pr_number)

    files = []
    for remote_file in pull_request.files:
        change = RawGitChange(
            status_token=GITHUB_STATUS_TO_GIT.get(remote_file.status, "M"),
            path=remote_file.filename,
            old_path=remote_file.previous_filename,
        )
        files.append(classify(change, remote_file.patch or ""))

    return ChangeManifest(
        repo=pull_request.repo_full_name,
        base=pull_request.base_sha,
        head=pull_request.head_sha,
        files=files,
    )
