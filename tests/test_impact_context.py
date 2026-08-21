from changeguard.github_client import GitHubChangedFile, GitHubPullRequest
from changeguard.java_analyzer import JavaSemanticAnalysis
from changeguard.models import (
    ConsumerHttpCall,
    DependencyEdge,
    DependencyKind,
    EndpointChangeKind,
    EndpointSemanticChange,
    ServiceDependencyGraph,
    ServiceNode,
    SpringEndpoint,
)
from changeguard.remote_scanner import scan_pull_request


class FakeGitHubClient:
    def __init__(self, pull_request: GitHubPullRequest, source: str):
        self.pull_request = pull_request
        self.source = source

    def get_pull_request(self, repo_full_name: str, number: int) -> GitHubPullRequest:
        assert repo_full_name == self.pull_request.repo_full_name
        assert number == self.pull_request.number
        return self.pull_request

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        assert repo_full_name == self.pull_request.repo_full_name
        return self.source


class FakeSemanticAnalyzer:
    def analyze_sources(self, before_source: str, after_source: str) -> JavaSemanticAnalysis:
        endpoint = SpringEndpoint(
            controller="OwnerResource",
            method_name="findOwner",
            http_method="GET",
            path="/owners/{ownerId}",
            return_type="OwnerDetails",
            parameter_types=["int"],
        )
        return JavaSemanticAnalysis(
            endpoint_changes=[
                EndpointSemanticChange(
                    kind=EndpointChangeKind.ENDPOINT_REMOVED,
                    before=endpoint,
                )
            ],
            security_changes=[],
        )


class FakeGraphBuilder:
    def __init__(self, graph: ServiceDependencyGraph):
        self.graph = graph

    def build(self, repo_full_name: str, ref: str) -> ServiceDependencyGraph:
        return self.graph


def _pull_request() -> GitHubPullRequest:
    path = (
        "spring-petclinic-customers-service/src/main/java/example/"
        "OwnerResource.java"
    )
    return GitHubPullRequest(
        repo_full_name="acme/petclinic",
        number=13,
        base_sha="a" * 40,
        head_sha="b" * 40,
        files=[
            GitHubChangedFile(
                filename=path,
                status="modified",
                patch='-    @GetMapping("/owners/{ownerId}")',
            )
        ],
    )


def _graph(consumer_calls: list[ConsumerHttpCall] | None = None) -> ServiceDependencyGraph:
    return ServiceDependencyGraph(
        nodes=[
            ServiceNode(
                name="api-gateway",
                module_path="spring-petclinic-api-gateway",
            ),
            ServiceNode(
                name="customers-service",
                module_path="spring-petclinic-customers-service",
            ),
        ],
        edges=[
            DependencyEdge(
                source="api-gateway",
                target="customers-service",
                kind=DependencyKind.SERVICE_URL,
                evidence_path=(
                    "spring-petclinic-api-gateway/src/main/java/example/"
                    "CustomersServiceClient.java"
                ),
                evidence="http://customers-service",
            )
        ],
        consumer_calls=consumer_calls or [],
    )


def test_impact_analysis_implies_semantic_and_dependency_analysis():
    pr = _pull_request()
    graph = _graph()

    result = scan_pull_request(
        "acme/petclinic",
        13,
        client=FakeGitHubClient(pr, "class OwnerResource {}"),
        semantic_analyzer=FakeSemanticAnalyzer(),
        dependency_graph_builder=FakeGraphBuilder(graph),
        impact_analysis=True,
    )

    assert result.impact_analysis_enabled is True
    assert result.dependency_graph == graph
    assert result.files[0].service == "customers-service"
    assert result.files[0].direct_dependents == ["api-gateway"]
    assert len(result.impact_candidates) == 1
    candidate = result.impact_candidates[0]
    assert candidate.provider_service == "customers-service"
    assert candidate.consumer_service == "api-gateway"
    assert candidate.trigger_kind == EndpointChangeKind.ENDPOINT_REMOVED
    assert result.suppressed_impact_candidates == []


def test_impact_analysis_retains_non_matching_call_as_suppressed_candidate():
    pr = _pull_request()
    call = ConsumerHttpCall(
        consumer_service="api-gateway",
        target_service="customers-service",
        http_method="POST",
        path="/owners",
        evidence_path=(
            "spring-petclinic-api-gateway/src/main/java/example/"
            "CustomersServiceClient.java"
        ),
        evidence='.post().uri("http://customers-service/owners")',
    )
    graph = _graph([call])

    result = scan_pull_request(
        "acme/petclinic",
        13,
        client=FakeGitHubClient(pr, "class OwnerResource {}"),
        semantic_analyzer=FakeSemanticAnalyzer(),
        dependency_graph_builder=FakeGraphBuilder(graph),
        impact_analysis=True,
    )

    assert result.impact_candidates == []
    assert len(result.suppressed_impact_candidates) == 1
    suppressed = result.suppressed_impact_candidates[0]
    assert suppressed.consumer_call_evidence == [call]
    assert suppressed.suppression_reason is not None
