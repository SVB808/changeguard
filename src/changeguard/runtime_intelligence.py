from __future__ import annotations

from datetime import datetime, timedelta, timezone

from changeguard.models import ServiceDependencyGraph
from changeguard.runtime_contracts import (
    ContractRemovalReport,
    RemovalGateStatus,
    RuntimeConsumerClassification,
    RuntimeConsumerSummary,
    static_consumers_for_contract,
)
from changeguard.runtime_store import RuntimeStore


def evaluate_removal_gate(
    store: RuntimeStore,
    graphs: list[ServiceDependencyGraph],
    provider_service: str,
    http_method: str,
    path: str,
    quiet_window_days: int = 7,
    as_of: datetime | None = None,
) -> ContractRemovalReport:
    if quiet_window_days < 1:
        raise ValueError("quiet_window_days must be at least 1")

    coverage = store.latest_contiguous_coverage()
    if as_of is None:
        as_of = coverage[1] if coverage is not None else datetime.now(timezone.utc)
    elif as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    else:
        as_of = as_of.astimezone(timezone.utc)

    window_start = as_of - timedelta(days=quiet_window_days)
    observations = store.contract_observations(
        provider_service=provider_service,
        http_method=http_method,
        path=path,
        start=window_start,
        end=as_of,
    )
    static = static_consumers_for_contract(
        graphs=graphs,
        provider_service=provider_service,
        http_method=http_method,
        path=path,
    )

    runtime_by_consumer: dict[str, list] = {}
    for observation in observations:
        runtime_by_consumer.setdefault(observation.consumer_service, []).append(observation)

    consumers: list[RuntimeConsumerSummary] = []
    for consumer in sorted(set(static) | set(runtime_by_consumer)):
        static_reference = consumer in static
        runtime_items = runtime_by_consumer.get(consumer, [])
        if static_reference and runtime_items:
            classification = RuntimeConsumerClassification.KNOWN_ACTIVE
        elif runtime_items:
            classification = RuntimeConsumerClassification.RUNTIME_ONLY
        else:
            classification = RuntimeConsumerClassification.STATIC_ONLY

        versions = sorted(
            {
                item.consumer_version
                for item in runtime_items
                if item.consumer_version is not None
            }
        )
        consumers.append(
            RuntimeConsumerSummary(
                consumer_service=consumer,
                classification=classification,
                static_reference=static_reference,
                static_evidence_paths=static.get(consumer, []),
                runtime_request_count=sum(item.request_count for item in runtime_items),
                runtime_last_seen=max(
                    (item.observed_at for item in runtime_items),
                    default=None,
                ),
                runtime_versions=versions,
            )
        )

    runtime_request_count = sum(item.request_count for item in observations)
    runtime_last_seen = max((item.observed_at for item in observations), default=None)
    coverage_start = coverage[0] if coverage is not None else None
    coverage_end = coverage[1] if coverage is not None else None
    coverage_sufficient = bool(
        coverage_start is not None
        and coverage_end is not None
        and coverage_start <= window_start
        and coverage_end >= as_of
    )

    blockers: list[str] = []
    caveats = [
        "Runtime absence is meaningful only for telemetry sources and services covered by this store.",
        "Static analysis can miss dynamic clients, generated code, external consumers, and repositories that were not supplied.",
        "REMOVAL_CANDIDATE is an evidence-backed readiness signal, not proof that removal is universally safe.",
    ]

    if runtime_request_count > 0:
        status = RemovalGateStatus.BLOCKED_ACTIVE_RUNTIME
        blockers.append(
            f"{runtime_request_count} request(s) to the contract were observed inside the "
            f"{quiet_window_days}-day quiet window."
        )
        ghost_consumers = [
            consumer.consumer_service
            for consumer in consumers
            if consumer.classification == RuntimeConsumerClassification.RUNTIME_ONLY
        ]
        if ghost_consumers:
            blockers.append(
                "Runtime-only consumer(s) have no matching supplied static reference: "
                + ", ".join(ghost_consumers)
            )
    elif static:
        status = RemovalGateStatus.BLOCKED_STATIC_REFERENCE
        blockers.append(
            f"{len(static)} static consumer(s) still reference the contract: "
            + ", ".join(sorted(static))
        )
    elif not coverage_sufficient:
        status = RemovalGateStatus.INSUFFICIENT_OBSERVATION
        blockers.append(
            f"Continuous telemetry coverage does not span the full {quiet_window_days}-day quiet window."
        )
    else:
        status = RemovalGateStatus.REMOVAL_CANDIDATE

    return ContractRemovalReport(
        provider_service=provider_service,
        http_method=http_method.upper(),
        path=path,
        status=status,
        quiet_window_days=quiet_window_days,
        as_of=as_of,
        telemetry_coverage_start=coverage_start,
        telemetry_coverage_end=coverage_end,
        telemetry_coverage_sufficient=coverage_sufficient,
        runtime_request_count=runtime_request_count,
        runtime_last_seen=runtime_last_seen,
        static_reference_count=len(static),
        consumers=consumers,
        blockers=blockers,
        caveats=caveats,
    )
