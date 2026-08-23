from changeguard.effective_selection_evaluation import evaluate_effective_selector
from changeguard.selection_evaluation import (
    SelectionBenchmarkCase,
    SelectionBenchmarkCorpus,
    SelectionCoverageGroup,
)
from changeguard.synthesis import (
    EvidenceCategory,
    EvidenceItem,
    EvidenceTier,
    SynthesisSelection,
)


class FixedSelector:
    def select(self, evidence):
        return SynthesisSelection(
            selected_evidence_ids=["impact:0", "security:9:0"],
            selector="ollama",
            model="fixture-model",
            input_tokens=20,
            output_tokens=4,
        )


class SemanticOnlySelector:
    def select(self, evidence):
        return SynthesisSelection(
            selected_evidence_ids=["semantic:0:0"],
            selector="ollama",
            model="fixture-model",
        )


def _corpus() -> SelectionBenchmarkCorpus:
    provider = "provider/OrderResource.java"
    return SelectionBenchmarkCorpus(
        version="effective-fixture-v1",
        description="raw versus effective fixture",
        cases=[
            SelectionBenchmarkCase(
                id="two-consumers",
                description="policy must restore the second consumer and shared semantic fact",
                evidence=[
                    EvidenceItem(
                        id="impact:0",
                        tier=EvidenceTier.INFERENCE,
                        category=EvidenceCategory.IMPACT,
                        statement="provider -> consumer-a",
                        source_paths=[provider, "consumer-a/Client.java"],
                    ),
                    EvidenceItem(
                        id="impact:1",
                        tier=EvidenceTier.INFERENCE,
                        category=EvidenceCategory.IMPACT,
                        statement="provider -> consumer-b",
                        source_paths=[provider, "consumer-b/Client.java"],
                    ),
                    EvidenceItem(
                        id="semantic:0:0",
                        tier=EvidenceTier.FACT,
                        category=EvidenceCategory.SEMANTIC_CHANGE,
                        statement="endpoint path changed",
                        source_paths=[provider],
                    ),
                    EvidenceItem(
                        id="security:9:0",
                        tier=EvidenceTier.FACT,
                        category=EvidenceCategory.SECURITY_CHANGE,
                        statement="unrelated security fact",
                        source_paths=["unrelated/SecurityConfig.java"],
                    ),
                ],
                required_evidence_ids=["impact:0", "impact:1", "semantic:0:0"],
                optional_evidence_ids=[],
                distractor_evidence_ids=["security:9:0"],
                coverage_groups=[
                    SelectionCoverageGroup(name="consumer-a", evidence_ids=["impact:0"]),
                    SelectionCoverageGroup(name="consumer-b", evidence_ids=["impact:1"]),
                ],
                verification_critical_ids=[],
            )
        ],
    )


def _diagnostic_corpus() -> SelectionBenchmarkCorpus:
    return SelectionBenchmarkCorpus(
        version="diagnostic-fixture-v1",
        description="benchmark labels intentionally conflict with runtime policy semantics",
        cases=[
            SelectionBenchmarkCase(
                id="synthetic-provenance-mismatch",
                description="required semantic is unlinked while an active impact is labeled distractor",
                evidence=[
                    EvidenceItem(
                        id="semantic:0:0",
                        tier=EvidenceTier.FACT,
                        category=EvidenceCategory.SEMANTIC_CHANGE,
                        statement="provider endpoint changed",
                        source_paths=["provider/Resource.java"],
                    ),
                    EvidenceItem(
                        id="impact:0",
                        tier=EvidenceTier.INFERENCE,
                        category=EvidenceCategory.IMPACT,
                        statement="unrelated provider -> consumer",
                        source_paths=["consumer/Client.java"],
                    ),
                ],
                required_evidence_ids=["semantic:0:0"],
                optional_evidence_ids=[],
                distractor_evidence_ids=["impact:0"],
                coverage_groups=[],
                verification_critical_ids=[],
            )
        ],
    )


def test_effective_evaluator_uses_same_raw_call_and_restores_critical_coverage():
    report = evaluate_effective_selector(_corpus(), FixedSelector(), runs_per_case=2)

    assert report.total_runs == 2
    assert report.successful_selections == 2
    assert report.raw_guardrail_passes == 2
    assert report.effective_guardrail_passes == 2
    assert report.raw_quality.required_evidence_recall == 1 / 3
    assert report.raw_quality.distinct_consumer_coverage == 1 / 2
    assert report.effective_quality.required_evidence_recall == 1.0
    assert report.effective_quality.distinct_consumer_coverage == 1.0
    assert report.policy_intervention_runs == 2
    assert report.policy_added_evidence_total == 4
    assert report.policy_dropped_evidence_total == 0
    assert report.policy_mandatory.raw_hits == 2
    assert report.policy_mandatory.raw_total == 6
    assert report.policy_mandatory.raw_retention == 1 / 3
    assert report.policy_mandatory.effective_hits == 6
    assert report.policy_mandatory.effective_total == 6
    assert report.policy_mandatory.effective_retention == 1.0
    assert report.corpus_policy_diagnostics == []
    assert report.input_tokens_total == 40
    assert report.output_tokens_total == 8

    first = report.runs[0]
    assert first.raw.selected_evidence_ids == ["impact:0", "security:9:0"]
    assert first.effective is not None
    assert first.effective.selected_evidence_ids == [
        "impact:0",
        "impact:1",
        "semantic:0:0",
        "security:9:0",
    ]
    assert first.policy_added_evidence_ids == ["impact:1", "semantic:0:0"]
    assert first.policy_mandatory_evidence_ids == [
        "impact:0",
        "impact:1",
        "semantic:0:0",
    ]
    assert first.raw_policy_mandatory_hits == 1
    assert first.effective_policy_mandatory_hits == 3
    assert first.policy_mandatory_total == 3


def test_effective_evaluator_does_not_pretend_closure_filters_distractors():
    report = evaluate_effective_selector(_corpus(), FixedSelector())

    assert report.raw_quality.distractor_selection_rate == 0.5
    assert report.effective_quality.distractor_selection_rate == 0.25
    assert report.effective_quality.selection_precision == 0.75
    assert "security:9:0" in report.runs[0].effective.selected_evidence_ids


def test_effective_evaluator_reports_corpus_policy_semantic_mismatches():
    report = evaluate_effective_selector(_diagnostic_corpus(), SemanticOnlySelector())

    diagnostics = {(item.code, tuple(item.evidence_ids)) for item in report.corpus_policy_diagnostics}
    assert (
        "distractor-is-policy-mandatory",
        ("impact:0",),
    ) in diagnostics
    assert (
        "required-semantic-not-provenance-linked",
        ("semantic:0:0",),
    ) in diagnostics
    assert report.policy_mandatory.raw_retention == 0.0
    assert report.policy_mandatory.effective_retention == 1.0
