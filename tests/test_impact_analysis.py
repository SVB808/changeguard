from changeguard.impact_analysis import generate_impact_candidates
from changeguard.models import (
    ChangeStatus,
    DependencyEdge,
    DependencyKind,
    EndpointChangeKind,
    EndpointSemanticChange,
    FileChange,
    ImpactKind,
    ImpactMatchLevel,
    ServiceDependencyGraph,
    ServiceNode,
    SpringEndpoint,
)


def _endpoint(path: str, method: str = "GET") -> SpringEndpoint:
    return SpringEndpoint(
        controller="OwnerResource",
        method_name="findOwner",
        http_method=method,
        path=path,
        return_type="OwnerDetails",
        parameter_types=["int"],
    )


def _graph() -> ServiceDependencyGraph:
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
                kind=DependencyKind.GATEWAY_ROUTE,
                evidence_path="spring-petclinic-api-gateway/src/main/resources/application.yml",
                evidence="lb://customers-service",
            ),
            DependencyEdge(
                source="api-gateway",
                target="customers-service",
                kind=DependencyKind.SERVICE_URL,
                evidence_path=(
                    "spring-petclinic-api-gateway/src/main/java/example/"
                    "CustomersServiceClient.java"
                ),
                evidence="http://customers-service",
            ),
        ],
    )


def test_endpoint_addition_does_not_create_impact_candidate():
    file = FileChange(
        status=ChangeStatus.MODIFIED,
        path=(
            "spring-petclinic-customers-service/src/main/java/example/"
            "OwnerResource.java"
        ),
        service="customers-service",
        semantic_changes=[
            EndpointSemanticChange(
                kind=EndpointChangeKind.ENDPOINT_ADDED,
                after=_endpoint("/owners/{ownerId}"),
            )
        ],
    )

    candidates = generate_impact_candidates([file], _graph())

    assert candidates == []


def test_removed_endpoint_creates_service_level_consumer_candidate():
    file = FileChange(
        status=ChangeStatus.MODIFIED,
        path=(
            "spring-petclinic-customers-service/src/main/java/example/"
            "OwnerResource.java"
        ),
        service="customers-service",
        semantic_changes=[
            EndpointSemanticChange(
                kind=EndpointChangeKind.ENDPOINT_REMOVED,
                before=_endpoint("/owners/{ownerId}"),
            )
        ],
    )

    candidates = generate_impact_candidates([file], _graph())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.kind == ImpactKind.POTENTIAL_CONSUMER_IMPACT
    assert candidate.provider_service == "customers-service"
    assert candidate.consumer_service == "api-gateway"
    assert candidate.trigger_kind == EndpointChangeKind.ENDPOINT_REMOVED
    assert candidate.match_level == ImpactMatchLevel.SERVICE
    assert candidate.before is not None
    assert candidate.before.path == "/owners/{ownerId}"
    assert len(candidate.dependency_evidence) == 2


def test_path_change_creates_candidate_but_unrelated_service_does_not():
    file = FileChange(
        status=ChangeStatus.MODIFIED,
        path=(
            "spring-petclinic-customers-service/src/main/java/example/"
            "OwnerResource.java"
        ),
        semantic_changes=[
            EndpointSemanticChange(
                kind=EndpointChangeKind.ENDPOINT_PATH_CHANGED,
                before=_endpoint("/owners/{ownerId}"),
                after=_endpoint("/customers/{ownerId}"),
            )
        ],
    )

    candidates = generate_impact_candidates([file], _graph())

    assert len(candidates) == 1
    assert candidates[0].consumer_service == "api-gateway"
    assert candidates[0].after is not None
    assert candidates[0].after.path == "/customers/{ownerId}"
