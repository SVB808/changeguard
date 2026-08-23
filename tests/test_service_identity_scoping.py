from changeguard.dependency_graph import ServiceDependencyGraphBuilder
from changeguard.impact_analysis import generate_impact_candidates, refine_impact_candidates
from changeguard.models import (
    ChangeStatus,
    EndpointChangeKind,
    EndpointSemanticChange,
    FileChange,
    ImpactMatchLevel,
    SpringEndpoint,
)
from changeguard.verification import build_verification_plans


class DuplicateServiceNameGraphClient:
    paths = [
        "workspace-a/provider-service/pom.xml",
        "workspace-a/provider-service/src/main/java/example/Provider.java",
        "workspace-a/consumer-service/pom.xml",
        "workspace-a/consumer-service/src/main/java/example/OwnersClient.java",
        "workspace-b/provider-service/pom.xml",
        "workspace-b/provider-service/src/main/java/example/OrderResource.java",
        "workspace-b/feign-consumer-service/pom.xml",
        "workspace-b/feign-consumer-service/src/main/java/example/OrdersFeign.java",
        "workspace-b/resttemplate-consumer-service/pom.xml",
        "workspace-b/resttemplate-consumer-service/src/main/java/example/OrdersRestTemplateClient.java",
    ]
    contents = {
        "workspace-a/consumer-service/src/main/java/example/OwnersClient.java": """
            class OwnersClient {
                Object owner() {
                    return client.get()
                        .uri("http://provider-service/owners/{ownerId}", 42);
                }
            }
        """,
        "workspace-b/feign-consumer-service/src/main/java/example/OrdersFeign.java": """
            @FeignClient(name = "provider-service")
            interface OrdersFeign {
                @GetMapping("/orders/{orderId}")
                Object order(int orderId);
            }
        """,
        "workspace-b/resttemplate-consumer-service/src/main/java/example/OrdersRestTemplateClient.java": """
            class OrdersRestTemplateClient {
                Object order(RestTemplate restTemplate) {
                    return restTemplate.getForEntity(
                        "http://provider-service/orders/{orderId}",
                        Object.class,
                        42
                    );
                }
            }
        """,
    }

    def list_repository_paths(self, repo_full_name: str, ref: str) -> list[str]:
        return self.paths

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        return self.contents.get(path)


def _path_change() -> EndpointSemanticChange:
    return EndpointSemanticChange(
        kind=EndpointChangeKind.ENDPOINT_PATH_CHANGED,
        before=SpringEndpoint(
            controller="OrderResource",
            methodName="findOrder",
            httpMethod="GET",
            path="/orders/{orderId}",
            returnType="Object",
            parameterTypes=["int"],
        ),
        after=SpringEndpoint(
            controller="OrderResource",
            methodName="findOrder",
            httpMethod="GET",
            path="/purchases/{orderId}",
            returnType="Object",
            parameterTypes=["int"],
        ),
    )


def test_duplicate_logical_service_names_resolve_to_nearest_workspace_module():
    graph = ServiceDependencyGraphBuilder(client=DuplicateServiceNameGraphClient()).build(
        "acme/monorepo",
        "head",
    )

    provider_modules = sorted(
        node.module_path for node in graph.nodes if node.name == "provider-service"
    )
    assert provider_modules == [
        "workspace-a/provider-service",
        "workspace-b/provider-service",
    ]
    assert graph.module_for_service("provider-service") is None

    old_edge = next(
        edge
        for edge in graph.edges
        if edge.source == "consumer-service"
    )
    assert old_edge.target_module == "workspace-a/provider-service"

    new_edges = [
        edge
        for edge in graph.edges
        if edge.source in {"feign-consumer-service", "resttemplate-consumer-service"}
    ]
    assert {edge.target_module for edge in new_edges} == {
        "workspace-b/provider-service"
    }


def test_impact_join_does_not_cross_contaminate_duplicate_service_names():
    graph = ServiceDependencyGraphBuilder(client=DuplicateServiceNameGraphClient()).build(
        "acme/monorepo",
        "head",
    )
    changed = FileChange(
        status=ChangeStatus.MODIFIED,
        path="workspace-b/provider-service/src/main/java/example/OrderResource.java",
        language="java",
        service="provider-service",
        semantic_changes=[_path_change()],
    )

    service_candidates = generate_impact_candidates([changed], graph)
    active, suppressed = refine_impact_candidates(service_candidates, graph)

    assert {candidate.consumer_service for candidate in active} == {
        "feign-consumer-service",
        "resttemplate-consumer-service",
    }
    assert all(candidate.match_level == ImpactMatchLevel.ENDPOINT for candidate in active)
    assert all(
        candidate.provider_module == "workspace-b/provider-service"
        for candidate in active
    )
    assert suppressed == []
    assert "consumer-service" not in {candidate.consumer_service for candidate in active}

    plans = build_verification_plans(active, graph)
    assert {plan.consumer_module for plan in plans} == {
        "workspace-b/feign-consumer-service",
        "workspace-b/resttemplate-consumer-service",
    }
