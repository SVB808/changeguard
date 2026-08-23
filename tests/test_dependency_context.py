from changeguard.github_client import GitHubChangedFile, GitHubPullRequest
from changeguard.models import (
    DependencyEdge,
    DependencyKind,
    ServiceDependencyGraph,
    ServiceNode,
)
from changeguard.remote_scanner import scan_pull_request


class FakeGitHubClient:
    def __init__(self, pull_request: GitHubPullRequest):
        self.pull_request = pull_request

    def get_pull_request(self, repo_full_name: str, number: int) -> GitHubPullRequest:
        assert repo_full_name == self.pull_request.repo_full_name
        assert number == self.pull_request.number
        return self.pull_request


class FakeGraphBuilder:
    def __init__(self, graph: ServiceDependencyGraph):
        self.graph = graph
        self.calls: list[tuple[str, str]] = []

    def build(self, repo_full_name: str, ref: str) -> ServiceDependencyGraph:
        self.calls.append((repo_full_name, ref))
        return self.graph


def test_pr_dependency_analysis_attaches_service_and_direct_dependents():
    head_sha = "b" * 40
    path = "spring-petclinic-vets-service/src/main/java/example/VetResource.java"
    pr = GitHubPullRequest(
        repo_full_name="acme/petclinic",
        number=12,
        base_sha="a" * 40,
        head_sha=head_sha,
        files=[
            GitHubChangedFile(
                filename=path,
                status="modified",
                patch='+    @GetMapping("/health")',
            )
        ],
    )
    graph = ServiceDependencyGraph(
        nodes=[
            ServiceNode(name="api-gateway", module_path="spring-petclinic-api-gateway"),
            ServiceNode(name="vets-service", module_path="spring-petclinic-vets-service"),
        ],
        edges=[
            DependencyEdge(
                source="api-gateway",
                target="vets-service",
                kind=DependencyKind.GATEWAY_ROUTE,
                evidence_path="spring-petclinic-api-gateway/src/main/resources/application.yml",
                evidence="lb://vets-service",
            )
        ],
    )
    builder = FakeGraphBuilder(graph)

    result = scan_pull_request(
        "acme/petclinic",
        12,
        client=FakeGitHubClient(pr),
        dependency_graph_builder=builder,
        dependency_analysis=True,
    )

    assert builder.calls == [("acme/petclinic", head_sha)]
    assert result.dependency_graph == graph
    assert result.files[0].service == "vets-service"
    assert result.files[0].direct_dependents == ["api-gateway"]
