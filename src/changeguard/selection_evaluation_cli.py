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
    SelectionEvaluationReport,
    evaluate_selector,
    load_selection_corpus,
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
        help="Number of selector runs per case. Use more than one to measure stability.",
    ),
    details: bool = typer.Option(
        False,
        "--details/--no-details",
        help="Print per-case, per-run selections and labeled outcomes.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict/--no-strict",
        help=(
            "Exit with code 1 if any selector call fails or any returned selection "
            "fails deterministic grounding guardrails. Quality metrics are reported "
            "but are not hard-gated by this flag."
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
        report = evaluate_selector(corpus_model, selector, runs_per_case=runs)
    except (OSError, ValueError, ValidationError, ModelSelectionError) as exc:
        typer.echo(f"Selector evaluation input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        _print_report(report, details=details)

    if strict and (
        report.successful_selections != report.total_runs
        or report.guardrail_passes != report.successful_selections
    ):
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


def _print_report(report: SelectionEvaluationReport, *, details: bool) -> None:
    model = f" | model={report.model}" if report.model else ""
    typer.echo(
        f"ChangeGuard V5.2 | corpus: {report.corpus_version} | "
        f"selector={report.selector}{model}"
    )
    typer.echo(
        f"cases: {report.total_cases} | runs/case: {report.runs_per_case} | "
        f"total runs: {report.total_runs}"
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
        "run-to-run stability (mean pairwise Jaccard): "
        f"{_decimal_or_na(report.mean_pairwise_jaccard)}"
    )
    typer.echo(
        "selector latency: "
        f"p50={report.p50_latency_ms:.3f} ms | p95={report.p95_latency_ms:.3f} ms"
    )
    if report.input_tokens_total is not None or report.output_tokens_total is not None:
        typer.echo(
            "provider tokens: "
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
    typer.echo("runs:")
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


def _percent(value: float) -> str:
    return f"{value * 100.0:.1f}%"


def _percent_or_na(value: float | None) -> str:
    return "N/A" if value is None else _percent(value)


def _decimal_or_na(value: float | None) -> str:
    return "N/A (use --runs >= 2)" if value is None else f"{value:.3f}"
