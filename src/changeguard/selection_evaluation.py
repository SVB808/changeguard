from __future__ import annotations

import json
import math
import time
from itertools import combinations
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from changeguard.model_selector import ModelSelectionError
from changeguard.synthesis import (
    EvidenceItem,
    EvidenceSelector,
    SynthesisGuardrailError,
    SynthesisSelection,
    _validate_selection as validate_selection,
)


class SelectionCoverageGroup(BaseModel):
    name: str
    evidence_ids: list[str] = Field(min_length=1)


class SelectionBenchmarkCase(BaseModel):
    id: str
    description: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    optional_evidence_ids: list[str] = Field(default_factory=list)
    distractor_evidence_ids: list[str] = Field(default_factory=list)
    coverage_groups: list[SelectionCoverageGroup] = Field(default_factory=list)
    verification_critical_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_labels(self) -> "SelectionBenchmarkCase":
        evidence_ids = [item.id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError(f"Case {self.id!r} contains duplicate evidence IDs")

        required = set(self.required_evidence_ids)
        optional = set(self.optional_evidence_ids)
        distractor = set(self.distractor_evidence_ids)
        overlaps = (required & optional) | (required & distractor) | (optional & distractor)
        if overlaps:
            raise ValueError(
                f"Case {self.id!r} labels evidence IDs more than once: "
                + ", ".join(sorted(overlaps))
            )

        labeled = required | optional | distractor
        known = set(evidence_ids)
        if labeled != known:
            missing = sorted(known - labeled)
            unknown = sorted(labeled - known)
            detail: list[str] = []
            if missing:
                detail.append("unlabeled=" + ",".join(missing))
            if unknown:
                detail.append("unknown=" + ",".join(unknown))
            raise ValueError(
                f"Case {self.id!r} must label every evidence ID exactly once: "
                + "; ".join(detail)
            )

        acceptable = required | optional
        for group in self.coverage_groups:
            unknown_group_ids = sorted(set(group.evidence_ids) - acceptable)
            if unknown_group_ids:
                raise ValueError(
                    f"Case {self.id!r} coverage group {group.name!r} references "
                    "non-acceptable evidence: " + ", ".join(unknown_group_ids)
                )

        unknown_verification = sorted(set(self.verification_critical_ids) - acceptable)
        if unknown_verification:
            raise ValueError(
                f"Case {self.id!r} verification-critical IDs must be required or "
                "optional evidence: " + ", ".join(unknown_verification)
            )
        return self


class SelectionBenchmarkCorpus(BaseModel):
    version: str
    description: str
    cases: list[SelectionBenchmarkCase]


class SelectionRunEvaluation(BaseModel):
    case_id: str
    run_index: int
    selector_success: bool
    guardrail_passed: bool
    selected_evidence_ids: list[str] = Field(default_factory=list)
    error: str | None = None
    required_hits: int = 0
    required_total: int = 0
    acceptable_hits: int = 0
    selected_total: int = 0
    distractor_hits: int = 0
    coverage_hits: int = 0
    coverage_total: int = 0
    verification_hits: int = 0
    verification_total: int = 0
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def required_recall(self) -> float | None:
        return _optional_ratio(self.required_hits, self.required_total)

    @property
    def selection_precision(self) -> float | None:
        return _optional_ratio(self.acceptable_hits, self.selected_total)

    @property
    def distractor_rate(self) -> float | None:
        return _optional_ratio(self.distractor_hits, self.selected_total)

    @property
    def consumer_coverage(self) -> float | None:
        return _optional_ratio(self.coverage_hits, self.coverage_total)

    @property
    def verification_retention(self) -> float | None:
        return _optional_ratio(self.verification_hits, self.verification_total)


class SelectionEvaluationReport(BaseModel):
    corpus_version: str
    selector: str
    model: str | None = None
    total_cases: int
    runs_per_case: int
    total_runs: int
    warmup_runs_per_case: int = 0
    total_warmup_runs: int = 0
    successful_warmups: int = 0
    warmup_guardrail_passes: int = 0
    successful_selections: int
    selection_success_rate: float
    guardrail_passes: int
    guardrail_pass_rate: float | None
    required_evidence_recall: float | None
    selection_precision: float | None
    distractor_selection_rate: float | None
    distinct_consumer_coverage: float | None
    verification_evidence_retention: float | None
    mean_pairwise_jaccard: float | None
    p50_latency_ms: float
    p95_latency_ms: float
    input_tokens_total: int | None = None
    output_tokens_total: int | None = None
    warmups: list[SelectionRunEvaluation] = Field(default_factory=list)
    runs: list[SelectionRunEvaluation] = Field(default_factory=list)


class SelectionEvaluationComparison(BaseModel):
    corpus_version: str
    selector: str
    model: str | None = None
    runs_per_case: int
    warmup_runs_per_case: int
    aligned_runs: int
    comparable_grounded_runs: int
    exact_ordered_matches: int
    exact_ordered_match_rate: float | None
    exact_set_matches: int
    exact_set_match_rate: float | None
    mean_cross_batch_jaccard: float | None
    quality_metric_deltas: dict[str, float | None]


def load_selection_corpus(path: Path | str) -> SelectionBenchmarkCorpus:
    payload = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    return SelectionBenchmarkCorpus.model_validate(payload)


def load_selection_report(path: Path | str) -> SelectionEvaluationReport:
    text = Path(path).expanduser().resolve().read_text(encoding="utf-8-sig")
    return SelectionEvaluationReport.model_validate_json(text)


def evaluate_selector(
    corpus: SelectionBenchmarkCorpus,
    selector: EvidenceSelector,
    *,
    runs_per_case: int = 1,
    warmup_runs_per_case: int = 0,
) -> SelectionEvaluationReport:
    if runs_per_case < 1:
        raise ValueError("runs_per_case must be at least 1")
    if warmup_runs_per_case < 0:
        raise ValueError("warmup_runs_per_case cannot be negative")

    warmups: list[SelectionRunEvaluation] = []
    runs: list[SelectionRunEvaluation] = []
    selector_name: str | None = None
    model: str | None = None

    for case in corpus.cases:
        for warmup_index in range(1, warmup_runs_per_case + 1):
            result, selection = _evaluate_run(case, selector, warmup_index)
            warmups.append(result)
            if selection is not None:
                selector_name = selector_name or selection.selector
                model = model or selection.model

        for run_index in range(1, runs_per_case + 1):
            result, selection = _evaluate_run(case, selector, run_index)
            runs.append(result)
            if selection is not None:
                selector_name = selector_name or selection.selector
                model = model or selection.model

    successful_warmups = [run for run in warmups if run.selector_success]
    valid_warmups = [run for run in warmups if run.guardrail_passed]
    successful = [run for run in runs if run.selector_success]
    valid = [run for run in runs if run.guardrail_passed]
    guardrail_passes = len(valid)

    required_hits = sum(run.required_hits for run in valid)
    required_total = sum(run.required_total for run in valid)
    acceptable_hits = sum(run.acceptable_hits for run in valid)
    selected_total = sum(run.selected_total for run in valid)
    distractor_hits = sum(run.distractor_hits for run in valid)
    coverage_hits = sum(run.coverage_hits for run in valid)
    coverage_total = sum(run.coverage_total for run in valid)
    verification_hits = sum(run.verification_hits for run in valid)
    verification_total = sum(run.verification_total for run in valid)

    # Warmups are deliberately excluded from quality, latency, and token metrics.
    latencies = [run.latency_ms for run in runs]
    input_tokens = [run.input_tokens for run in successful if run.input_tokens is not None]
    output_tokens = [run.output_tokens for run in successful if run.output_tokens is not None]

    return SelectionEvaluationReport(
        corpus_version=corpus.version,
        selector=selector_name or selector.__class__.__name__,
        model=model,
        total_cases=len(corpus.cases),
        runs_per_case=runs_per_case,
        total_runs=len(runs),
        warmup_runs_per_case=warmup_runs_per_case,
        total_warmup_runs=len(warmups),
        successful_warmups=len(successful_warmups),
        warmup_guardrail_passes=len(valid_warmups),
        successful_selections=len(successful),
        selection_success_rate=_ratio(len(successful), len(runs)),
        guardrail_passes=guardrail_passes,
        guardrail_pass_rate=_optional_ratio(guardrail_passes, len(successful)),
        required_evidence_recall=_optional_ratio(required_hits, required_total),
        selection_precision=_optional_ratio(acceptable_hits, selected_total),
        distractor_selection_rate=_optional_ratio(distractor_hits, selected_total),
        distinct_consumer_coverage=_optional_ratio(coverage_hits, coverage_total),
        verification_evidence_retention=_optional_ratio(
            verification_hits,
            verification_total,
        ),
        mean_pairwise_jaccard=_mean_pairwise_jaccard(valid, runs_per_case),
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        input_tokens_total=sum(input_tokens) if input_tokens else None,
        output_tokens_total=sum(output_tokens) if output_tokens else None,
        warmups=warmups,
        runs=runs,
    )


def compare_selection_reports(
    left: SelectionEvaluationReport,
    right: SelectionEvaluationReport,
) -> SelectionEvaluationComparison:
    protocol_fields = (
        ("corpus_version", left.corpus_version, right.corpus_version),
        ("selector", left.selector, right.selector),
        ("model", left.model, right.model),
        ("total_cases", left.total_cases, right.total_cases),
        ("runs_per_case", left.runs_per_case, right.runs_per_case),
        (
            "warmup_runs_per_case",
            left.warmup_runs_per_case,
            right.warmup_runs_per_case,
        ),
    )
    mismatches = [
        f"{name}: {left_value!r} != {right_value!r}"
        for name, left_value, right_value in protocol_fields
        if left_value != right_value
    ]
    if mismatches:
        raise ValueError(
            "Selection evaluation reports use different protocols: "
            + "; ".join(mismatches)
        )

    left_runs = {(run.case_id, run.run_index): run for run in left.runs}
    right_runs = {(run.case_id, run.run_index): run for run in right.runs}
    if set(left_runs) != set(right_runs):
        raise ValueError("Selection evaluation reports have different measured run keys")

    aligned_keys = sorted(left_runs)
    grounded_pairs = [
        (left_runs[key], right_runs[key])
        for key in aligned_keys
        if left_runs[key].guardrail_passed and right_runs[key].guardrail_passed
    ]

    exact_ordered = sum(
        left_run.selected_evidence_ids == right_run.selected_evidence_ids
        for left_run, right_run in grounded_pairs
    )
    exact_sets = sum(
        set(left_run.selected_evidence_ids) == set(right_run.selected_evidence_ids)
        for left_run, right_run in grounded_pairs
    )
    jaccards = [
        _jaccard(
            set(left_run.selected_evidence_ids),
            set(right_run.selected_evidence_ids),
        )
        for left_run, right_run in grounded_pairs
    ]

    metric_names = (
        "required_evidence_recall",
        "selection_precision",
        "distractor_selection_rate",
        "distinct_consumer_coverage",
        "verification_evidence_retention",
        "mean_pairwise_jaccard",
    )
    deltas = {
        name: _optional_delta(getattr(left, name), getattr(right, name))
        for name in metric_names
    }

    return SelectionEvaluationComparison(
        corpus_version=left.corpus_version,
        selector=left.selector,
        model=left.model,
        runs_per_case=left.runs_per_case,
        warmup_runs_per_case=left.warmup_runs_per_case,
        aligned_runs=len(aligned_keys),
        comparable_grounded_runs=len(grounded_pairs),
        exact_ordered_matches=exact_ordered,
        exact_ordered_match_rate=_optional_ratio(exact_ordered, len(grounded_pairs)),
        exact_set_matches=exact_sets,
        exact_set_match_rate=_optional_ratio(exact_sets, len(grounded_pairs)),
        mean_cross_batch_jaccard=(
            sum(jaccards) / len(jaccards) if jaccards else None
        ),
        quality_metric_deltas=deltas,
    )


def _evaluate_run(
    case: SelectionBenchmarkCase,
    selector: EvidenceSelector,
    run_index: int,
) -> tuple[SelectionRunEvaluation, SynthesisSelection | None]:
    started = time.perf_counter()
    try:
        selection = selector.select(case.evidence)
    except ModelSelectionError as exc:
        return (
            SelectionRunEvaluation(
                case_id=case.id,
                run_index=run_index,
                selector_success=False,
                guardrail_passed=False,
                error=str(exc),
                latency_ms=(time.perf_counter() - started) * 1000.0,
            ),
            None,
        )
    except Exception as exc:
        return (
            SelectionRunEvaluation(
                case_id=case.id,
                run_index=run_index,
                selector_success=False,
                guardrail_passed=False,
                error=f"Selector raised {type(exc).__name__}: {exc}",
                latency_ms=(time.perf_counter() - started) * 1000.0,
            ),
            None,
        )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    try:
        validate_selection(case.evidence, selection)
    except SynthesisGuardrailError as exc:
        return (
            SelectionRunEvaluation(
                case_id=case.id,
                run_index=run_index,
                selector_success=True,
                guardrail_passed=False,
                selected_evidence_ids=selection.selected_evidence_ids,
                error=str(exc),
                latency_ms=elapsed_ms,
                input_tokens=selection.input_tokens,
                output_tokens=selection.output_tokens,
            ),
            selection,
        )

    selected = set(selection.selected_evidence_ids)
    required = set(case.required_evidence_ids)
    optional = set(case.optional_evidence_ids)
    distractor = set(case.distractor_evidence_ids)
    verification = set(case.verification_critical_ids)
    coverage_hits = sum(
        bool(selected & set(group.evidence_ids)) for group in case.coverage_groups
    )

    return (
        SelectionRunEvaluation(
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
            latency_ms=elapsed_ms,
            input_tokens=selection.input_tokens,
            output_tokens=selection.output_tokens,
        ),
        selection,
    )


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
            scores.append(_jaccard(left, right))
    if not scores:
        return None
    return sum(scores) / len(scores)


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


def _optional_delta(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return right - left


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _optional_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]
