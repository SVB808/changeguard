from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from changeguard.models import ChangeManifest, VerificationResult
from changeguard.synthesis import SynthesisGuardrailError, synthesize_manifest


def synthesize_cmd(
    manifest_path: Path = typer.Option(
        ...,
        "--manifest",
        help="ChangeGuard ChangeManifest JSON produced by deterministic analysis.",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    verification_result: list[Path] = typer.Option(
        [],
        "--verification-result",
        help="Optional VerificationResult JSON. Repeat for multiple explicit local runs.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable synthesis JSON.",
    ),
) -> None:
    """Synthesize only evidence already produced by ChangeGuard."""
    try:
        manifest = ChangeManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        results = [
            VerificationResult.model_validate_json(path.read_text(encoding="utf-8"))
            for path in verification_result
        ]
        report = synthesize_manifest(manifest, results)
    except (OSError, ValidationError, SynthesisGuardrailError) as exc:
        typer.echo(f"Synthesis input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
        return

    typer.echo(
        f"ChangeGuard V5.0 synthesis | {report.repo} | "
        f"{report.base[:12]} -> {report.head[:12]}"
    )
    typer.echo(f"headline: {report.headline}")
    typer.echo(
        f"selected evidence: {len(report.evidence)} | "
        f"omitted: {report.omitted_evidence_count}"
    )
    typer.echo("")
    typer.echo("evidence:")
    if not report.evidence:
        typer.echo("  none")
    for item in report.evidence:
        typer.echo(f"  [{item.tier.value}/{item.category.value}] {item.statement}")
        for path in item.source_paths:
            typer.echo(f"    source: {path}")

    typer.echo("")
    typer.echo("caveats:")
    for caveat in report.caveats:
        typer.echo(f"  - {caveat}")
