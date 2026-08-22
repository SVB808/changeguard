from changeguard.selection_evaluation import (
    SelectionBenchmarkCase,
    SelectionBenchmarkCorpus,
    compare_selection_reports,
    evaluate_selector,
)
from changeguard.synthesis import (
    EvidenceCategory,
    EvidenceItem,
    EvidenceTier,
    SynthesisSelection,
)


class SequenceSelector:
    def __init__(self, selections):
        self.selections = list(selections)
        self.index = 0

    def select(self, evidence):
        selected = self.selections[self.index]
        self.index += 1
        return SynthesisSelection(
            selected_evidence_ids=selected,
            selector="sequence",
            model="fixture-model",
            input_tokens=10,
            output_tokens=2,
        )


def _corpus() -> SelectionBenchmarkCorpus:
    return SelectionBenchmarkCorpus(
        version="fixture-v1",
        description="fixture",
        cases=[
            SelectionBenchmarkCase(
                id="case",
                description="fixture case",
                evidence=[
                    EvidenceItem(
                        id="required",
                        tier=EvidenceTier.INFERENCE,
                        category=EvidenceCategory.IMPACT,
                        statement="required impact",
                    ),
                    EvidenceItem(
                        id="optional",
                        tier=EvidenceTier.FACT,
                        category=EvidenceCategory.SEMANTIC_CHANGE,
                        statement="optional fact",
                    ),
                    EvidenceItem(
                        id="distractor",
                        tier=EvidenceTier.FACT,
                        category=EvidenceCategory.SECURITY_CHANGE,
                        statement="unrelated fact",
                    ),
                ],
                required_evidence_ids=["required"],
                optional_evidence_ids=["optional"],
                distractor_evidence_ids=["distractor"],
            )
        ],
    )


def test_warmup_runs_are_validated_but_excluded_from_scored_metrics_and_tokens():
    selector = SequenceSelector(
        [
            ["distractor"],  # unscored warmup
            ["required"],
            ["required", "optional"],
        ]
    )

    report = evaluate_selector(
        _corpus(),
        selector,
        warmup_runs_per_case=1,
        runs_per_case=2,
    )

    assert report.total_warmup_runs == 1
    assert report.successful_warmups == 1
    assert report.warmup_guardrail_passes == 1
    assert report.total_runs == 2
    assert report.required_evidence_recall == 1.0
    assert report.selection_precision == 1.0
    assert report.distractor_selection_rate == 0.0
    assert report.input_tokens_total == 20
    assert report.output_tokens_total == 4
    assert report.warmups[0].selected_evidence_ids == ["distractor"]


def test_cross_batch_comparison_reports_exact_matches_and_jaccard():
    left = evaluate_selector(
        _corpus(),
        SequenceSelector([["required"], ["required", "optional"]]),
        runs_per_case=2,
    )
    right = evaluate_selector(
        _corpus(),
        SequenceSelector([["required"], ["required", "distractor"]]),
        runs_per_case=2,
    )

    comparison = compare_selection_reports(left, right)

    assert comparison.aligned_runs == 2
    assert comparison.comparable_grounded_runs == 2
    assert comparison.exact_ordered_matches == 1
    assert comparison.exact_ordered_match_rate == 0.5
    assert comparison.exact_set_matches == 1
    assert comparison.exact_set_match_rate == 0.5
    assert comparison.mean_cross_batch_jaccard == 0.75
    assert comparison.quality_metric_deltas["selection_precision"] < 0
    assert comparison.quality_metric_deltas["distractor_selection_rate"] > 0


def test_cross_batch_comparison_rejects_different_warmup_protocols():
    left = evaluate_selector(
        _corpus(),
        SequenceSelector([["required"]]),
        runs_per_case=1,
    )
    right = evaluate_selector(
        _corpus(),
        SequenceSelector([["required"], ["required"]]),
        warmup_runs_per_case=1,
        runs_per_case=1,
    )

    try:
        compare_selection_reports(left, right)
    except ValueError as exc:
        assert "different protocols" in str(exc)
        assert "warmup_runs_per_case" in str(exc)
    else:
        raise AssertionError("expected mismatched protocol to be rejected")
