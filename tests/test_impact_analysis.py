from changeguard.impact_analysis import (
    generate_impact_candidates,
    refine_impact_candidates,
)
from changeguard.models import (
    ChangeStatus,
    ConsumerHttpCall,
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


def _endpoint(path: str, method: str = "GET", parameter_types: list[str] | None = None) -> SpringEndpoint:
    return SpringEndpoint(
        controller="OwnerResource",
        method_name="findOwner",
        http_method=method,
        path=path,
        return_type="OwnerDetails",
        parameter_types=parameter_types or ["int"],
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
        consumer_calls=consumer_calls or [],
    )


def _call(method: str, path: str) -> ConsumerHttpCall:
    return ConsumerHttpCall(
        consumer_service="api-gateway",
        target_service="customers-service",
        http_method=method,
        path=path,
        evidence_path=(
            "spring-petclinic-api-gateway/src/main/java/example/"
            "CustomersServiceClient.java"
        ),
        evidence=f'.{method.lower()}().uri("http://customers-service{path}")',
    )


def _removed_file(path: str, method: str = "GET") -> FileChange:
    return FileChange(
        status=ChangeStatus.MODIFIED,
        path="spring-petclinic-customers-service/src/main/java/example/OwnerResource.java",
        service="customers-service",
        semantic_changes=[
            EndpointSemanticChange(
                kind=EndpointChangeKind.ENDPOINT_REMOVED,
                before=_endpoint(path, method=method),
            )
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


def test_exact_consumer_call_upgrades_candidate_to_endpoint_match():
    file = _removed_file("/owners/{ownerId}")
    graph = _graph([_call("GET", "/owners/{id}")])

    service_candidates = generate_impact_candidates([file], graph)
    active, suppressed = refine_impact_candidates(service_candidates, graph)

    assert suppressed == []
    assert len(active) == 1
    assert active[0].match_level == ImpactMatchLevel.ENDPOINT
    assert active[0].consumer_call_evidence[0].path == "/owners/{id}"


def test_non_matching_explicit_call_suppresses_service_level_candidate():
    before = _endpoint(
        "/owners",
        method="POST",
        parameter_types=["Owner"],
    )
    after = _endpoint(
        "/owners",
        method="POST",
        parameter_types=["OwnerRequest"],
    )
    file = FileChange(
        status=ChangeStatus.MODIFIED,
        path="spring-petclinic-customers-service/src/main/java/example/OwnerResource.java",
        service="customers-service",
        semantic_changes=[
            EndpointSemanticChange(
                kind=EndpointChangeKind.REQUEST_SIGNATURE_CHANGED,
                before=before,
                after=after,
            )
        ],
    )
    graph = _graph([_call("GET", "/owners/{ownerId}")])

    service_candidates = generate_impact_candidates([file], graph)
    active, suppressed = refine_impact_candidates(service_candidates, graph)

    assert active == []
    assert len(suppressed) == 1
    assert suppressed[0].match_level == ImpactMatchLevel.SERVICE
    assert suppressed[0].suppression_reason is not None
    assert suppressed[0].consumer_call_evidence[0].http_method == "GET"


def test_query_string_and_variable_name_do_not_hide_endpoint_match():
    file = _removed_file("/owners/{ownerId}")
    graph = _graph([_call("GET", "/owners/{id}?expand=pets")])

    service_candidates = generate_impact_candidates([file], graph)
    active, suppressed = refine_impact_candidates(service_candidates, graph)

    assert suppressed == []
    assert len(active) == 1
    assert active[0].match_level == ImpactMatchLevel.ENDPOINT


def test_any_method_endpoint_matches_concrete_consumer_method():
    file = _removed_file("/events/{eventId}", method="ANY")
    graph = _graph([_call("POST", "/events/{id}")])

    service_candidates = generate_impact_candidates([file], graph)
    active, suppressed = refine_impact_candidates(service_candidates, graph)

    assert suppressed == []
    assert len(active) == 1
    assert active[0].match_level == ImpactMatchLevel.ENDPOINT


def test_recursive_spring_wildcard_matches_nested_consumer_route():
    file = _removed_file("/files/**")
    graph = _graph([_call("GET", "/files/reports/2026/summary")])

    service_candidates = generate_impact_candidates([file], graph)
    active, suppressed = refine_impact_candidates(service_candidates, graph)

    assert suppressed == []
    assert len(active) == 1
    assert active[0].match_level == ImpactMatchLevel.ENDPOINT


def test_single_spring_wildcard_does_not_cross_path_segment():
    file = _removed_file("/files/*/metadata")
    graph = _graph([_call("GET", "/files/a/b/metadata")])

    service_candidates = generate_impact_candidates([file], graph)
    active, suppressed = refine_impact_candidates(service_candidates, graph)

    assert active == []
    assert len(suppressed) == 1
