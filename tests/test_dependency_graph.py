from changeguard.dependency_graph import ServiceDependencyGraphBuilder
from changeguard.models import DependencyKind


class FakeGraphClient:
    def __init__(self):
        self.paths = [
            "spring-petclinic-api-gateway/pom.xml",
            "spring-petclinic-api-gateway/src/main/resources/application.yml",
            "spring-petclinic-api-gateway/src/main/java/example/CustomersServiceClient.java",
            "spring-petclinic-customers-service/pom.xml",
            "spring-petclinic-vets-service/pom.xml",
            "spring-petclinic-visits-service/pom.xml",
            "spring-petclinic-config-server/pom.xml",
        ]
        self.contents = {
            "spring-petclinic-api-gateway/src/main/resources/application.yml": """
                spring:
                  cloud:
                    gateway:
                      routes:
                        - id: vets-service
                          uri: lb://vets-service
                        - id: visits-service
                          uri: lb://visits-service
                  config:
                    import: configserver:http://config-server:8888
            """,
            "spring-petclinic-api-gateway/src/main/java/example/CustomersServiceClient.java": """
                class CustomersServiceClient {
                    Object getOwner(int ownerId) {
                        return webClientBuilder.build().get()
                            .uri("http://customers-service/owners/{ownerId}", ownerId)
                            .retrieve();
                    }
                }
            """,
        }

    def list_repository_paths(self, repo_full_name: str, ref: str) -> list[str]:
        assert repo_full_name == "acme/petclinic"
        assert ref == "abc123"
        return self.paths

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        assert repo_full_name == "acme/petclinic"
        assert ref == "abc123"
        return self.contents.get(path)


def test_builds_graph_from_gateway_routes_and_service_urls():
    graph = ServiceDependencyGraphBuilder(client=FakeGraphClient()).build(
        "acme/petclinic",
        "abc123",
    )

    assert {node.name for node in graph.nodes} == {
        "api-gateway",
        "config-server",
        "customers-service",
        "vets-service",
        "visits-service",
    }
    assert {
        (edge.source, edge.target, edge.kind)
        for edge in graph.edges
    } == {
        ("api-gateway", "vets-service", DependencyKind.GATEWAY_ROUTE),
        ("api-gateway", "visits-service", DependencyKind.GATEWAY_ROUTE),
        ("api-gateway", "config-server", DependencyKind.CONFIG_IMPORT),
        ("api-gateway", "customers-service", DependencyKind.SERVICE_URL),
    }


def test_extracts_literal_consumer_http_method_and_route():
    graph = ServiceDependencyGraphBuilder(client=FakeGraphClient()).build(
        "acme/petclinic",
        "abc123",
    )

    assert len(graph.consumer_calls) == 1
    call = graph.consumer_calls[0]
    assert call.consumer_service == "api-gateway"
    assert call.target_service == "customers-service"
    assert call.http_method == "GET"
    assert call.path == "/owners/{ownerId}"
    assert call.evidence_path.endswith("CustomersServiceClient.java")


def test_resolves_service_ownership_and_direct_dependents():
    graph = ServiceDependencyGraphBuilder(client=FakeGraphClient()).build(
        "acme/petclinic",
        "abc123",
    )

    assert graph.service_for_path(
        "spring-petclinic-vets-service/src/main/java/example/VetResource.java"
    ) == "vets-service"
    assert graph.direct_dependents("vets-service") == ["api-gateway"]
    assert graph.direct_dependents("api-gateway") == []
