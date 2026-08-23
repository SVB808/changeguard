from __future__ import annotations

from pydantic import BaseModel

from changeguard.effective_selection_evaluation import (
    EffectiveSelectionEvaluationReport,
    evaluate_effective_selector,
)
from changeguard.evaluation import EvaluationReport, evaluate_corpus, load_corpus
from changeguard.evaluation_cli import DEFAULT_CORPUS
from changeguard.runtime_selection_corpus import build_runtime_selection_corpus
from changeguard.synthesis import EvidenceSelector


class ReleaseEvaluationReport(BaseModel):
    release_candidate: str
    deterministic_impact: EvaluationReport
    runtime_selection: EffectiveSelectionEvaluationReport
    deterministic_gate_passed: bool
    grounding_gate_passed: bool
    policy_mandatory_gate_passed: bool
    corpus_policy_gate_passed: bool
    release_gate_passed: bool


def evaluate_release_candidate(
    selector: EvidenceSelector,
    *,
    runs_per_case: int = 1,
    warmup_runs_per_case: int = 0,
) -> ReleaseEvaluationReport:
    """Run the controlled deterministic and runtime-shaped synthesis gates together."""
    deterministic = evaluate_corpus(load_corpus(DEFAULT_CORPUS))
    runtime_selection = evaluate_effective_selector(
        build_runtime_selection_corpus(),
        selector,
        runs_per_case=runs_per_case,
        warmup_runs_per_case=warmup_runs_per_case,
    )

    deterministic_gate = deterministic.exact_matches == deterministic.total_cases
    grounding_gate = (
        runtime_selection.successful_selections == runtime_selection.total_runs
        and runtime_selection.raw_guardrail_passes == runtime_selection.total_runs
        and runtime_selection.effective_guardrail_passes == runtime_selection.total_runs
    )
    mandatory_retention = runtime_selection.policy_mandatory.effective_retention
    policy_mandatory_gate = mandatory_retention in (None, 1.0)
    corpus_policy_gate = not runtime_selection.corpus_policy_diagnostics

    return ReleaseEvaluationReport(
        release_candidate="1.0.0rc1",
        deterministic_impact=deterministic,
        runtime_selection=runtime_selection,
        deterministic_gate_passed=deterministic_gate,
        grounding_gate_passed=grounding_gate,
        policy_mandatory_gate_passed=policy_mandatory_gate,
        corpus_policy_gate_passed=corpus_policy_gate,
        release_gate_passed=(
            deterministic_gate
            and grounding_gate
            and policy_mandatory_gate
            and corpus_policy_gate
        ),
    )
