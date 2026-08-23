from __future__ import annotations

import typer

from changeguard.model_selector import (
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    DEFAULT_OPENAI_MODEL,
    ModelSelectionError,
    OllamaEvidenceSelector,
    OpenAIEvidenceSelector,
)
from changeguard.release_evaluation import ReleaseEvaluationReport, evaluate_release_candidate
from changeguard.synthesis import DeterministicEvidenceSelector


def evaluate_release_cmd(
    selector_name: str = typer.Option(
        "deterministic",
        "--selector",
        help="Runtime-shaped synthesis selector: deterministic, openai, or ollama.",
    ),
    model: str | None = typer.Option(None, "--model", help="Optional model override."),
    ollama_url: str = typer.Option(
        DEFAULT_OLLAMA_URL,
        "--ollama-url",
        help="Ollama API base URL used only with --selector ollama.",
    ),
    runs: int = typer.Option(1, "--runs", min=1, max=20),
    warmup_runs: int = typer.Option(0, "--warmup-runs", min=0, max=20),
    strict: bool = typer.Option(
        False,
        "--strict/--no-strict",
        help="Exit 1 unless every release-candidate gate passes.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Run ChangeGuard's deterministic and runtime-shaped V1 release gates together."""
    try:
        selector = _selector(selector_name, model=model, ollama_url=ollama_url)
        report = evaluate_release_candidate(
            selector,
            runs_per_case=runs,
            warmup_runs_per_case=warmup_runs,
        )
    except (ValueError, ModelSelectionError) as exc:
        typer.echo(f"Release evaluation input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        _print_release_report(report)

    if strict and not report.release_gate_passed:
        raise typer.Exit(code=1)


def _selector(selector_name: str, *, model: str | None, ollama_url: str):
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


def _print_release_report(report: ReleaseEvaluationReport) -> None:
    impact = report.deterministic_impact
    selection = report.runtime_selection
    mandatory = selection.policy_mandatory

    typer.echo(f"ChangeGuard {report.release_candidate} release evaluation")
    typer.echo("")
    typer.echo("deterministic impact gate:")
    typer.echo(
        f"  corpus: {impact.corpus_version} | exact: "
        f"{impact.exact_matches}/{impact.total_cases} "
        f"({impact.exact_accuracy * 100:.1f}%)"
    )
    typer.echo(
        "  impact precision/recall: "
        f"{impact.impact_detection.precision:.3f}/{impact.impact_detection.recall:.3f}"
    )
    typer.echo(
        "  endpoint precision/recall: "
        f"{impact.endpoint_evidence.precision:.3f}/{impact.endpoint_evidence.recall:.3f}"
    )

    typer.echo("")
    typer.echo("runtime-shaped synthesis gate:")
    typer.echo(
        f"  corpus: {selection.corpus_version} | selector={selection.selector}" +
        (f" | model={selection.model}" if selection.model else "")
    )
    typer.echo(
        f"  grounding: raw={selection.raw_guardrail_passes}/{selection.total_runs} | "
        f"effective={selection.effective_guardrail_passes}/{selection.total_runs}"
    )
    typer.echo(
        "  required recall: "
        f"raw={_percent(selection.raw_quality.required_evidence_recall)} | "
        f"effective={_percent(selection.effective_quality.required_evidence_recall)}"
    )
    typer.echo(
        "  consumer coverage: "
        f"raw={_percent(selection.raw_quality.distinct_consumer_coverage)} | "
        f"effective={_percent(selection.effective_quality.distinct_consumer_coverage)}"
    )
    typer.echo(
        "  verification retention: "
        f"raw={_percent(selection.raw_quality.verification_evidence_retention)} | "
        f"effective={_percent(selection.effective_quality.verification_evidence_retention)}"
    )
    typer.echo(
        "  runtime policy-mandatory retention: "
        f"raw={mandatory.raw_hits}/{mandatory.raw_total} "
        f"({_percent(mandatory.raw_retention)}) | "
        f"effective={mandatory.effective_hits}/{mandatory.effective_total} "
        f"({_percent(mandatory.effective_retention)})"
    )
    typer.echo(
        f"  corpus-policy diagnostics: {len(selection.corpus_policy_diagnostics)}"
    )

    typer.echo("")
    typer.echo("release gates:")
    typer.echo(f"  deterministic impact: {_status(report.deterministic_gate_passed)}")
    typer.echo(f"  selector grounding: {_status(report.grounding_gate_passed)}")
    typer.echo(
        f"  policy-mandatory retention: {_status(report.policy_mandatory_gate_passed)}"
    )
    typer.echo(f"  runtime corpus semantics: {_status(report.corpus_policy_gate_passed)}")
    typer.echo(f"  overall: {_status(report.release_gate_passed)}")
    typer.echo("")
    typer.echo(
        "scope: controlled corpora and runtime-shaped evidence fixtures only; this is "
        "not a production-accuracy claim."
    )


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def _status(value: bool) -> str:
    return "PASS" if value else "FAIL"
