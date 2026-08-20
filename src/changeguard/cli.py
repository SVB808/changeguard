from __future__ import annotations

from pathlib import Path

import typer

from changeguard.git_client import GitError
from changeguard.github_client import GitHubAPIError
from changeguard.java_analyzer import JavaAnalyzerError
from changeguard.remote_scanner import scan_pull_request
from changeguard.scanner import scan

app = typer.Typer(
    help="ChangeGuard: deterministic change-impact evidence before AI reasoning."
)


def _format_endpoint(endpoint) -> str:
    params = ", ".join(endpoint.parameter_types)
    return (
        f"{endpoint.http_method} {endpoint.path} | "
        f"{endpoint.controller}#{endpoint.method_name}({params}) "
        f"-> {endpoint.return_type}"
    )


def _print_manifest(manifest, json_output: bool) -> None:
    if json_output:
        typer.echo(manifest.model_dump_json(indent=2))
        return

    typer.echo(
        f"ChangeGuard V1 | {manifest.base[:12]} -> {manifest.head[:12]} | "
        f"{manifest.changed_file_count} changed file(s)"
    )
    typer.echo(f"repository: {manifest.repo}")
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

        if file.semantic_changes:
            typer.echo("  semantic changes:")
            for semantic_change in file.semantic_changes:
                typer.echo(f"    {semantic_change.kind.value}")
                if semantic_change.before is not None:
                    typer.echo(
                        "      before: " + _format_endpoint(semantic_change.before)
                    )
                if semantic_change.after is not None:
                    typer.echo(
                        "      after:  " + _format_endpoint(semantic_change.after)
                    )

        typer.echo("")


@app.command("scan")
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

    _print_manifest(manifest, json_output)


@app.command("pr")
def scan_pr_cmd(
    repo: str = typer.Option(
        ...,
        "--repo",
        help="GitHub repository in owner/name format.",
    ),
    pr_number: int = typer.Option(
        ...,
        "--pr",
        min=1,
        help="Pull request number.",
    ),
    semantic: bool = typer.Option(
        True,
        "--semantic/--no-semantic",
        help="Run Java/Spring semantic analysis for changed Java files.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
) -> None:
    """Analyze a GitHub pull request without cloning the target repository."""
    try:
        manifest = scan_pull_request(
            repo,
            pr_number,
            semantic_analysis=semantic,
        )
    except GitHubAPIError as exc:
        typer.echo(f"GitHub error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except JavaAnalyzerError as exc:
        typer.echo(f"Java analyzer error: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    _print_manifest(manifest, json_output)


if __name__ == "__main__":
    app()
