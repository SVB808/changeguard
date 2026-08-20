from changeguard.github_client import GitHubChangedFile, GitHubPullRequest
from changeguard.models import ChangeStatus, EngineeringSurface
from changeguard.remote_scanner import scan_pull_request


class FakeGitHubClient:
    def __init__(self, pull_request: GitHubPullRequest):
        self.pull_request = pull_request

    def get_pull_request(self, repo_full_name: str, number: int) -> GitHubPullRequest:
        assert repo_full_name == self.pull_request.repo_full_name
        assert number == self.pull_request.number
        return self.pull_request


def test_remote_pr_classifies_controller_and_migration():
    pr = GitHubPullRequest(
        repo_full_name="acme/orders",
        number=42,
        base_sha="a" * 40,
        head_sha="b" * 40,
        files=[
            GitHubChangedFile(
                filename="src/main/java/com/acme/orders/OrderController.java",
                status="modified",
                patch='+    @GetMapping("/orders/{id}")',
            ),
            GitHubChangedFile(
                filename="src/main/resources/db/migration/V12__add_status.sql",
                status="added",
                patch="+ALTER TABLE orders ADD COLUMN status varchar(32);",
            ),
        ],
    )

    result = scan_pull_request("acme/orders", 42, client=FakeGitHubClient(pr))

    assert result.repo == "acme/orders"
    assert result.base == "a" * 40
    assert result.head == "b" * 40
    assert result.changed_file_count == 2
    assert EngineeringSurface.API_CONTRACT in result.files[0].surfaces
    assert EngineeringSurface.DATABASE in result.files[1].surfaces


def test_remote_rename_preserves_old_path():
    pr = GitHubPullRequest(
        repo_full_name="acme/orders",
        number=7,
        base_sha="c" * 40,
        head_sha="d" * 40,
        files=[
            GitHubChangedFile(
                filename="src/main/java/com/acme/orders/NewName.java",
                previous_filename="src/main/java/com/acme/orders/OldName.java",
                status="renamed",
                patch=None,
            )
        ],
    )

    result = scan_pull_request("acme/orders", 7, client=FakeGitHubClient(pr))

    assert result.files[0].status == ChangeStatus.RENAMED
    assert result.files[0].old_path == "src/main/java/com/acme/orders/OldName.java"


def test_missing_remote_patch_still_uses_path_evidence():
    pr = GitHubPullRequest(
        repo_full_name="acme/orders",
        number=8,
        base_sha="e" * 40,
        head_sha="f" * 40,
        files=[
            GitHubChangedFile(
                filename="src/main/resources/db/migration/V13__index.sql",
                status="modified",
                patch=None,
            )
        ],
    )

    result = scan_pull_request("acme/orders", 8, client=FakeGitHubClient(pr))

    assert EngineeringSurface.DATABASE in result.files[0].surfaces
