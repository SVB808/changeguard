from __future__ import annotations

from pathlib import Path

from changeguard.classifier import classify
from changeguard.git_client import list_changes, patch_for_file, validate_repo
from changeguard.models import ChangeManifest


def scan(repo: Path, base: str, head: str) -> ChangeManifest:
    repo = repo.resolve()
    validate_repo(repo)

    files = []
    for change in list_changes(repo, base, head):
        patch = patch_for_file(repo, base, head, change.path)
        files.append(classify(change, patch))

    return ChangeManifest(
        repo=str(repo),
        base=base,
        head=head,
        files=files,
    )
