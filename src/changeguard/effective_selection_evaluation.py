from __future__ import annotations

import math
import time
from itertools import combinations

from pydantic import BaseModel, Field

from changeguard.model_selector import ModelSelectionError
from changeguard.selection_evaluation import (
    SelectionBenchmarkCase,
    SelectionBenchmarkCorpus,
    SelectionRunEvaluation,
)
from changeguard.synthesis import (
    EvidenceCategory,
    EvidenceSelector,
    SynthesisGuardrailError,
    SynthesisSelection,
    _validate_selection as validate_selection,
    apply_decision_critical_policy,
    decision_critical_evidence_ids,
)


class SelectionQualitySummary(BaseModel):
    valid_runs: int
    required_evidence_recall: float | None
    selection_precision: float | None
    distractor_selection_rate: float | None
    distinct_consumer_coverage: float | None
    verification_evidence_retention: float | None
    mean_pairwise_jaccard: float | None


class PolicyMandatorySummary(BaseModel):
    raw_hits: int
    raw_total: int
    raw_retention: float | None
    effective_hits: int
    effective_total: int
    effective_retention: float | None


class CorpusPolicyDiagnostic(BaseModel):
    case_id: str
    code: str
    evidence_ids: list[str] = Field(default_factory=list)
    message: str


class EffectiveSelectionRunPair(BaseModel):
    case_id: str
    run_index: int
    raw: SelectionRunEvaluation
    effective: SelectionRunEvaluation | None = None
    policy_added_evidence_ids: list[str] = Field(default_factory=list)
    policy_dropped_evidence_ids: list[str] = Field(default_factory=list)
    policy_mandatory_evidence_ids: list[str] = Field(default_factory=list)
    raw_policy_mandatory_hits: int = 0
    effective_policy_mandatory_hits: int = 0
    policy_mandatory_total: int = 0


class EffectiveSelectionEvaluationReport(BaseModel):
    corpus_version: str
    selector: str
    model: str | None = None
    total_cases: int
    runs_per_case: int
    total_runs: int
    warmup_runs_per_case: int = 0
    total_warmup_runs: int = 0
    successful_warmups: int = 0
    effective_warmup_guardrail_passes: int = 0
    successful_selections: int
    raw_guardrail_passes: int
    effective_guardrail_passes: int
    policy_intervention_runs: int
    policy_added_evidence_total: int
    policy_dropped_evidence_total: int
    raw_quality: SelectionQualitySummary
    effective_quality: SelectionQualitySummary
    policy_mandatory: PolicyMandatorySummary
    corpus_policy_diagnostics: list[CorpusPolicyDiagnostic] = Field(default_factory=list)
    p50_provider_latency_ms: float
    p95_provider_latency_ms: float
    input_tokens_total: int | None = None
    output_tokens_total: int | None = None
    runs: list[EffectiveSelectionRunPair] = Field(default_factory=list)


def evaluate_effective_selector(
    corpus: SelectionBenchmarkCorpus,
    selector: EvidenceSelector,
    *,
    runs_per_case: int = 1,
    warmup_runs_per_case: int = 0,
) -> EffectiveSelectionEvaluationReport:
    """Measure one provider selection before and after deterministic policy closure.

    Raw and effective metrics are derived from the same selector call for each measured
    run. This avoids comparing two independent model generations and keeps raw model
    quality observable instead of hiding it behind deterministic post-processing.
    """
    if runs_per_case < 1:
        raise ValueError("runs_per_case must be at least 1")
    if warmup_runs_per_case < 0:
        raise ValueError("warmup_runs_per_case cannot be negative")

    measured: list[EffectiveSelectionRunPair] = []
    total_warmups = 0
    successful_warmups = 0
    effective_warmup_guardrail_passes = 0
    selector_name: str | None = None
    model: str | None = None

    for case in corpus.cases:
        for warmup_index in range(1, warmup_runs_per_case + 1):
            pair, selection = _evaluate_pair(case, selector, warmup_index)
            total_warmups += 1
            if pair.raw.selector_success:
                successful_warmups += 1
            if pair.effective is not None and pair.effective.guardrail_passed:
                effective_warmup_guardrail_passes += 1
            if selection is not None:
                selector_name = selector_name or selection.selector
                model = model or selection.model

        for run_index in range(1, runs_per_case + 1):
            pair, selection = _evaluate_pair(case, selector, run_index)
            measured.append(pair)
            if selection is not None:
                selector_name = selector_name or selection.selector
                model = model or selection.model

    raw_runs = [pair.raw for pair in measured]
    effective_runs = [
        pair.effective for pair in measured if pair.effective is not None
    ]
    raw_valid = [run for run in raw_runs if run.guardrail_passed]
    effective_valid = [run for run in effective_runs if run.guardrail_passed]
    successful = [run for run in raw_runs if run.selector_success]
    intervention_runs = [
        pair
        for pair in measured
        if pair.policy_added_evidence_ids or pair.policy_dropped_evidence_ids
    ]
    latencies = [run.latency_ms for run in raw_runs]
    input_tokens = [
        run.input_tokens for run in successful if run.input_tokens is not None
    ]
    output_tokens = [
        run.output_tokens for run in successful if run.output_tokens is not None
    ]

    return EffectiveSelectionEvaluationReport(
        corpus_version=corpus.version,
        selector=selector_name or selector.__class__.__name__,
        model=model,
        total_cases=len(corpus.cases),
        runs_per_case=runs_per_case,
        total_runs=len(measured),
        warmup_runs_per_case=warmup_runs_per_case,
        total_warmup_runs=total_warmups,
        successful_warmups=successful_warmups,
        effective_warmup_guardrail_passes=effective_warmup_guardrail_passes,
        successful_selections=len(successful),
        raw_guardrail_passes=len(raw_valid),
        effective_guardrail_passes=len(effective_valid),
        policy_intervention_runs=len(intervention_runs),
        policy_added_evidence_total=sum(
            len(pair.policy_added_evidence_ids) for pair in measured
        ),
        policy_dropped_evidence_total=sum(
            len(pair.policy_dropped_evidence_ids) for pair in measured
        ),
        raw_quality=_quality_summary(raw_valid, runs_per_case),
        effective_quality=_quality_summary(effective_valid, runs_per_case),
        policy_mandatory=_policy_mandatory_summary(measured),
        corpus_policy_diagnostics=_diagnose_corpus_policy(corpus),
        p50_provider_latency_ms=_percentile(latencies, 0.50),
        p95_provider_latency_ms=_percentile(latencies, 0.95),
        input_tokens_total=sum(input_tokens) if input_tokens else None,
        output_tokens_total=sum(output_tokens) if output_tokens else None,
        runs=measured,
    )


def _evaluate_pair(
    case: SelectionBenchmarkCase,
    selector: EvidenceSelector,
    run_index: int,
) -> tuple[EffectiveSelectionRunPair, SynthesisSelection | None]:
    mandatory_ids = decision_critical_evidence_ids(case.evidence)
    mandatory_set = set(mandatory_ids)
    mandatory_total = len(mandatory_ids)
    started = time.perf_counter()
    try:
        selection = selector.select(case.evidence)
    except ModelSelectionError as exc:
        raw = SelectionRunEvaluation(
            case_id=case.id,
            run_index=run_index,
            selector_success=False,
            guardrail_passed=False,
            error=str(exc),
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
        return (
            EffectiveSelectionRunPair(
                case_id=case.id,
                run_index=run_index,
                raw=raw,
                policy_mandatory_evidence_ids=mandatory_ids,
                policy_mandatory_total=mandatory_total,
            ),
            None,
        )
    except Exception as exc:
        raw = SelectionRunEvaluation(
            case_id=case.id,
            run_index=run_index,
            selector_success=False,
            guardrail_passed=False,
            error=f"Selector raised {type(exc).__name__}: {exc}",
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
        return (
            EffectiveSelectionRunPair(
                case_id=case.id,
                run_index=run_index,
                raw=raw,
                policy_mandatory_evidence_ids=mandatory_ids,
                policy_mandatory_total=mandatory_total,
            ),
            None,
        )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    raw = _score_selection(case, selection, run_index, elapsed_ms)
    raw_mandatory_hits = len(set(selection.selected_evidence_ids) & mandatory_set)
    if not raw.guardrail_passed:
        return (
            EffectiveSelectionRunPair(
                case_id=case.id,
                run_index=run_index,
                raw=raw,
                policy_mandatory_evidence_ids=mandatory_ids,
                raw_policy_mandatory_hits=raw_mandatory_hits,
                policy_mandatory_total=mandatory_total,
            ),
            selection,
        )

    try:
        effective_selection = apply_decision_critical_policy(case.evidence, selection)
    except SynthesisGuardrailError as exc:
        effective = SelectionRunEvaluation(
            case_id=case.id,
            run_index=run_index,
            selector_success=True,
            guardrail_passed=False,
            selected_evidence_ids=selection.selected_evidence_ids,
            error=f"Decision-critical policy closure failed: {exc}",
            latency_ms=elapsed_ms,
            input_tokens=selection.input_tokens,
            output_tokens=selection.output_tokens,
        )
        effective_mandatory_hits = len(
            set(effective.selected_evidence_ids) & mandatory_set
        )
        return (
            EffectiveSelectionRunPair(
                case_id=case.id,
                run_index=run_index,
                raw=raw,
                effective=effective,
                policy_mandatory_evidence_ids=mandatory_ids,
                raw_policy_mandatory_hits=raw_mandatory_hits,
                effective_policy_mandatory_hits=effective_mandatory_hits,
                policy_mandatory_total=mandatory_total,
            ),
            selection,
        )

    effective = _score_selection(case, effective_selection, run_index, elapsed_ms)
    effective_mandatory_hits = len(
        set(effective_selection.selected_evidence_ids) & mandatory_set
    )
    return (
        EffectiveSelectionRunPair(
            case_id=case.id,
            run_index=run_index,
            raw=raw,
            effective=effective,
            policy_added_evidence_ids=effective_selection.policy_added_evidence_ids,
            policy_dropped_evidence_ids=effective_selection.policy_dropped_evidence_ids,
            policy_mandatory_evidence_ids=mandatory_ids,
            raw_policy_mandatory_hits=raw_mandatory_hits,
            effective_policy_mandatory_hits=effective_mandatory_hits,
            policy_mandatory_total=mandatory_total,
        ),
        selection,
    )


def _score_selection(
    case: SelectionBenchmarkCase,
    selection: SynthesisSelection,
    run_index: int,
    latency_ms: float,
) -> SelectionRunEvaluation:
    try:
        validate_selection(case.evidence, selection)
    except SynthesisGuardrailError as exc:
        return SelectionRunEvaluation(
            case_id=case.id,
            run_index=run_index,
            selector_success=True,
            guardrail_passed=False,
            selected_evidence_ids=selection.selected_evidence_ids,
            error=str(exc),
            latency_ms=latency_ms,
            input_tokens=selection.input_tokens,
            output_tokens=selection.output_tokens,
        )

    selected = set(selection.selected_evidence_ids)
    required = set(case.required_evidence_ids)
    optional = set(case.optional_evidence_ids)
    distractor = set(case.distractor_evidence_ids)
    verification = set(case.verification_critical_ids)
    coverage_hits = sum(
        bool(selected & set(group.evidence_ids)) for group in case.coverage_groups
    )
    return SelectionRunEvaluation(
        case_id=case.id,
        run_index=run_index,
        selector_success=True,
        guardrail_passed=True,
        selected_evidence_ids=selection.selected_evidence_ids,
        required_hits=len(selected & required),
        required_total=len(required),
        acceptable_hits=len(selected & (required | optional)),
        selected_total=len(selected),
        distractor_hits=len(selected & distractor),
        coverage_hits=coverage_hits,
        coverage_total=len(case.coverage_groups),
        verification_hits=len(selected & verification),
        verification_total=len(verification),
        latency_ms=latency_ms,
        input_tokens=selection.input_tokens,
        output_tokens=selection.output_tokens,
    )


def _quality_summary(
    valid_runs: list[SelectionRunEvaluation],
    runs_per_case: int,
) -> SelectionQualitySummary:
    required_hits = sum(run.required_hits for run in valid_runs)
    required_total = sum(run.required_total for run in valid_runs)
    acceptable_hits = sum(run.acceptable_hits for run in valid_runs)
    selected_total = sum(run.selected_total for run in valid_runs)
    distractor_hits = sum(run.distractor_hits for run in valid_runs)
    coverage_hits = sum(run.coverage_hits for run in valid_runs)
    coverage_total = sum(run.coverage_total for run in valid_runs)
    verification_hits = sum(run.verification_hits for run in valid_runs)
    verification_total = sum(run.verification_total for run in valid_runs)
    return SelectionQualitySummary(
        valid_runs=len(valid_runs),
        required_evidence_recall=_optional_ratio(required_hits, required_total),
        selection_precision=_optional_ratio(acceptable_hits, selected_total),
        distractor_selection_rate=_optional_ratio(distractor_hits, selected_total),
        distinct_consumer_coverage=_optional_ratio(coverage_hits, coverage_total),
        verification_evidence_retention=_optional_ratio(
            verification_hits, verification_total
        ),
        mean_pairwise_jaccard=_mean_pairwise_jaccard(valid_runs, runs_per_case),
    )


def _policy_mandatory_summary(
    measured: list[EffectiveSelectionRunPair],
) -> PolicyMandatorySummary:
    raw_valid = [pair for pair in measured if pair.raw.guardrail_passed]
    effective_valid = [
        pair
        for pair in measured
        if pair.effective is not None and pair.effective.guardrail_passed
    ]
    raw_hits = sum(pair.raw_policy_mandatory_hits for pair in raw_valid)
    raw_total = sum(pair.policy_mandatory_total for pair in raw_valid)
    effective_hits = sum(
        pair.effective_policy_mandatory_hits for pair in effective_valid
    )
    effective_total = sum(pair.policy_mandatory_total for pair in effective_valid)
    return PolicyMandatorySummary(
        raw_hits=raw_hits,
        raw_total=raw_total,
        raw_retention=_optional_ratio(raw_hits, raw_total),
        effective_hits=effective_hits,
        effective_total=effective_total,
        effective_retention=_optional_ratio(effective_hits, effective_total),
    )


def _diagnose_corpus_policy(
    corpus: SelectionBenchmarkCorpus,
) -> list[CorpusPolicyDiagnostic]:
    diagnostics: list[CorpusPolicyDiagnostic] = []
    for case in corpus.cases:
        evidence_by_id = {item.id: item for item in case.evidence}
        mandatory_ids = set(decision_critical_evidence_ids(case.evidence))

        mandatory_distractors = sorted(
            mandatory_ids.intersection(case.distractor_evidence_ids)
        )
        if mandatory_distractors:
            diagnostics.append(
                CorpusPolicyDiagnostic(
                    case_id=case.id,
                    code="distractor-is-policy-mandatory",
                    evidence_ids=mandatory_distractors,
                    message=(
                        "The corpus labels runtime policy-mandatory evidence as a "
                        "distractor. Effective policy closure will preserve these IDs."
                    ),
                )
            )

        has_active_impact = any(
            item.category == EvidenceCategory.IMPACT for item in case.evidence
        )
        if not has_active_impact:
            continue
        for evidence_id in case.required_evidence_ids:
            item = evidence_by_id[evidence_id]
            if (
                item.category == EvidenceCategory.SEMANTIC_CHANGE
                and evidence_id not in mandatory_ids
            ):
                diagnostics.append(
                    CorpusPolicyDiagnostic(
                        case_id=case.id,
                        code="required-semantic-not-provenance-linked",
                        evidence_ids=[evidence_id],
                        message=(
                            "Required semantic evidence does not share source-path "
                            "provenance with any active impact in this corpus case, so "
                            "decision-critical closure cannot guarantee it."
                        ),
                    )
                )
    return diagnostics


def _mean_pairwise_jaccard(
    valid_runs: list[SelectionRunEvaluation],
    runs_per_case: int,
) -> float | None:
    if runs_per_case < 2:
        return None
    by_case: dict[str, list[set[str]]] = {}
    for run in valid_runs:
        by_case.setdefault(run.case_id, []).append(set(run.selected_evidence_ids))
    scores: list[float] = []
    for selections in by_case.values():
        for left, right in combinations(selections, 2):
            union = left | right
            scores.append(1.0 if not union else len(left & right) / len(union))
    return sum(scores) / len(scores) if scores else None


def _optional_ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]