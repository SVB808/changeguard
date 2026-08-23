from pathlib import Path

import pytest

from changeguard.model_selector import ModelSelectionError
from changeguard.selection_evaluation import (
    SelectionBenchmarkCase,
    SelectionBenchmarkCorpus,
    SelectionCoverageGroup,
    evaluate_selector,
    load_selection_corpus,
)
from changeguard.synthesis import (
    DeterministicEvidenceSelector,
    EvidenceCategory,
    EvidenceItem,
    EvidenceTier,
    SynthesisSelection,
)


DEFAULT_CORPUS = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "evaluation"
    / "synthesis-selection-v1.json"
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
            model="fake-model",
            input_tokens=10,
            output_tokens=2,
        )


class ErrorSelector:
    def select(self, evidence):
        raise ModelSelectionError("provider unavailable")


def _case() -> SelectionBenchmarkCase:
    return SelectionBenchmarkCase(
        id="case",
        description="metric fixture",
        evidence=[
            EvidenceItem(
                id="required",
                tier=EvidenceTier.VERIFICATION,
                category=EvidenceCategory.VERIFICATION_RESULT,
                statement="verification evidence",
            ),
            EvidenceItem(
                id="optional",
                tier=EvidenceTier.FACT,
                category=EvidenceCategory.SEMANTIC_CHANGE,
                statement="supporting fact",
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
        coverage_groups=[
            SelectionCoverageGroup(name="consumer", evidence_ids=["required"])
        ],
        verification_critical_ids=["required"],
    )


def test_default_selection_corpus_loads_and_labels_every_evidence_item():
    corpus = load_selection_corpus(DEFAULT_CORPUS)

    assert corpus.version == "synthesis-selection-v1"
    assert len(corpus.cases) == 9
    assert any(case.id == "prompt-injection-distractor" for case in corpus.cases)
    assert any(case.id == "selection-budget-pressure" for case in corpus.cases)


def test_selection_metrics_separate_quality_grounding_and_stability():
    corpus = SelectionBenchmarkCorpus(
        version="fixture-v1",
        description="fixture",
        cases=[_case()],
    )
    selector = SequenceSelector([["required", "optional"], ["required"]])

    report = evaluate_selector(corpus, selector, runs_per_case=2)

    assert report.selection_success_rate == 1.0
    assert report.guardrail_pass_rate == 1.0
    assert report.required_evidence_recall == 1.0
    assert report.selection_precision == 1.0
    assert report.distractor_selection_rate == 0.0
    assert report.distinct_consumer_coverage == 1.0
    assert report.verification_evidence_retention == 1.0
    assert report.mean_pairwise_jaccard == 0.5
    assert report.input_tokens_total == 20
    assert report.output_tokens_total == 4


def test_guardrail_failure_is_distinct_from_provider_failure():
    corpus = SelectionBenchmarkCorpus(
        version="fixture-v1",
        description="fixture",
        cases=[_case()],
    )
    selector = SequenceSelector([["invented:outage"]])

    report = evaluate_selector(corpus, selector)

    assert report.successful_selections == 1
    assert report.guardrail_passes == 0
    assert report.guardrail_pass_rate == 0.0
    assert "did not produce" in report.runs[0].error


def test_provider_failure_does_not_count_as_returned_grounding_failure():
    corpus = SelectionBenchmarkCorpus(
        version="fixture-v1",
        description="fixture",
        cases=[_case()],
    )

    report = evaluate_selector(corpus, ErrorSelector())

    assert report.successful_selections == 0
    assert report.selection_success_rate == 0.0
    assert report.guardrail_pass_rate is None
    assert report.runs[0].error == "provider unavailable"


def test_deterministic_selector_is_stable_baseline_but_not_perfectly_selective():
    corpus = load_selection_corpus(DEFAULT_CORPUS)

    report = evaluate_selector(
        corpus,
        DeterministicEvidenceSelector(),
        runs_per_case=2,
    )

    assert report.total_runs == 18
    assert report.successful_selections == 18
    assert report.guardrail_passes == 18
    assert report.guardrail_pass_rate == 1.0
    assert report.mean_pairwise_jaccard == 1.0
    assert report.selection_precision is not None
    assert report.selection_precision < 1.0
    assert report.distractor_selection_rate is not None
    assert report.distractor_selection_rate > 0.0


def test_case_labels_reject_unlabeled_evidence():
    with pytest.raises(ValueError, match="label every evidence ID"):
        SelectionBenchmarkCase(
            id="bad",
            description="bad labels",
            evidence=[
                EvidenceItem(
                    id="evidence:0",
                    tier=EvidenceTier.FACT,
                    category=EvidenceCategory.SEMANTIC_CHANGE,
                    statement="fact",
                )
            ],
        )
