from __future__ import annotations

import json
from pathlib import Path

import typer

from changeguard.git_client import GitError
from changeguard.scanner import scan

app = typer.Typer(
    help="ChangeGuard: deterministic change-impact evidence before AI reasoning."
)


@app.command()
def scan_cmd(
    repo: Path = typer.Option(
        Path("."),
        "--repo",
        help="Path to a local Git repository.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    base: str = typer.Option("HEAD~1", "--base", help="Base Git ref."),
    head: str = typer.Option("HEAD", "--head", help="Head Git ref."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
) -> None:
    try:
        manifest = scan(repo=repo, base=base, head=head)
    except GitError as exc:
        typer.echo(f"Git error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        typer.echo(manifest.model_dump_json(indent=2))
        return

    typer.echo(
        f"ChangeGuard V0 | {manifest.base} -> {manifest.head} | "
        f"{manifest.changed_file_count} changed file(s)"
    )
    typer.echo("")

    for file in manifest.files:
        typer.echo(file.path)
        typer.echo(f"  status: {file.status.value}")
        typer.echo(f"  language: {file.language}")

        if file.surfaces:
            typer.echo(
                "  surfaces: " + ", ".join(surface.value for surface in file.surfaces)
            )
        else:
            typer.echo("  surfaces: none")

        for reason in file.evidence:
            typer.echo(f"  evidence: {reason}")

        typer.echo("")


if __name__ == "__main__":
    app()
