from __future__ import annotations

import re

from changeguard.models import (
    ConsumerHttpCall,
    EndpointChangeKind,
    FileChange,
    ImpactCandidate,
    ImpactMatchLevel,
    ServiceDependencyGraph,
    ServiceNode,
    SpringEndpoint,
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


NO_EXACT_CALL_REASON = (
    "Explicit literal HTTP calls to the provider were found for this consumer, but none "
    "match the changed endpoint's previous method and path. The service-level candidate "
    "is suppressed from the active list; dynamic or unparsed call sites may still exist."
)


def generate_impact_candidates(
    files: list[FileChange],
    graph: ServiceDependencyGraph,
) -> list[ImpactCandidate]:
    """Join compatibility-sensitive semantic changes with module-scoped dependencies."""
    candidates: list[ImpactCandidate] = []

    for file in files:
        provider_node = graph.node_for_path(file.path)
        provider = file.service or (provider_node.name if provider_node is not None else None)
        if provider is None:
            continue

        if provider_node is None:
            provider_module = file.service_module
            dependent_nodes = [
                node
                for node in graph.nodes
                if node.name in graph.direct_dependents(provider)
            ]
        else:
            provider_module = provider_node.module_path
            dependent_nodes = graph.direct_dependent_nodes(provider_node)

        for semantic_change in file.semantic_changes:
            reason = COMPATIBILITY_SENSITIVE_ENDPOINT_CHANGES.get(semantic_change.kind)
            if reason is None:
                continue

            for consumer_node in dependent_nodes:
                if provider_node is not None:
                    evidence = graph.edges_between_nodes(consumer_node, provider_node)
                else:
                    evidence = graph.edges_between(consumer_node.name, provider)
                if not evidence:
                    continue

                candidates.append(
                    ImpactCandidate(
                        provider_service=provider,
                        consumer_service=consumer_node.name,
                        provider_module=provider_module,
                        consumer_module=consumer_node.module_path,
                        changed_file=file.path,
                        trigger_kind=semantic_change.kind,
                        before=semantic_change.before,
                        after=semantic_change.after,
                        reason=reason,
                        dependency_evidence=evidence,
                    )
                )

    return sorted(candidates, key=_candidate_sort_key)


def refine_impact_candidates(
    candidates: list[ImpactCandidate],
    graph: ServiceDependencyGraph,
) -> tuple[list[ImpactCandidate], list[ImpactCandidate]]:
    """Use explicit consumer call sites to upgrade or suppress service-level candidates.

    Module paths are preferred for joins so duplicate logical service names in separate
    Maven workspaces cannot contaminate each other's call evidence. Legacy name-only
    graphs still fall back to their original behavior.
    """
    active: list[ImpactCandidate] = []
    suppressed: list[ImpactCandidate] = []

    for candidate in candidates:
        provider_node = _node_for_module(graph, candidate.provider_module)
        consumer_node = _node_for_module(graph, candidate.consumer_module)
        if provider_node is not None and consumer_node is not None:
            calls = graph.calls_between_nodes(consumer_node, provider_node)
        else:
            calls = graph.calls_between(
                candidate.consumer_service,
                candidate.provider_service,
            )

        if not calls:
            active.append(candidate)
            continue

        endpoint = candidate.before or candidate.after
        if endpoint is None:
            active.append(candidate)
            continue

        exact_calls = [call for call in calls if _call_matches_endpoint(call, endpoint)]
        if exact_calls:
            active.append(
                candidate.model_copy(
                    update={
                        "match_level": ImpactMatchLevel.ENDPOINT,
                        "consumer_call_evidence": exact_calls,
                        "reason": (
                            candidate.reason
                            + " Exact consumer HTTP call evidence matches the previous contract."
                        ),
                    }
                )
            )
        else:
            suppressed.append(
                candidate.model_copy(
                    update={
                        "consumer_call_evidence": calls,
                        "suppression_reason": NO_EXACT_CALL_REASON,
                    }
                )
            )

    return (
        sorted(active, key=_candidate_sort_key),
        sorted(suppressed, key=_candidate_sort_key),
    )


def _node_for_module(
    graph: ServiceDependencyGraph,
    module_path: str | None,
) -> ServiceNode | None:
    if module_path is None:
        return None
    return next(
        (node for node in graph.nodes if node.module_path == module_path),
        None,
    )


def _call_matches_endpoint(call: ConsumerHttpCall, endpoint: SpringEndpoint) -> bool:
    method_matches = (
        endpoint.http_method == "ANY"
        or call.http_method.upper() == endpoint.http_method.upper()
    )
    return method_matches and _route_matches(call.path, endpoint.path)


def _route_matches(call_path: str, endpoint_path: str) -> bool:
    """Match a consumer route against a Spring endpoint path deterministically.

    Path-variable names are treated structurally, query strings are ignored for routing,
    and Spring-style `*`/`**` path wildcards are supported. We intentionally do not try
    to interpret arbitrary regex constraints inside path-variable declarations yet.
    """
    call_route = _normalize_route(call_path)
    endpoint_route = _normalize_route(endpoint_path)

    pattern_parts: list[str] = []
    index = 0
    while index < len(endpoint_route):
        char = endpoint_route[index]

        if char == "{":
            closing = endpoint_route.find("}", index + 1)
            if closing != -1:
                pattern_parts.append(r"[^/]+")
                index = closing + 1
                continue

        if endpoint_route.startswith("**", index):
            pattern_parts.append(r".*")
            index += 2
            continue

        if char == "*":
            pattern_parts.append(r"[^/]*")
            index += 1
            continue

        pattern_parts.append(re.escape(char))
        index += 1

    return re.fullmatch("".join(pattern_parts), call_route) is not None


def _normalize_route(path: str) -> str:
    route = path.split("?", 1)[0].strip()
    route = "/" + route.lstrip("/")
    if len(route) > 1:
        route = route.rstrip("/")
    return route


def _candidate_sort_key(candidate: ImpactCandidate) -> tuple[str, str, str, str, str, str, str, str]:
    return (
        candidate.provider_module or "",
        candidate.consumer_module or "",
        candidate.provider_service,
        candidate.consumer_service,
        candidate.changed_file,
        candidate.trigger_kind.value,
        candidate.before.path if candidate.before is not None else "",
        candidate.after.path if candidate.after is not None else "",
    )
