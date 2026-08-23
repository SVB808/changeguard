from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from changeguard import __version__
from changeguard.effective_selection_evaluation import (
    EffectiveSelectionEvaluationReport,
    SelectionQualitySummary,
    evaluate_effective_selector,
)
from changeguard.model_selector import (
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    DEFAULT_OPENAI_MODEL,
    ModelSelectionError,
    OllamaEvidenceSelector,
    OpenAIEvidenceSelector,
)
from changeguard.selection_evaluation import load_selection_corpus
from changeguard.selection_evaluation_cli import DEFAULT_SELECTION_CORPUS
from changeguard.synthesis import DeterministicEvidenceSelector


def evaluate_selector_policy_cmd(
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
        help="Unscored selector runs per case before measurement.",
    ),
    details: bool = typer.Option(
        False,
        "--details/--no-details",
        help="Print raw and effective evidence IDs for every measured run.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict/--no-strict",
        help=(
            "Exit with code 1 if any provider call fails, raw selection fails grounding, "
            "or deterministic policy closure fails. Quality metrics are not hard-gated."
        ),
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
) -> None:
    """Compare raw model selection with the effective post-policy selection."""
    try:
        corpus_model = load_selection_corpus(corpus)
        selector = _create_selector(selector_name, model=model, ollama_url=ollama_url)
        report = evaluate_effective_selector(
            corpus_model,
            selector,
            runs_per_case=runs,
            warmup_runs_per_case=warmup_runs,
        )
    except (OSError, ValueError, ValidationError, ModelSelectionError) as exc:
        typer.echo(f"Effective selector evaluation input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        _print_report(report, details=details)

    warmup_failed = (
        report.total_warmup_runs > 0
        and (
            report.successful_warmups != report.total_warmup_runs
            or report.effective_warmup_guardrail_passes != report.total_warmup_runs
        )
    )
    measured_failed = (
        report.successful_selections != report.total_runs
        or report.raw_guardrail_passes != report.total_runs
        or report.effective_guardrail_passes != report.total_runs
    )
    if strict and (warmup_failed or measured_failed):
        raise typer.Exit(code=1)


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


def _print_report(report: EffectiveSelectionEvaluationReport, *, details: bool) -> None:
    model = f" | model={report.model}" if report.model else ""
    typer.echo(
        f"ChangeGuard {__version__} policy evaluation | corpus: {report.corpus_version} | "
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
            "effective grounding="
            f"{report.effective_warmup_guardrail_passes}/{report.total_warmup_runs}"
        )
    typer.echo(
        "measured grounding: "
        f"raw={report.raw_guardrail_passes}/{report.total_runs} | "
        f"effective={report.effective_guardrail_passes}/{report.total_runs}"
    )
    typer.echo("")
    typer.echo("raw selector quality:")
    _print_quality(report.raw_quality)
    typer.echo("")
    typer.echo("effective quality after deterministic decision-critical closure:")
    _print_quality(report.effective_quality)
    typer.echo("")
    typer.echo("runtime policy-mandatory retention:")
    typer.echo(
        "  raw: "
        f"{report.policy_mandatory.raw_hits}/{report.policy_mandatory.raw_total} "
        f"({_percent_or_na(report.policy_mandatory.raw_retention)})"
    )
    typer.echo(
        "  effective: "
        f"{report.policy_mandatory.effective_hits}/"
        f"{report.policy_mandatory.effective_total} "
        f"({_percent_or_na(report.policy_mandatory.effective_retention)})"
    )
    typer.echo("")
    typer.echo(
        "policy interventions: "
        f"{report.policy_intervention_runs}/{report.total_runs} run(s) | "
        f"added={report.policy_added_evidence_total} | "
        f"dropped={report.policy_dropped_evidence_total}"
    )
    typer.echo(
        "corpus-policy diagnostics: "
        f"{len(report.corpus_policy_diagnostics)} warning(s)"
    )
    for diagnostic in report.corpus_policy_diagnostics:
        ids = ", ".join(diagnostic.evidence_ids)
        typer.echo(
            f"  WARNING {diagnostic.case_id} [{diagnostic.code}] {ids}: "
            f"{diagnostic.message}"
        )
    typer.echo(
        "measured provider latency: "
        f"p50={report.p50_provider_latency_ms:.3f} ms | "
        f"p95={report.p95_provider_latency_ms:.3f} ms"
    )
    if report.input_tokens_total is not None or report.output_tokens_total is not None:
        typer.echo(
            "measured provider tokens: "
            f"input={report.input_tokens_total or 0} | "
            f"output={report.output_tokens_total or 0}"
        )
    typer.echo(
        "scope: controlled evidence-selection corpus only; effective metrics measure "
        "deterministic policy closure over supplied evidence, not production accuracy."
    )

    if not details:
        return

    typer.echo("")
    typer.echo("measured runs:")
    for pair in report.runs:
        raw_ids = ", ".join(pair.raw.selected_evidence_ids)
        effective_ids = (
            ", ".join(pair.effective.selected_evidence_ids)
            if pair.effective is not None
            else "<not available>"
        )
        typer.echo(
            f"  {pair.case_id} run={pair.run_index} | "
            f"raw_grounded={pair.raw.guardrail_passed} | "
            f"effective_grounded={bool(pair.effective and pair.effective.guardrail_passed)}"
        )
        typer.echo(f"    raw:       {raw_ids}")
        typer.echo(f"    effective: {effective_ids}")
        typer.echo(
            "    policy mandatory: "
            f"raw={pair.raw_policy_mandatory_hits}/{pair.policy_mandatory_total} | "
            f"effective={pair.effective_policy_mandatory_hits}/"
            f"{pair.policy_mandatory_total}"
        )
        if pair.policy_added_evidence_ids:
            typer.echo("    policy added: " + ", ".join(pair.policy_added_evidence_ids))
        if pair.policy_dropped_evidence_ids:
            typer.echo("    policy dropped: " + ", ".join(pair.policy_dropped_evidence_ids))
        error = pair.raw.error or (pair.effective.error if pair.effective else None)
        if error:
            typer.echo(f"    error: {error}")


def _print_quality(summary: SelectionQualitySummary) -> None:
    typer.echo(f"  valid runs: {summary.valid_runs}")
    typer.echo(
        "  required evidence recall: "
        f"{_percent_or_na(summary.required_evidence_recall)}"
    )
    typer.echo(
        "  selection precision: "
        f"{_percent_or_na(summary.selection_precision)}"
    )
    typer.echo(
        "  distractor selection rate: "
        f"{_percent_or_na(summary.distractor_selection_rate)}"
    )
    typer.echo(
        "  distinct-consumer coverage: "
        f"{_percent_or_na(summary.distinct_consumer_coverage)}"
    )
    typer.echo(
        "  verification-evidence retention: "
        f"{_percent_or_na(summary.verification_evidence_retention)}"
    )
    typer.echo(
        "  within-batch stability (mean pairwise Jaccard): "
        f"{_decimal_or_na(summary.mean_pairwise_jaccard)}"
    )


def _percent_or_na(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def _decimal_or_na(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.3f}"
