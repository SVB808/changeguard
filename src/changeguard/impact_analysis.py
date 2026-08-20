from __future__ import annotations

from changeguard.models import (
    EndpointChangeKind,
    FileChange,
    ImpactCandidate,
    ServiceDependencyGraph,
)


COMPATIBILITY_SENSITIVE_ENDPOINT_CHANGES: dict[EndpointChangeKind, str] = {
    EndpointChangeKind.ENDPOINT_REMOVED: (
        "Provider endpoint was removed; direct dependents may require compatibility verification."
    ),
    EndpointChangeKind.ENDPOINT_PATH_CHANGED: (
        "Provider endpoint path changed; direct dependents may still call the previous path."
    ),
    EndpointChangeKind.ENDPOINT_METHOD_CHANGED: (
        "Provider HTTP method changed; direct dependents may still use the previous method."
    ),
    EndpointChangeKind.REQUEST_SIGNATURE_CHANGED: (
        "Provider request signature changed; direct dependents may send an incompatible request."
    ),
    EndpointChangeKind.RESPONSE_TYPE_CHANGED: (
        "Provider response type changed; direct dependents may deserialize an incompatible response."
    ),
}


def generate_impact_candidates(
    files: list[FileChange],
    graph: ServiceDependencyGraph,
) -> list[ImpactCandidate]:
    """Join semantic contract changes with explicit service dependency evidence.

    V2.1 intentionally generates *candidates*, not breakage claims. The graph currently
    proves only that one service depends on another at service scope. Endpoint-level
    call-site matching and runtime verification are later stages.
    """
    candidates: list[ImpactCandidate] = []

    for file in files:
        provider = file.service or graph.service_for_path(file.path)
        if provider is None:
            continue

        for semantic_change in file.semantic_changes:
            reason = COMPATIBILITY_SENSITIVE_ENDPOINT_CHANGES.get(semantic_change.kind)
            if reason is None:
                continue

            for consumer in graph.direct_dependents(provider):
                evidence = graph.edges_between(consumer, provider)
                if not evidence:
                    continue

                candidates.append(
                    ImpactCandidate(
                        provider_service=provider,
                        consumer_service=consumer,
                        changed_file=file.path,
                        trigger_kind=semantic_change.kind,
                        before=semantic_change.before,
                        after=semantic_change.after,
                        reason=reason,
                        dependency_evidence=evidence,
                    )
                )

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.provider_service,
            candidate.consumer_service,
            candidate.changed_file,
            candidate.trigger_kind.value,
            candidate.before.path if candidate.before is not None else "",
            candidate.after.path if candidate.after is not None else "",
        ),
    )
