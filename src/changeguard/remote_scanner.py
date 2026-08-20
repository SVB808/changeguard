from __future__ import annotations

from changeguard.classifier import classify
from changeguard.git_client import RawGitChange
from changeguard.github_client import GitHubAPIError, GitHubChangedFile, GitHubClient
from changeguard.java_analyzer import JavaSpringAnalyzer
from changeguard.models import ChangeManifest, FileChange


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
    semantic_analyzer: JavaSpringAnalyzer | None = None,
    semantic_analysis: bool = False,
) -> ChangeManifest:
    client = client or GitHubClient()
    pull_request = client.get_pull_request(repo_full_name, pr_number)

    analyzer = semantic_analyzer
    if semantic_analysis and analyzer is None:
        analyzer = JavaSpringAnalyzer()

    files: list[FileChange] = []
    for remote_file in pull_request.files:
        change = RawGitChange(
            status_token=GITHUB_STATUS_TO_GIT.get(remote_file.status, "M"),
            path=remote_file.filename,
            old_path=remote_file.previous_filename,
        )
        classified = classify(change, remote_file.patch or "")

        if semantic_analysis and classified.language == "java":
            assert analyzer is not None
            before_source, after_source = _load_java_versions(
                client=client,
                repo_full_name=pull_request.repo_full_name,
                remote_file=remote_file,
                base_sha=pull_request.base_sha,
                head_sha=pull_request.head_sha,
            )
            classified.semantic_changes.extend(
                analyzer.analyze_sources(before_source, after_source)
            )

        files.append(classified)

    return ChangeManifest(
        repo=pull_request.repo_full_name,
        base=pull_request.base_sha,
        head=pull_request.head_sha,
        files=files,
    )


def _load_java_versions(
    client: GitHubClient,
    repo_full_name: str,
    remote_file: GitHubChangedFile,
    base_sha: str,
    head_sha: str,
) -> tuple[str, str]:
    before_path = remote_file.previous_filename or remote_file.filename

    if remote_file.status == "added":
        before_source = ""
    else:
        before_source = client.get_file_text(repo_full_name, before_path, base_sha)
        if before_source is None:
            raise GitHubAPIError(
                f"Could not load base source for {before_path} at {base_sha[:12]}"
            )

    if remote_file.status == "removed":
        after_source = ""
    else:
        after_source = client.get_file_text(
            repo_full_name,
            remote_file.filename,
            head_sha,
        )
        if after_source is None:
            raise GitHubAPIError(
                f"Could not load head source for {remote_file.filename} "
                f"at {head_sha[:12]}"
            )

    return before_source, after_source
