from __future__ import annotations

from pathlib import Path

import typer

from changeguard.dependency_graph import ServiceDependencyGraphBuilder
from changeguard.git_client import GitError
from changeguard.github_client import GitHubAPIError, GitHubClient
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


def _format_security_rule(rule) -> str:
    selector = rule.selector
    if rule.patterns:
        selector += "(" + ", ".join(rule.patterns) + ")"
    return f"{selector} -> {rule.action}"


def _print_security_policy(policy, prefix: str) -> None:
    typer.echo(f"      {prefix}: {policy.component}#{policy.method_name}")
    for rule in policy.authorization_rules:
        typer.echo(f"        authorization: {_format_security_rule(rule)}")
    if policy.disabled_features:
        typer.echo("        disabled: " + ", ".join(policy.disabled_features))


def _print_dependency_graph(graph, json_output: bool) -> None:
    if json_output:
        typer.echo(graph.model_dump_json(indent=2))
        return

    typer.echo(
        f"services: {len(graph.nodes)} | dependency edges: {len(graph.edges)} | "
        f"explicit consumer calls: {len(graph.consumer_calls)}"
    )
    typer.echo("")
    for edge in graph.edges:
        typer.echo(f"{edge.source} -> {edge.target} [{edge.kind.value}]")
        typer.echo(f"  evidence: {edge.evidence_path} | {edge.evidence}")

    if graph.consumer_calls:
        typer.echo("")
        typer.echo("explicit consumer calls:")
        for call in graph.consumer_calls:
            typer.echo(
                f"{call.consumer_service} -> {call.target_service} "
                f"{call.http_method} {call.path}"
            )
            typer.echo(f"  evidence: {call.evidence_path}")


def _print_candidate(candidate, suppressed: bool = False) -> None:
    typer.echo(f"  {candidate.kind.value}")
    typer.echo(
        f"    provider: {candidate.provider_service} | "
        f"consumer: {candidate.consumer_service}"
    )
    typer.echo(f"    changed file: {candidate.changed_file}")
    typer.echo(f"    trigger: {candidate.trigger_kind.value}")
    if candidate.before is not None:
        typer.echo("    before: " + _format_endpoint(candidate.before))
    if candidate.after is not None:
        typer.echo("    after:  " + _format_endpoint(candidate.after))
    typer.echo(f"    match level: {candidate.match_level.value}")
    typer.echo(f"    reason: {candidate.reason}")
    for edge in candidate.dependency_evidence:
        typer.echo(
            f"    dependency evidence: [{edge.kind.value}] "
            f"{edge.evidence_path} | {edge.evidence}"
        )
    for call in candidate.consumer_call_evidence:
        typer.echo(
            f"    consumer call: {call.http_method} {call.path} | "
            f"{call.evidence_path}"
        )
    if suppressed and candidate.suppression_reason:
        typer.echo(f"    suppression: {candidate.suppression_reason}")


def _print_impact_candidates(manifest) -> None:
    typer.echo(f"impact candidates: {manifest.impact_candidate_count}")
    if not manifest.impact_candidates:
        typer.echo("  none")
    else:
        for candidate in manifest.impact_candidates:
            _print_candidate(candidate)

    typer.echo(
        f"suppressed service-level candidates: "
        f"{manifest.suppressed_impact_candidate_count}"
    )
    if not manifest.suppressed_impact_candidates:
        typer.echo("  none")
    else:
        for candidate in manifest.suppressed_impact_candidates:
            _print_candidate(candidate, suppressed=True)


def _print_manifest(manifest, json_output: bool) -> None:
    if json_output:
        typer.echo(manifest.model_dump_json(indent=2))
        return

    if manifest.impact_analysis_enabled:
        version = "V2.2"
    elif manifest.dependency_graph is not None:
        version = "V2"
    else:
        version = "V1"

    typer.echo(
        f"ChangeGuard {version} | {manifest.base[:12]} -> {manifest.head[:12]} | "
        f"{manifest.changed_file_count} changed file(s)"
    )
    typer.echo(f"repository: {manifest.repo}")
    if manifest.dependency_graph is not None:
        typer.echo(
            "dependency graph: "
            f"{len(manifest.dependency_graph.nodes)} service(s), "
            f"{len(manifest.dependency_graph.edges)} edge(s), "
            f"{len(manifest.dependency_graph.consumer_calls)} explicit call(s)"
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

        if file.service is not None:
            typer.echo(f"  service: {file.service}")
            if file.direct_dependents:
                typer.echo(
                    "  direct dependents: " + ", ".join(file.direct_dependents)
                )
            else:
                typer.echo("  direct dependents: none")

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

        if file.security_changes:
            typer.echo("  security semantic changes:")
            for security_change in file.security_changes:
                typer.echo(f"    {security_change.kind.value}")
                if security_change.before is not None:
                    _print_security_policy(security_change.before, "before")
                if security_change.after is not None:
                    _print_security_policy(security_change.after, "after ")

        typer.echo("")

    if manifest.impact_analysis_enabled:
        _print_impact_candidates(manifest)
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


@app.command("graph")
def graph_cmd(
    repo: str = typer.Option(
        ...,
        "--repo",
        help="GitHub repository in owner/name format.",
    ),
    ref: str = typer.Option(
        "main",
        "--ref",
        help="Git ref used to build the repository dependency snapshot.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
) -> None:
    """Build deterministic service dependency and HTTP call-site evidence."""
    try:
        graph = ServiceDependencyGraphBuilder(client=GitHubClient()).build(repo, ref)
    except GitHubAPIError as exc:
        typer.echo(f"GitHub error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    _print_dependency_graph(graph, json_output)


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
    dependencies: bool = typer.Option(
        False,
        "--dependencies/--no-dependencies",
        help="Build a repository service dependency graph and attach direct dependents.",
    ),
    impacts: bool = typer.Option(
        False,
        "--impacts/--no-impacts",
        help=(
            "Generate impact candidates and refine them with explicit consumer HTTP "
            "method+route evidence. Implies semantic and dependency analysis."
        ),
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
            dependency_analysis=dependencies,
            impact_analysis=impacts,
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
