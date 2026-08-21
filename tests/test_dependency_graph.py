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


class NestedGraphClient:
    def __init__(self):
        self.paths = [
            "benchmarks/rest-path-break/pom.xml",
            "benchmarks/rest-path-break/spring-petclinic-provider-service/pom.xml",
            "benchmarks/rest-path-break/spring-petclinic-provider-service/src/main/java/benchmark/provider/OwnerResource.java",
            "benchmarks/rest-path-break/spring-petclinic-consumer-service/pom.xml",
            "benchmarks/rest-path-break/spring-petclinic-consumer-service/src/main/java/benchmark/consumer/OwnersServiceClient.java",
        ]
        self.contents = {
            "benchmarks/rest-path-break/spring-petclinic-consumer-service/src/main/java/benchmark/consumer/OwnersServiceClient.java": """
                class OwnersServiceClient {
                    Object getOwner(int ownerId) {
                        return client.get()
                            .uri("http://provider-service/owners/{ownerId}", ownerId);
                    }
                }
            """,
        }

    def list_repository_paths(self, repo_full_name: str, ref: str) -> list[str]:
        return self.paths

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        return self.contents.get(path)


class GenericGraphClient:
    def __init__(self):
        self.paths = [
            "edge-router/pom.xml",
            "edge-router/src/main/resources/application.yml",
            "edge-router/src/main/java/example/BillingClient.java",
            "billing-app/pom.xml",
            "billing-app/src/main/resources/application.properties",
            "shared-library/pom.xml",
        ]
        self.contents = {
            "edge-router/src/main/resources/application.yml": """
                spring:
                  application:
                    name: edge-gateway
            """,
            "billing-app/src/main/resources/application.properties": (
                "spring.application.name=billing-service\n"
            ),
            "edge-router/src/main/java/example/BillingClient.java": """
                class BillingClient {
                    Object invoice(String invoiceId) {
                        return client.get()
                            .uri("http://billing-service/invoices/{invoiceId}", invoiceId);
                    }
                }
            """,
        }

    def list_repository_paths(self, repo_full_name: str, ref: str) -> list[str]:
        return self.paths

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        return self.contents.get(path)


class EnvDefaultGraphClient:
    paths = [
        "orders-app/pom.xml",
        "orders-app/src/main/resources/application.properties",
    ]
    contents = {
        "orders-app/src/main/resources/application.properties": (
            "spring.application.name=${SPRING_APPLICATION_NAME:orders-service}\n"
        )
    }

    def list_repository_paths(self, repo_full_name: str, ref: str) -> list[str]:
        return self.paths

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        return self.contents.get(path)


class AggregatorGraphClient:
    paths = [
        "platform/pom.xml",
        "platform/orders-service/pom.xml",
        "platform/orders-service/src/main/java/example/OrdersApplication.java",
        "platform/payments-service/pom.xml",
        "platform/payments-service/src/main/java/example/PaymentsApplication.java",
    ]

    def list_repository_paths(self, repo_full_name: str, ref: str) -> list[str]:
        return self.paths

    def get_file_text(self, repo_full_name: str, path: str, ref: str) -> str | None:
        return None


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


def test_discovers_nested_service_modules_and_call_evidence():
    graph = ServiceDependencyGraphBuilder(client=NestedGraphClient()).build(
        "acme/changeguard",
        "benchmark",
    )

    modules = {node.name: node.module_path for node in graph.nodes}
    assert modules == {
        "consumer-service": (
            "benchmarks/rest-path-break/spring-petclinic-consumer-service"
        ),
        "provider-service": (
            "benchmarks/rest-path-break/spring-petclinic-provider-service"
        ),
    }
    assert graph.service_for_path(
        "benchmarks/rest-path-break/spring-petclinic-provider-service/"
        "src/main/java/benchmark/provider/OwnerResource.java"
    ) == "provider-service"
    assert len(graph.consumer_calls) == 1
    call = graph.consumer_calls[0]
    assert call.consumer_service == "consumer-service"
    assert call.target_service == "provider-service"
    assert call.http_method == "GET"
    assert call.path == "/owners/{ownerId}"


def test_discovers_generic_names_from_spring_application_configuration():
    graph = ServiceDependencyGraphBuilder(client=GenericGraphClient()).build(
        "acme/commerce",
        "main",
    )

    assert {node.name for node in graph.nodes} == {
        "billing-service",
        "edge-gateway",
        "shared-library",
    }
    assert {
        (edge.source, edge.target, edge.kind)
        for edge in graph.edges
    } == {
        ("edge-gateway", "billing-service", DependencyKind.SERVICE_URL),
    }
    assert len(graph.consumer_calls) == 1
    assert graph.consumer_calls[0].consumer_service == "edge-gateway"
    assert graph.consumer_calls[0].target_service == "billing-service"


def test_uses_environment_default_as_deterministic_application_name():
    graph = ServiceDependencyGraphBuilder(client=EnvDefaultGraphClient()).build(
        "acme/orders",
        "main",
    )

    assert [(node.name, node.module_path) for node in graph.nodes] == [
        ("orders-service", "orders-app")
    ]


def test_falls_back_to_plain_module_basename_without_application_name():
    client = AggregatorGraphClient()
    client.paths = [
        "notifications-service/pom.xml",
        "notifications-service/src/main/java/example/NotificationsApplication.java",
    ]

    graph = ServiceDependencyGraphBuilder(client=client).build("acme/notify", "main")

    assert [(node.name, node.module_path) for node in graph.nodes] == [
        ("notifications-service", "notifications-service")
    ]


def test_excludes_pure_aggregator_but_keeps_child_modules():
    graph = ServiceDependencyGraphBuilder(client=AggregatorGraphClient()).build(
        "acme/platform",
        "main",
    )

    assert {node.name: node.module_path for node in graph.nodes} == {
        "orders-service": "platform/orders-service",
        "payments-service": "platform/payments-service",
    }
