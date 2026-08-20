from changeguard.github_client import GitHubChangedFile, GitHubPullRequest
from changeguard.models import (
    ChangeStatus,
    EndpointChangeKind,
    EndpointSemanticChange,
    EngineeringSurface,
    SpringEndpoint,
)
from changeguard.remote_scanner import scan_pull_request


class FakeGitHubClient:
    def __init__(
        self,
        pull_request: GitHubPullRequest,
        sources: dict[tuple[str, str], str] | None = None,
    ):
        self.pull_request = pull_request
        self.sources = sources or {}

    def get_pull_request(self, repo_full_name: str, number: int) -> GitHubPullRequest:
        assert repo_full_name == self.pull_request.repo_full_name
        assert number == self.pull_request.number
        return self.pull_request

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        assert repo_full_name == self.pull_request.repo_full_name
        return self.sources.get((path, ref))


class FakeSemanticAnalyzer:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def analyze_sources(
        self,
        before_source: str,
        after_source: str,
    ) -> list[EndpointSemanticChange]:
        self.calls.append((before_source, after_source))
        return [
            EndpointSemanticChange(
                kind=EndpointChangeKind.ENDPOINT_ADDED,
                after=SpringEndpoint(
                    controller="VetResource",
                    method_name="health",
                    http_method="GET",
                    path="/vets/health",
                    return_type="String",
                    parameter_types=[],
                ),
            )
        ]


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


def test_semantic_analysis_uses_full_before_and_after_java_source():
    base_sha = "1" * 40
    head_sha = "2" * 40
    path = "src/main/java/example/VetResource.java"
    before_source = """
        @RestController
        @RequestMapping("/vets")
        class VetResource {}
    """
    after_source = """
        @RestController
        @RequestMapping("/vets")
        class VetResource {
            @GetMapping("/health")
            public String health() { return "UP"; }
        }
    """

    pr = GitHubPullRequest(
        repo_full_name="acme/orders",
        number=9,
        base_sha=base_sha,
        head_sha=head_sha,
        files=[
            GitHubChangedFile(
                filename=path,
                status="modified",
                patch='+    @GetMapping("/health")',
            )
        ],
    )
    client = FakeGitHubClient(
        pr,
        sources={
            (path, base_sha): before_source,
            (path, head_sha): after_source,
        },
    )
    analyzer = FakeSemanticAnalyzer()

    result = scan_pull_request(
        "acme/orders",
        9,
        client=client,
        semantic_analyzer=analyzer,
        semantic_analysis=True,
    )

    assert analyzer.calls == [(before_source, after_source)]
    assert len(result.files[0].semantic_changes) == 1
    semantic_change = result.files[0].semantic_changes[0]
    assert semantic_change.kind == EndpointChangeKind.ENDPOINT_ADDED
    assert semantic_change.after is not None
    assert semantic_change.after.path == "/vets/health"
