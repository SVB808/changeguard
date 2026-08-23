from __future__ import annotations

from changeguard.models import (
    ChangeManifest,
    ChangeStatus,
    ConsumerHttpCall,
    EndpointChangeKind,
    EndpointSemanticChange,
    FileChange,
    ImpactCandidate,
    ImpactMatchLevel,
    SecurityPolicyChangeKind,
    SecuritySemanticChange,
    ServiceDependencyGraph,
    SpringEndpoint,
    SpringSecurityPolicy,
    VerificationPlan,
    VerificationResult,
    VerificationStatus,
)
from changeguard.selection_evaluation import (
    SelectionBenchmarkCase,
    SelectionBenchmarkCorpus,
    SelectionCoverageGroup,
)
from changeguard.synthesis import collect_evidence


RUNTIME_SELECTION_CORPUS_VERSION = "synthesis-selection-runtime-v1"


def build_runtime_selection_corpus() -> SelectionBenchmarkCorpus:
    """Build evaluation cases through the same evidence collector used at runtime.

    Unlike the earlier hand-authored selector corpora, these cases start as typed
    ChangeManifest / VerificationResult objects. Evidence IDs, statements and source
    provenance are therefore produced by `collect_evidence()` itself. This makes the
    corpus suitable for validating runtime policy invariants without synthetic
    provenance mismatches.
    """
    return SelectionBenchmarkCorpus(
        version=RUNTIME_SELECTION_CORPUS_VERSION,
        description=(
            "Production-shaped evidence-selection corpus generated through "
            "ChangeGuard collect_evidence() from typed manifests and verification results."
        ),
        cases=[
            _two_consumers_with_verification_error(),
            _four_consumer_fanout(),
            _security_only(),
            _active_and_suppressed(),
        ],
    )


def _endpoint(
    *,
    controller: str,
    method_name: str,
    http_method: str,
    path: str,
    return_type: str = "String",
) -> SpringEndpoint:
    return SpringEndpoint(
        controller=controller,
        method_name=method_name,
        http_method=http_method,
        path=path,
        return_type=return_type,
        parameter_types=["String"],
    )


def _impact(
    *,
    provider: str,
    consumer: str,
    provider_path: str,
    consumer_path: str,
    before: SpringEndpoint,
    after: SpringEndpoint,
) -> ImpactCandidate:
    return ImpactCandidate(
        provider_service=provider,
        consumer_service=consumer,
        provider_module=provider,
        consumer_module=consumer,
        changed_file=provider_path,
        trigger_kind=EndpointChangeKind.ENDPOINT_PATH_CHANGED,
        before=before,
        after=after,
        match_level=ImpactMatchLevel.ENDPOINT,
        reason="Provider endpoint path changed.",
        consumer_call_evidence=[
            ConsumerHttpCall(
                consumer_service=consumer,
                target_service=provider,
                consumer_module=consumer,
                target_module=provider,
                http_method=before.http_method,
                path=before.path,
                evidence_path=consumer_path,
                evidence="Explicit parsed consumer call to the previous provider contract.",
            )
        ],
    )


def _plan(
    *,
    provider: str,
    consumer: str,
    provider_path: str,
    endpoint: SpringEndpoint,
    expected_head: str = "1" * 40,
) -> VerificationPlan:
    return VerificationPlan(
        provider_service=provider,
        consumer_service=consumer,
        consumer_module=consumer,
        changed_file=provider_path,
        trigger_kind=EndpointChangeKind.ENDPOINT_PATH_CHANGED,
        endpoint=endpoint,
        command=["mvn", "-pl", consumer, "-am", "test"],
        reason="Production-shaped targeted verification fixture.",
        expected_head=expected_head,
    )


def _manifest(
    *,
    repo: str,
    provider_path: str,
    semantic_change: EndpointSemanticChange | None,
    impacts: list[ImpactCandidate],
    suppressed: list[ImpactCandidate] | None = None,
    plans: list[VerificationPlan] | None = None,
    extra_files: list[FileChange] | None = None,
) -> ChangeManifest:
    files: list[FileChange] = []
    if semantic_change is not None:
        files.append(
            FileChange(
                status=ChangeStatus.MODIFIED,
                path=provider_path,
                language="java",
                semantic_changes=[semantic_change],
            )
        )
    files.extend(extra_files or [])
    return ChangeManifest(
        repo=repo,
        base="0" * 40,
        head="1" * 40,
        files=files,
        dependency_graph=ServiceDependencyGraph(),
        impact_analysis_enabled=True,
        impact_candidates=impacts,
        suppressed_impact_candidates=suppressed or [],
        verification_planning_enabled=bool(plans),
        verification_plans=plans or [],
    )


def _two_consumers_with_verification_error() -> SelectionBenchmarkCase:
    provider = "invoice-service"
    provider_path = "invoice-service/src/main/java/example/InvoiceResource.java"
    before = _endpoint(
        controller="InvoiceResource",
        method_name="getInvoice",
        http_method="GET",
        path="/invoices/{id}",
    )
    after = before.model_copy(update={"path": "/billing/invoices/{id}"})
    semantic = EndpointSemanticChange(
        kind=EndpointChangeKind.ENDPOINT_PATH_CHANGED,
        before=before,
        after=after,
    )
    impacts = [
        _impact(
            provider=provider,
            consumer="billing-client",
            provider_path=provider_path,
            consumer_path="billing-client/src/main/java/example/InvoiceClient.java",
            before=before,
            after=after,
        ),
        _impact(
            provider=provider,
            consumer="audit-client",
            provider_path=provider_path,
            consumer_path="audit-client/src/main/java/example/InvoiceClient.java",
            before=before,
            after=after,
        ),
    ]
    plans = [
        _plan(
            provider=provider,
            consumer="billing-client",
            provider_path=provider_path,
            endpoint=before,
        ),
        _plan(
            provider=provider,
            consumer="audit-client",
            provider_path=provider_path,
            endpoint=before,
        ),
    ]
    manifest = _manifest(
        repo="fixture/invoices",
        provider_path=provider_path,
        semantic_change=semantic,
        impacts=impacts,
        plans=plans,
    )
    result = VerificationResult(
        plan=plans[0],
        status=VerificationStatus.ERROR,
        error="Maven process timed out.",
    )
    evidence = collect_evidence(manifest, [result])
    return SelectionBenchmarkCase(
        id="runtime-two-consumers-verification-error",
        description=(
            "Runtime-shaped endpoint change with two active consumers and an execution "
            "error for one targeted verification."
        ),
        evidence=evidence,
        required_evidence_ids=[
            "verification-result:0",
            "impact:0",
            "impact:1",
            "semantic:0:0",
        ],
        optional_evidence_ids=["verification-plan:0", "verification-plan:1"],
        distractor_evidence_ids=[],
        coverage_groups=[
            SelectionCoverageGroup(
                name="billing-client",
                evidence_ids=["impact:0", "verification-result:0"],
            ),
            SelectionCoverageGroup(name="audit-client", evidence_ids=["impact:1"]),
        ],
        verification_critical_ids=["verification-result:0"],
    )


def _four_consumer_fanout() -> SelectionBenchmarkCase:
    provider = "profile-service"
    provider_path = "profile-service/src/main/java/example/ProfileResource.java"
    before = _endpoint(
        controller="ProfileResource",
        method_name="getProfile",
        http_method="GET",
        path="/profiles/{id}",
    )
    after = before.model_copy(update={"path": "/users/{id}"})
    semantic = EndpointSemanticChange(
        kind=EndpointChangeKind.ENDPOINT_PATH_CHANGED,
        before=before,
        after=after,
    )
    consumers = ["mobile-api", "web-api", "notification-service", "recommendation-service"]
    impacts = [
        _impact(
            provider=provider,
            consumer=consumer,
            provider_path=provider_path,
            consumer_path=f"{consumer}/src/main/java/example/ProfileClient.java",
            before=before,
            after=after,
        )
        for consumer in consumers
    ]
    manifest = _manifest(
        repo="fixture/profile",
        provider_path=provider_path,
        semantic_change=semantic,
        impacts=impacts,
    )
    evidence = collect_evidence(manifest)
    return SelectionBenchmarkCase(
        id="runtime-four-consumer-fanout",
        description=(
            "Runtime-shaped four-consumer fan-out whose active impacts all preserve the "
            "provider changed-file provenance used by policy closure."
        ),
        evidence=evidence,
        required_evidence_ids=[
            "semantic:0:0",
            "impact:0",
            "impact:1",
            "impact:2",
            "impact:3",
        ],
        optional_evidence_ids=[],
        distractor_evidence_ids=[],
        coverage_groups=[
            SelectionCoverageGroup(name=consumer, evidence_ids=[f"impact:{index}"])
            for index, consumer in enumerate(consumers)
        ],
        verification_critical_ids=[],
    )


def _security_only() -> SelectionBenchmarkCase:
    security_path = "checkout-service/src/main/java/example/SecurityConfig.java"
    security_policy = SpringSecurityPolicy(
        component="SecurityFilterChain",
        method_name="filterChain",
        authorization_rules=[],
        disabled_features=["csrf"],
    )
    manifest = _manifest(
        repo="fixture/checkout",
        provider_path=security_path,
        semantic_change=None,
        impacts=[],
        extra_files=[
            FileChange(
                status=ChangeStatus.MODIFIED,
                path=security_path,
                language="java",
                security_changes=[
                    SecuritySemanticChange(
                        kind=SecurityPolicyChangeKind.SECURITY_POLICY_CHANGED,
                        before=security_policy,
                        after=security_policy.model_copy(update={"disabled_features": []}),
                    )
                ],
            )
        ],
    )
    evidence = collect_evidence(manifest)
    return SelectionBenchmarkCase(
        id="runtime-security-only",
        description="Runtime-shaped security semantic change with no active impact candidate.",
        evidence=evidence,
        required_evidence_ids=["security:0:0"],
        optional_evidence_ids=[],
        distractor_evidence_ids=[],
        coverage_groups=[],
        verification_critical_ids=[],
    )


def _active_and_suppressed() -> SelectionBenchmarkCase:
    provider = "order-service"
    provider_path = "order-service/src/main/java/example/OrderResource.java"
    before = _endpoint(
        controller="OrderResource",
        method_name="getOrder",
        http_method="GET",
        path="/orders/{id}",
    )
    after = before.model_copy(update={"path": "/purchases/{id}"})
    semantic = EndpointSemanticChange(
        kind=EndpointChangeKind.ENDPOINT_PATH_CHANGED,
        before=before,
        after=after,
    )
    active = _impact(
        provider=provider,
        consumer="fulfillment-service",
        provider_path=provider_path,
        consumer_path="fulfillment-service/src/main/java/example/OrderClient.java",
        before=before,
        after=after,
    )
    suppressed = _impact(
        provider=provider,
        consumer="reporting-service",
        provider_path=provider_path,
        consumer_path="reporting-service/src/main/java/example/OrderClient.java",
        before=before,
        after=after,
    ).model_copy(
        update={
            "match_level": ImpactMatchLevel.SERVICE,
            "suppression_reason": "Explicit parsed calls use a different route.",
        }
    )
    manifest = _manifest(
        repo="fixture/orders",
        provider_path=provider_path,
        semantic_change=semantic,
        impacts=[active],
        suppressed=[suppressed],
    )
    evidence = collect_evidence(manifest)
    return SelectionBenchmarkCase(
        id="runtime-active-and-suppressed",
        description=(
            "Runtime-shaped active impact plus a separately preserved suppression audit trail."
        ),
        evidence=evidence,
        required_evidence_ids=["impact:0", "semantic:0:0", "suppressed-impact:0"],
        optional_evidence_ids=[],
        distractor_evidence_ids=[],
        coverage_groups=[
            SelectionCoverageGroup(name="fulfillment-service", evidence_ids=["impact:0"]),
            SelectionCoverageGroup(
                name="reporting-service-suppression",
                evidence_ids=["suppressed-impact:0"],
            ),
        ],
        verification_critical_ids=[],
    )
