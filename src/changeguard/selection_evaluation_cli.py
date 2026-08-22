from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from changeguard.model_selector import (
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    DEFAULT_OPENAI_MODEL,
    ModelSelectionError,
    OllamaEvidenceSelector,
    OpenAIEvidenceSelector,
)
from changeguard.selection_evaluation import (
    SelectionEvaluationComparison,
    SelectionEvaluationReport,
    compare_selection_reports,
    evaluate_selector,
    load_selection_corpus,
    load_selection_report,
)
from changeguard.synthesis import DeterministicEvidenceSelector


DEFAULT_SELECTION_CORPUS = (
    Path(__file__).resolve().parents[2]
    / "benchmarks"
    / "evaluation"
    / "synthesis-selection-v1.json"
)


def evaluate_selector_cmd(
    corpus: Path = typer.Option(
        DEFAULT_SELECTION_CORPUS,
        "--corpus",
        help="Path to a labeled ChangeGuard evidence-selection corpus.",
        exists=True,
        dir_okay=False,
        file_okay=True,
    ),
    selector_name: str = typer.Option(
        "deterministic",
        "--selector",
        help="Evidence selector to evaluate: deterministic, openai, or ollama.",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help=(
            "Model override for a model-backed selector. Defaults to "
            f"{DEFAULT_OPENAI_MODEL} for OpenAI or {DEFAULT_OLLAMA_MODEL} for Ollama."
        ),
    ),
    ollama_url: str = typer.Option(
        DEFAULT_OLLAMA_URL,
        "--ollama-url",
        help="Ollama API base URL used only with --selector ollama.",
    ),
    runs: int = typer.Option(
        1,
        "--runs",
        min=1,
        max=20,
        help="Number of measured selector runs per case.",
    ),
    warmup_runs: int = typer.Option(
        0,
        "--warmup-runs",
        min=0,
        max=20,
        help=(
            "Unscored selector runs per case before measurement. Use this to measure "
            "steady-state behavior separately from cold/first-call behavior."
        ),
    ),
    details: bool = typer.Option(
        False,
        "--details/--no-details",
        help="Print per-case, per-run measured selections and labeled outcomes.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict/--no-strict",
        help=(
            "Exit with code 1 if any warmup/measured selector call fails or any returned "
            "selection fails deterministic grounding guardrails. Quality metrics are "
            "reported but are not hard-gated by this flag."
        ),
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
) -> None:
    """Evaluate evidence-selection quality separately from deterministic impact analysis."""
    try:
        corpus_model = load_selection_corpus(corpus)
        selector = _create_selector(selector_name, model=model, ollama_url=ollama_url)
        report = evaluate_selector(
            corpus_model,
            selector,
            runs_per_case=runs,
            warmup_runs_per_case=warmup_runs,
        )
    except (OSError, ValueError, ValidationError, ModelSelectionError) as exc:
        typer.echo(f"Selector evaluation input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        _print_report(report, details=details)

    warmup_failed = (
        report.total_warmup_runs > 0
        and (
            report.successful_warmups != report.total_warmup_runs
            or report.warmup_guardrail_passes != report.successful_warmups
        )
    )
    measured_failed = (
        report.successful_selections != report.total_runs
        or report.guardrail_passes != report.successful_selections
    )
    if strict and (warmup_failed or measured_failed):
        raise typer.Exit(code=1)


def compare_selector_evals_cmd(
    left: Path = typer.Argument(
        ...,
        help="First machine-readable evaluate-selector JSON report.",
        exists=True,
        dir_okay=False,
        file_okay=True,
    ),
    right: Path = typer.Argument(
        ...,
        help="Second machine-readable evaluate-selector JSON report.",
        exists=True,
        dir_okay=False,
        file_okay=True,
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable comparison JSON.",
    ),
) -> None:
    """Compare independent selector-evaluation batches for reproducibility."""
    try:
        left_report = load_selection_report(left)
        right_report = load_selection_report(right)
        comparison = compare_selection_reports(left_report, right_report)
    except (OSError, ValueError, ValidationError) as exc:
        typer.echo(f"Selector comparison input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(comparison.model_dump_json(indent=2))
        return

    _print_comparison(comparison, left=left, right=right)


def _create_selector(selector_name: str, *, model: str | None, ollama_url: str):
    normalized = selector_name.strip().lower()
    if normalized == "deterministic":
        return DeterministicEvidenceSelector()
    if normalized == "openai":
        return OpenAIEvidenceSelector(model=model or DEFAULT_OPENAI_MODEL)
    if normalized == "ollama":
        return OllamaEvidenceSelector(
            model=model or DEFAULT_OLLAMA_MODEL,
            base_url=ollama_url,
        )
    raise ValueError(
        f"Unknown selector {selector_name!r}; use deterministic, openai, or ollama."
    )


def _print_report(report: SelectionEvaluationReport, *, details: bool) -> None:
    model = f" | model={report.model}" if report.model else ""
    typer.echo(
        f"ChangeGuard V5.2.1 | corpus: {report.corpus_version} | "
        f"selector={report.selector}{model}"
    )
    mode = "cold/normal-call"
    if report.warmup_runs_per_case:
        mode = (
            f"steady-state after {report.warmup_runs_per_case} unscored "
            "warmup run(s) per case"
        )
    typer.echo(f"measurement mode: {mode}")
    typer.echo(
        f"cases: {report.total_cases} | measured runs/case: {report.runs_per_case} | "
        f"measured total: {report.total_runs}"
    )
    if report.total_warmup_runs:
        typer.echo(
            "warmups: "
            f"selector success={report.successful_warmups}/{report.total_warmup_runs} | "
            "grounding="
            f"{report.warmup_guardrail_passes}/{report.successful_warmups}"
        )
    typer.echo(
        "selector success: "
        f"{report.successful_selections}/{report.total_runs} "
        f"({_percent(report.selection_success_rate)})"
    )
    typer.echo(
        "grounding guardrail pass: "
        f"{report.guardrail_passes}/{report.successful_selections} returned selection(s) "
        f"({_percent_or_na(report.guardrail_pass_rate)})"
    )
    typer.echo(
        "required evidence recall: "
        f"{_percent_or_na(report.required_evidence_recall)}"
    )
    typer.echo(
        "selection precision: "
        f"{_percent_or_na(report.selection_precision)}"
    )
    typer.echo(
        "distractor selection rate: "
        f"{_percent_or_na(report.distractor_selection_rate)}"
    )
    typer.echo(
        "distinct-consumer coverage: "
        f"{_percent_or_na(report.distinct_consumer_coverage)}"
    )
    typer.echo(
        "verification-evidence retention: "
        f"{_percent_or_na(report.verification_evidence_retention)}"
    )
    typer.echo(
        "within-batch stability (mean pairwise Jaccard): "
        f"{_decimal_or_na(report.mean_pairwise_jaccard)}"
    )
    typer.echo(
        "measured selector latency: "
        f"p50={report.p50_latency_ms:.3f} ms | p95={report.p95_latency_ms:.3f} ms"
    )
    if report.input_tokens_total is not None or report.output_tokens_total is not None:
        typer.echo(
            "measured provider tokens: "
            f"input={report.input_tokens_total or 0} | "
            f"output={report.output_tokens_total or 0}"
        )
    typer.echo(
        "scope: controlled evidence-selection corpus only; metrics do not measure "
        "end-to-end change-impact accuracy or production reliability."
    )

    if not details:
        return

    typer.echo("")
    typer.echo("measured runs:")
    for run in report.runs:
        if not run.selector_success:
            typer.echo(
                f"  ERROR {run.case_id} run={run.run_index} | "
                f"{run.latency_ms:.3f} ms | {run.error}"
            )
            continue
        if not run.guardrail_passed:
            typer.echo(
                f"  GUARDRAIL_FAIL {run.case_id} run={run.run_index} | "
                f"selected={run.selected_evidence_ids} | {run.error}"
            )
            continue

        typer.echo(
            f"  PASS {run.case_id} run={run.run_index} | "
            f"required={run.required_hits}/{run.required_total} | "
            f"acceptable={run.acceptable_hits}/{run.selected_total} | "
            f"distractors={run.distractor_hits} | "
            f"coverage={run.coverage_hits}/{run.coverage_total} | "
            f"verification={run.verification_hits}/{run.verification_total} | "
            f"{run.latency_ms:.3f} ms"
        )
        typer.echo("    selected: " + ", ".join(run.selected_evidence_ids))


def _print_comparison(
    comparison: SelectionEvaluationComparison,
    *,
    left: Path,
    right: Path,
) -> None:
    model = f" | model={comparison.model}" if comparison.model else ""
    typer.echo(
        f"ChangeGuard V5.2.1 selector reproducibility | "
        f"corpus={comparison.corpus_version} | selector={comparison.selector}{model}"
    )
    typer.echo(f"left:  {left}")
    typer.echo(f"right: {right}")
    typer.echo(
        f"protocol: warmups/case={comparison.warmup_runs_per_case} | "
        f"measured runs/case={comparison.runs_per_case}"
    )
    typer.echo(
        f"aligned measured runs: {comparison.aligned_runs} | "
        f"comparable grounded pairs: {comparison.comparable_grounded_runs}"
    )
    typer.echo(
        "exact ordered selection match: "
        f"{comparison.exact_ordered_matches}/{comparison.comparable_grounded_runs} "
        f"({_percent_or_na(comparison.exact_ordered_match_rate)})"
    )
    typer.echo(
        "exact evidence-set match: "
        f"{comparison.exact_set_matches}/{comparison.comparable_grounded_runs} "
        f"({_percent_or_na(comparison.exact_set_match_rate)})"
    )
    typer.echo(
        "mean cross-batch Jaccard: "
        f"{_decimal_or_na(comparison.mean_cross_batch_jaccard)}"
    )
    typer.echo("quality metric deltas (right - left):")
    for name, value in comparison.quality_metric_deltas.items():
        typer.echo(f"  {name}: {_signed_percent_or_na(value)}")


def _percent(value: float) -> str:
    return f"{value * 100.0:.1f}%"


def _percent_or_na(value: float | None) -> str:
    return "N/A" if value is None else _percent(value)


def _signed_percent_or_na(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100.0:+.1f} pp"


def _decimal_or_na(value: float | None) -> str:
    return "N/A (insufficient comparable runs)" if value is None else f"{value:.3f}"
