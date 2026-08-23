from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError

from changeguard.models import ChangeManifest, VerificationStatus
from changeguard.verification import DEFAULT_TIMEOUT_SECONDS, execute_verification_plan


def verify_plan_cmd(
    manifest_path: Path = typer.Option(
        ...,
        "--manifest",
        help="ChangeManifest JSON containing a revision-bound verification plan.",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    repo: Path = typer.Option(
        ...,
        "--repo",
        help="Local checked-out repository workspace. Project test code may execute.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    plan_index: int = typer.Option(
        0,
        "--plan-index",
        min=0,
        help="Zero-based verification plan index from the manifest.",
    ),
    timeout_seconds: int = typer.Option(
        DEFAULT_TIMEOUT_SECONDS,
        "--timeout",
        min=1,
        help="Maximum verification runtime in seconds.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit VerificationResult JSON."),
) -> None:
    """Explicitly execute one manifest plan only at the analyzed Git revision."""
    try:
        manifest = ChangeManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8-sig")
        )
    except (OSError, ValidationError) as exc:
        typer.echo(f"Verification manifest input error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if plan_index >= len(manifest.verification_plans):
        typer.echo(
            f"Verification plan index {plan_index} is out of range; manifest has "
            f"{len(manifest.verification_plans)} plan(s).",
            err=True,
        )
        raise typer.Exit(code=2)

    plan = manifest.verification_plans[plan_index]
    if plan.expected_head is None:
        typer.echo(
            "Verification plan is not revision-bound. Re-analyze the PR with the current "
            "ChangeGuard version before executing project code.",
            err=True,
        )
        raise typer.Exit(code=2)

    result = execute_verification_plan(
        plan,
        repo,
        timeout_seconds=timeout_seconds,
    )

    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        typer.echo(f"verification status: {result.status.value}")
        typer.echo(f"expected HEAD: {plan.expected_head}")
        typer.echo("command: " + " ".join(plan.command))
        typer.echo(f"workspace: {repo.resolve()}")
        if result.exit_code is not None:
            typer.echo(f"exit code: {result.exit_code}")
        if result.duration_seconds is not None:
            typer.echo(f"duration: {result.duration_seconds:.2f}s")
        if result.error:
            typer.echo(f"error: {result.error}")
        if result.stdout_tail:
            typer.echo("stdout tail:")
            typer.echo(result.stdout_tail)
        if result.stderr_tail:
            typer.echo("stderr tail:")
            typer.echo(result.stderr_tail)

    if result.status == VerificationStatus.FAILED:
        raise typer.Exit(code=1)
    if result.status == VerificationStatus.ERROR:
        raise typer.Exit(code=2)
