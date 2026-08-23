import pytest

from changeguard.synthesis import (
    EvidenceCategory,
    EvidenceItem,
    EvidenceTier,
    SynthesisGuardrailError,
    SynthesisSelection,
    apply_decision_critical_policy,
)


def _item(
    item_id: str,
    category: EvidenceCategory,
    *,
    tier: EvidenceTier,
    source_paths: list[str],
) -> EvidenceItem:
    return EvidenceItem(
        id=item_id,
        tier=tier,
        category=category,
        statement=item_id,
        source_paths=source_paths,
    )


def test_policy_adds_verification_active_impacts_and_linked_semantic_change():
    evidence = [
        _item(
            "verification-result:0",
            EvidenceCategory.VERIFICATION_RESULT,
            tier=EvidenceTier.VERIFICATION,
            source_paths=["provider/OrderResource.java"],
        ),
        _item(
            "impact:0",
            EvidenceCategory.IMPACT,
            tier=EvidenceTier.INFERENCE,
            source_paths=["provider/OrderResource.java", "consumer-a/Client.java"],
        ),
        _item(
            "impact:1",
            EvidenceCategory.IMPACT,
            tier=EvidenceTier.INFERENCE,
            source_paths=["provider/OrderResource.java", "consumer-b/Client.java"],
        ),
        _item(
            "semantic:0:0",
            EvidenceCategory.SEMANTIC_CHANGE,
            tier=EvidenceTier.FACT,
            source_paths=["provider/OrderResource.java"],
        ),
        _item(
            "security:9:0",
            EvidenceCategory.SECURITY_CHANGE,
            tier=EvidenceTier.FACT,
            source_paths=["unrelated/SecurityConfig.java"],
        ),
    ]
    raw = SynthesisSelection(
        selected_evidence_ids=["impact:0", "security:9:0"],
        selector="ollama",
        model="test-model",
    )

    effective = apply_decision_critical_policy(evidence, raw)

    assert effective.selected_evidence_ids == [
        "verification-result:0",
        "impact:0",
        "impact:1",
        "semantic:0:0",
        "security:9:0",
    ]
    assert effective.policy_added_evidence_ids == [
        "verification-result:0",
        "impact:1",
        "semantic:0:0",
    ]
    assert effective.policy_dropped_evidence_ids == []
    assert effective.selector == "ollama"
    assert effective.model == "test-model"


def test_policy_uses_remaining_budget_for_selector_context_and_drops_overflow():
    evidence = [
        _item(
            f"impact:{index}",
            EvidenceCategory.IMPACT,
            tier=EvidenceTier.INFERENCE,
            source_paths=[f"provider/{index}.java"],
        )
        for index in range(10)
    ]
    evidence.extend(
        [
            _item(
                "security:0:0",
                EvidenceCategory.SECURITY_CHANGE,
                tier=EvidenceTier.FACT,
                source_paths=["security/0.java"],
            ),
            _item(
                "security:0:1",
                EvidenceCategory.SECURITY_CHANGE,
                tier=EvidenceTier.FACT,
                source_paths=["security/1.java"],
            ),
            _item(
                "security:0:2",
                EvidenceCategory.SECURITY_CHANGE,
                tier=EvidenceTier.FACT,
                source_paths=["security/2.java"],
            ),
        ]
    )
    raw = SynthesisSelection(
        selected_evidence_ids=["security:0:0", "security:0:1", "security:0:2"],
        selector="ollama",
    )

    effective = apply_decision_critical_policy(evidence, raw)

    assert effective.selected_evidence_ids[:10] == [f"impact:{index}" for index in range(10)]
    assert effective.selected_evidence_ids[10:] == ["security:0:0", "security:0:1"]
    assert effective.policy_dropped_evidence_ids == ["security:0:2"]


def test_policy_fails_closed_when_mandatory_evidence_exceeds_budget():
    evidence = [
        _item(
            f"impact:{index}",
            EvidenceCategory.IMPACT,
            tier=EvidenceTier.INFERENCE,
            source_paths=[f"provider/{index}.java"],
        )
        for index in range(13)
    ]

    with pytest.raises(SynthesisGuardrailError, match="Decision-critical evidence exceeds"):
        apply_decision_critical_policy(evidence, SynthesisSelection())


def test_policy_does_not_repair_invented_model_ids():
    evidence = [
        _item(
            "impact:0",
            EvidenceCategory.IMPACT,
            tier=EvidenceTier.INFERENCE,
            source_paths=["provider/OrderResource.java"],
        )
    ]
    raw = SynthesisSelection(
        selected_evidence_ids=["invented:production-outage"],
        selector="ollama",
    )

    with pytest.raises(SynthesisGuardrailError, match="did not produce"):
        apply_decision_critical_policy(evidence, raw)
