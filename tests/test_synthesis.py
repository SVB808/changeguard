import pytest

from changeguard.models import (
    ChangeManifest,
    ChangeStatus,
    ConsumerHttpCall,
    DependencyEdge,
    DependencyKind,
    EndpointChangeKind,
    EndpointSemanticChange,
    FileChange,
    ImpactCandidate,
    ImpactMatchLevel,
    SpringEndpoint,
    VerificationPlan,
    VerificationResult,
    VerificationStatus,
)
from changeguard.synthesis import (
    EvidenceCategory,
    EvidenceTier,
    SynthesisGuardrailError,
    SynthesisSelection,
    collect_evidence,
    synthesize_manifest,
)


PROVIDER_FILE = "benchmarks/client-style-path-break/provider-service/src/main/java/benchmark/provider/OrderResource.java"
CONSUMER_FILE = "benchmarks/client-style-path-break/feign-consumer-service/src/main/java/benchmark/feign/OrdersFeign.java"


def _endpoint(path: str) -> SpringEndpoint:
    return SpringEndpoint(
        controller="OrderResource",
        method_name="findOrder",
        http_method="GET",
        path=path,
        return_type="String",
        parameter_types=["int"],
    )


def _manifest() -> ChangeManifest:
    before = _endpoint("/orders/{orderId}")
    after = _endpoint("/purchases/{orderId}")
    edge = DependencyEdge(
        source="feign-consumer-service",
        target="provider-service",
        source_module="benchmarks/client-style-path-break/feign-consumer-service",
        target_module="benchmarks/client-style-path-break/provider-service",
        kind=DependencyKind.DECLARATIVE_CLIENT,
        evidence_path=CONSUMER_FILE,
        evidence='@FeignClient(name = "provider-service")',
    )
    call = ConsumerHttpCall(
        consumer_service="feign-consumer-service",
        target_service="provider-service",
        consumer_module="benchmarks/client-style-path-break/feign-consumer-service",
        target_module="benchmarks/client-style-path-break/provider-service",
        http_method="GET",
        path="/orders/{orderId}",
        evidence_path=CONSUMER_FILE,
        evidence='@GetMapping("/{orderId}")',
    )
    candidate = ImpactCandidate(
        provider_service="provider-service",
        consumer_service="feign-consumer-service",
        provider_module="benchmarks/client-style-path-break/provider-service",
        consumer_module="benchmarks/client-style-path-break/feign-consumer-service",
        changed_file=PROVIDER_FILE,
        trigger_kind=EndpointChangeKind.ENDPOINT_PATH_CHANGED,
        before=before,
        after=after,
        match_level=ImpactMatchLevel.ENDPOINT,
        reason="Provider endpoint path changed.",
        dependency_evidence=[edge],
        consumer_call_evidence=[call],
    )
    plan = VerificationPlan(
        provider_service="provider-service",
        consumer_service="feign-consumer-service",
        consumer_module="benchmarks/client-style-path-break/feign-consumer-service",
        changed_file=PROVIDER_FILE,
        trigger_kind=EndpointChangeKind.ENDPOINT_PATH_CHANGED,
        endpoint=before,
        command=[
            "mvn",
            "-f",
            "benchmarks/client-style-path-break/pom.xml",
            "-pl",
            "feign-consumer-service",
            "-am",
            "test",
        ],
        reason="Run targeted consumer tests.",
    )
    return ChangeManifest(
        repo="SVB808/changeguard",
        base="a" * 40,
        head="b" * 40,
        files=[
            FileChange(
                status=ChangeStatus.MODIFIED,
                path=PROVIDER_FILE,
                language="java",
                semantic_changes=[
                    EndpointSemanticChange(
                        kind=EndpointChangeKind.ENDPOINT_PATH_CHANGED,
                        before=before,
                        after=after,
                    )
                ],
            )
        ],
        impact_analysis_enabled=True,
        impact_candidates=[candidate],
        verification_planning_enabled=True,
        verification_plans=[plan],
    )


def test_collects_fact_inference_and_plan_evidence():
    evidence = collect_evidence(_manifest())

    assert {item.category for item in evidence} == {
        EvidenceCategory.SEMANTIC_CHANGE,
        EvidenceCategory.IMPACT,
        EvidenceCategory.VERIFICATION_PLAN,
    }
    assert {item.tier for item in evidence} == {
        EvidenceTier.FACT,
        EvidenceTier.INFERENCE,
    }


def test_langgraph_synthesis_renders_only_grounded_evidence():
    report = synthesize_manifest(_manifest())

    assert report.headline == (
        "Compatibility-sensitive cross-service impact evidence reached endpoint scope."
    )
    assert report.evidence
    assert all(item.id for item in report.evidence)
    assert any(item.category == EvidenceCategory.IMPACT for item in report.evidence)
    assert any("NOT_RUN" in item.statement for item in report.evidence)
    assert any("does not inspect new repository content" in caveat for caveat in report.caveats)


def test_failed_verification_is_process_evidence_not_breakage_claim():
    manifest = _manifest()
    result = VerificationResult(
        plan=manifest.verification_plans[0],
        status=VerificationStatus.FAILED,
        exit_code=1,
        stdout_tail="test failure",
    )

    report = synthesize_manifest(manifest, [result])

    verification = next(
        item for item in report.evidence if item.tier == EvidenceTier.VERIFICATION
    )
    assert "does not by itself prove causal breakage" in verification.statement
    assert "non-zero exit status" in report.headline
    assert any("not automatic proof" in caveat for caveat in report.caveats)


def test_passed_verification_does_not_become_safe_claim():
    manifest = _manifest()
    result = VerificationResult(
        plan=manifest.verification_plans[0],
        status=VerificationStatus.PASSED,
        exit_code=0,
    )

    report = synthesize_manifest(manifest, [result])

    verification = next(
        item for item in report.evidence if item.tier == EvidenceTier.VERIFICATION
    )
    assert "not that the change is safe" in verification.statement
    assert any("does not prove the change is universally safe" in caveat for caveat in report.caveats)


def test_selector_cannot_invent_evidence_ids():
    class HostileSelector:
        def select(self, evidence):
            return SynthesisSelection(selected_evidence_ids=["invented:production-outage"])

    with pytest.raises(SynthesisGuardrailError, match="did not produce"):
        synthesize_manifest(_manifest(), selector=HostileSelector())


def test_empty_manifest_produces_explicit_no_active_impact_report():
    manifest = ChangeManifest(repo="acme/empty", base="a" * 40, head="b" * 40)

    report = synthesize_manifest(manifest)

    assert report.evidence == []
    assert report.omitted_evidence_count == 0
    assert report.headline == (
        "No active cross-service impact candidate is present in the supplied manifest."
    )
