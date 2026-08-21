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
from changeguard.models import ChangeManifest, VerificationResult
from changeguard.synthesis import SynthesisGuardrailError, synthesize_manifest


def _read_json_text(path: Path) -> str:
    """Read UTF-8 JSON while tolerating a leading BOM from Windows PowerShell."""
    return path.read_text(encoding="utf-8-sig")


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
    selector_name: str = typer.Option(
        "deterministic",
        "--selector",
        help="Evidence selector: deterministic, openai, or ollama.",
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
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable synthesis JSON.",
    ),
) -> None:
    """Synthesize only evidence already produced by ChangeGuard."""
    try:
        manifest = ChangeManifest.model_validate_json(_read_json_text(manifest_path))
        results = [
            VerificationResult.model_validate_json(_read_json_text(path))
            for path in verification_result
        ]

        normalized_selector = selector_name.strip().lower()
        if normalized_selector == "deterministic":
            selector = None
        elif normalized_selector == "openai":
            selector = OpenAIEvidenceSelector(model=model or DEFAULT_OPENAI_MODEL)
        elif normalized_selector == "ollama":
            selector = OllamaEvidenceSelector(
                model=model or DEFAULT_OLLAMA_MODEL,
                base_url=ollama_url,
            )
        else:
            raise SynthesisGuardrailError(
                f"Unknown synthesis selector {selector_name!r}; use deterministic, "
                "openai, or ollama."
            )

        report = synthesize_manifest(manifest, results, selector=selector)
    except (
        OSError,
        ValidationError,
        SynthesisGuardrailError,
        ModelSelectionError,
    ) as exc:
        typer.echo(f"Synthesis input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
        return

    version = "V5.1" if report.selector != "deterministic" else "V5.0"
    typer.echo(
        f"ChangeGuard {version} synthesis | {report.repo} | "
        f"{report.base[:12]} -> {report.head[:12]}"
    )
    selector_line = f"selector: {report.selector}"
    if report.model:
        selector_line += f" | model: {report.model}"
    if report.input_tokens is not None or report.output_tokens is not None:
        selector_line += (
            f" | tokens: input={report.input_tokens or 0} "
            f"output={report.output_tokens or 0}"
        )
    typer.echo(selector_line)
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
