from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class RawGitChange:
    status_token: str
    path: str
    old_path: str | None = None


def _run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "unknown git error"
        raise GitError(stderr)
    return completed.stdout


def validate_repo(repo: Path) -> None:
    value = _run_git(repo, "rev-parse", "--is-inside-work-tree").strip()
    if value != "true":
        raise GitError(f"{repo} is not a Git work tree")


def list_changes(repo: Path, base: str, head: str) -> list[RawGitChange]:
    # Two-dot diff is deliberate for V0: compare exactly the two tree states.
    output = _run_git(
        repo,
        "diff",
        "--name-status",
        "--find-renames",
        base,
        head,
    )

    changes: list[RawGitChange] = []
    for line in output.splitlines():
        if not line.strip():
            continue

        parts = line.split("\t")
        token = parts[0]

        if token.startswith(("R", "C")) and len(parts) >= 3:
            changes.append(
                RawGitChange(
                    status_token=token,
                    old_path=parts[1],
                    path=parts[2],
                )
            )
        elif len(parts) >= 2:
            changes.append(
                RawGitChange(
                    status_token=token,
                    path=parts[1],
                )
            )

    return changes


def patch_for_file(repo: Path, base: str, head: str, path: str) -> str:
    return _run_git(
        repo,
        "diff",
        "--unified=0",
        base,
        head,
        "--",
        path,
    )
