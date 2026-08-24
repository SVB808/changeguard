from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import typer

from changeguard.models import ServiceDependencyGraph
from changeguard.runtime_contracts import RuntimeObservation, parse_runtime_payload
from changeguard.runtime_intelligence import evaluate_removal_gate
from changeguard.runtime_store import RuntimeStore


runtime_app = typer.Typer(
    help="Reconcile static service dependencies with runtime HTTP telemetry."
)

DEFAULT_RUNTIME_DB = Path(".changeguard/runtime.db")


def _parse_datetime(value: str | None, option_name: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise typer.BadParameter(
            f"{option_name} must be ISO-8601, for example 2026-08-24T10:30:00+00:00"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_graphs(paths: list[Path]) -> list[ServiceDependencyGraph]:
    graphs: list[ServiceDependencyGraph] = []
    for path in paths:
        try:
            graphs.append(
                ServiceDependencyGraph.model_validate_json(
                    path.read_text(encoding="utf-8-sig")
                )
            )
        except (OSError, ValueError) as exc:
            raise typer.BadParameter(f"could not load graph {path}: {exc}") from exc
    return graphs


@runtime_app.command("ingest")
def ingest_runtime_cmd(
    file: Path = typer.Option(
        ...,
        "--file",
        exists=True,
        dir_okay=False,
        help="OTLP JSON or normalized ChangeGuard runtime-observation JSON.",
    ),
    db: Path = typer.Option(
        DEFAULT_RUNTIME_DB,
        "--db",
        help="Local SQLite runtime evidence store.",
    ),
    source: str = typer.Option("otel", "--source", help="Telemetry source label."),
    coverage_start: str | None = typer.Option(
        None,
        "--coverage-start",
        help="Optional ISO-8601 start of telemetry coverage represented by this import.",
    ),
    coverage_end: str | None = typer.Option(
        None,
        "--coverage-end",
        help="Optional ISO-8601 end of telemetry coverage represented by this import.",
    ),
) -> None:
    """Ingest runtime HTTP observations without sending telemetry to a model."""
    try:
        payload = json.loads(file.read_text(encoding="utf-8-sig"))
        observations = parse_runtime_payload(payload, source=source)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        typer.echo(f"runtime ingest error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    explicit_start = _parse_datetime(coverage_start, "--coverage-start")
    explicit_end = _parse_datetime(coverage_end, "--coverage-end")
    if (explicit_start is None) != (explicit_end is None):
        raise typer.BadParameter(
            "--coverage-start and --coverage-end must be supplied together"
        )

    store = RuntimeStore(db)
    inserted, skipped = store.ingest(observations)

    if explicit_start is not None and explicit_end is not None:
        try:
            store.record_coverage(explicit_start, explicit_end, source)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    elif observations:
        store.record_coverage(
            min(item.observed_at for item in observations),
            max(item.observed_at for item in observations),
            source,
        )

    typer.echo(
        f"runtime ingest: inserted={inserted} skipped_duplicate={skipped} "
        f"parsed={len(observations)} db={db}"
    )


@runtime_app.command("observe")
def observe_runtime_cmd(
    consumer: str = typer.Option(..., "--consumer"),
    provider: str = typer.Option(..., "--provider"),
    method: str = typer.Option(..., "--method"),
    path: str = typer.Option(..., "--path"),
    observed_at: str = typer.Option(..., "--at", help="ISO-8601 observation timestamp."),
    count: int = typer.Option(1, "--count", min=1),
    consumer_version: str | None = typer.Option(None, "--consumer-version"),
    db: Path = typer.Option(DEFAULT_RUNTIME_DB, "--db"),
) -> None:
    """Record one normalized observation for demos or non-OTel adapters."""
    timestamp = _parse_datetime(observed_at, "--at")
    assert timestamp is not None
    observation = RuntimeObservation(
        observed_at=timestamp,
        consumer_service=consumer,
        provider_service=provider,
        http_method=method,
        path=path,
        request_count=count,
        consumer_version=consumer_version,
        source="manual",
    )
    store = RuntimeStore(db)
    inserted, skipped = store.ingest([observation])
    typer.echo(f"runtime observation: inserted={inserted} skipped_duplicate={skipped}")


@runtime_app.command("coverage")
def record_coverage_cmd(
    start: str = typer.Option(..., "--start", help="ISO-8601 coverage start."),
    end: str = typer.Option(..., "--end", help="ISO-8601 coverage end."),
    source: str = typer.Option("manual", "--source"),
    db: Path = typer.Option(DEFAULT_RUNTIME_DB, "--db"),
) -> None:
    """Record a telemetry coverage interval, including zero-traffic periods."""
    start_at = _parse_datetime(start, "--start")
    end_at = _parse_datetime(end, "--end")
    assert start_at is not None and end_at is not None
    try:
        RuntimeStore(db).record_coverage(start_at, end_at, source)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        f"telemetry coverage recorded: {start_at.isoformat()} -> {end_at.isoformat()}"
    )


@runtime_app.command("removal-gate")
def removal_gate_cmd(
    provider: str = typer.Option(..., "--provider", help="Provider service identity."),
    method: str = typer.Option(..., "--method", help="HTTP method."),
    path: str = typer.Option(..., "--path", help="Provider route template."),
    graph: list[Path] = typer.Option(
        [],
        "--graph",
        exists=True,
        dir_okay=False,
        help="Repeatable service-graph JSON exported by `changeguard graph --json`.",
    ),
    db: Path = typer.Option(DEFAULT_RUNTIME_DB, "--db"),
    quiet_days: int = typer.Option(7, "--quiet-days", min=1),
    as_of: str | None = typer.Option(
        None,
        "--as-of",
        help="Optional ISO-8601 decision time. Defaults to latest telemetry coverage end.",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Decide whether a contract is blocked, under-observed, or a removal candidate."""
    graphs = _load_graphs(graph)
    report = evaluate_removal_gate(
        store=RuntimeStore(db),
        graphs=graphs,
        provider_service=provider,
        http_method=method,
        path=path,
        quiet_window_days=quiet_days,
        as_of=_parse_datetime(as_of, "--as-of"),
    )

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
        return

    typer.echo(f"contract: {report.provider_service} {report.http_method} {report.path}")
    typer.echo(f"decision: {report.status.value}")
    typer.echo(
        f"quiet window: {report.quiet_window_days} day(s) | "
        f"telemetry sufficient: {report.telemetry_coverage_sufficient}"
    )
    if report.telemetry_coverage_start and report.telemetry_coverage_end:
        typer.echo(
            "telemetry coverage: "
            f"{report.telemetry_coverage_start.isoformat()} -> "
            f"{report.telemetry_coverage_end.isoformat()}"
        )
    else:
        typer.echo("telemetry coverage: none")

    typer.echo(
        f"runtime requests: {report.runtime_request_count} | "
        f"static consumers: {report.static_reference_count}"
    )
    if report.runtime_last_seen:
        typer.echo(f"last runtime request: {report.runtime_last_seen.isoformat()}")

    if report.consumers:
        typer.echo("consumers:")
        for consumer in report.consumers:
            typer.echo(
                f"  {consumer.consumer_service}: {consumer.classification.value} | "
                f"runtime={consumer.runtime_request_count} | "
                f"static={consumer.static_reference}"
            )
            if consumer.runtime_versions:
                typer.echo("    versions: " + ", ".join(consumer.runtime_versions))
            for evidence_path in consumer.static_evidence_paths:
                typer.echo(f"    static evidence: {evidence_path}")

    if report.blockers:
        typer.echo("blockers:")
        for blocker in report.blockers:
            typer.echo(f"  - {blocker}")

    typer.echo("scope:")
    for caveat in report.caveats:
        typer.echo(f"  - {caveat}")
