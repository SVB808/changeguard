from __future__ import annotations

from pathlib import Path

import typer

from changeguard.evaluation import EvaluationReport, evaluate_corpus, load_corpus


DEFAULT_CORPUS = (
    Path(__file__).resolve().parents[2]
    / "benchmarks"
    / "evaluation"
    / "rest-impact-v1.json"
)


def evaluate_cmd(
    corpus: Path = typer.Option(
        DEFAULT_CORPUS,
        "--corpus",
        help="Path to a labeled ChangeGuard evaluation corpus.",
        exists=True,
        dir_okay=False,
        file_okay=True,
    ),
    details: bool = typer.Option(
        False,
        "--details/--no-details",
        help="Print per-case expected versus actual outcomes.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict/--no-strict",
        help="Exit with code 1 when any disposition or verification-plan expectation mismatches.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
) -> None:
    """Evaluate deterministic impact/refinement behavior against a labeled corpus."""
    report = evaluate_corpus(load_corpus(corpus))

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        _print_report(report, details=details)

    if strict and report.exact_matches != report.total_cases:
        raise typer.Exit(code=1)


def _print_report(report: EvaluationReport, details: bool) -> None:
    typer.echo(
        f"ChangeGuard V4 | corpus: {report.corpus_version} | "
        f"{report.total_cases} case(s)"
    )
    typer.echo(
        "exact disposition + verification-plan accuracy: "
        f"{report.exact_matches}/{report.total_cases} "
        f"({_percent(report.exact_accuracy)})"
    )
    typer.echo(
        "impact detection: "
        f"TP={report.impact_detection.true_positive} "
        f"FP={report.impact_detection.false_positive} "
        f"TN={report.impact_detection.true_negative} "
        f"FN={report.impact_detection.false_negative} | "
        f"precision={report.impact_detection.precision:.3f} "
        f"recall={report.impact_detection.recall:.3f} "
        f"FPR={report.impact_detection.false_positive_rate:.3f}"
    )
    typer.echo(
        "endpoint evidence: "
        f"TP={report.endpoint_evidence.true_positive} "
        f"FP={report.endpoint_evidence.false_positive} "
        f"TN={report.endpoint_evidence.true_negative} "
        f"FN={report.endpoint_evidence.false_negative} | "
        f"precision={report.endpoint_evidence.precision:.3f} "
        f"recall={report.endpoint_evidence.recall:.3f} "
        f"FPR={report.endpoint_evidence.false_positive_rate:.3f}"
    )
    typer.echo(
        "verification-plan accuracy: "
        f"{_percent(report.verification_plan_accuracy)}"
    )
    typer.echo(
        "deterministic core latency: "
        f"p50={report.p50_analysis_ms:.3f} ms | "
        f"p95={report.p95_analysis_ms:.3f} ms"
    )
    typer.echo(
        "scope: controlled corpus metrics only; not a production accuracy or "
        "end-to-end latency claim."
    )

    if not details:
        return

    typer.echo("")
    typer.echo("cases:")
    for case in report.cases:
        status = "PASS" if case.exact_match else "FAIL"
        typer.echo(
            f"  {status} {case.id} | impact expected={case.expected_impact} "
            f"actual={case.predicted_impact} | disposition "
            f"expected={case.expected_disposition.value} "
            f"actual={case.actual_disposition.value} | verification-plan "
            f"expected={case.expected_verification_plan} "
            f"actual={case.actual_verification_plan} | {case.analysis_ms:.3f} ms"
        )
        if case.reference:
            typer.echo(f"    reference: {case.reference}")


def _percent(value: float) -> str:
    return f"{value * 100.0:.1f}%"
