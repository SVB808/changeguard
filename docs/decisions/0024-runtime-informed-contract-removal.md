# ADR 0024: Runtime-informed contract removal readiness

Status: accepted for evaluation

## Context

Static source analysis can prove that a known source reference exists, but absence of a source reference does not prove that a contract is unused. Old deployments, external clients, dynamic URLs, generated code, scripts, or repositories outside the scan can continue sending production traffic after source migrations appear complete.

A coding assistant can reason over code that it can inspect, but it does not inherently own a continuously observed record of which deployed consumers are still using a contract.

## Decision

ChangeGuard adds a local runtime evidence layer that can ingest normalized HTTP observations or OTLP JSON into SQLite and reconcile those observations with supplied static service graphs.

The removal gate classifies a contract as one of:

- `BLOCKED_ACTIVE_RUNTIME`: matching runtime traffic exists inside the configured quiet window.
- `BLOCKED_STATIC_REFERENCE`: runtime is quiet, but supplied static consumer references still exist.
- `INSUFFICIENT_OBSERVATION`: no runtime/static blocker is known, but continuous telemetry coverage does not span the entire quiet window.
- `REMOVAL_CANDIDATE`: supplied static graphs show no caller, the runtime store shows no matching traffic, and continuous telemetry coverage spans the quiet window.

`REMOVAL_CANDIDATE` is deliberately not named `SAFE_TO_REMOVE`. The evidence can still be incomplete.

Runtime/static reconciliation also exposes `runtime_only` consumers. These are ghost dependencies: runtime traffic exists even though no matching static call was found in the supplied graphs.

## Evidence and safety rules

1. Raw runtime telemetry is not sent to an LLM by this feature.
2. Observations are stored locally in SQLite by default.
3. Re-imported observations are deduplicated by span/event ID when available, otherwise by a stable content hash.
4. Zero traffic is not treated as evidence unless an explicit telemetry coverage interval spans the configured quiet window.
5. Static graph absence is scoped only to the graph files supplied to the decision.
6. Route matching supports literal paths, Spring-style path variables, and `*`/`**` patterns; it does not infer arbitrary application routing or gateway rewrites.

## OTLP normalization

For OTLP JSON client spans, ChangeGuard currently reads:

- consumer identity from resource `service.name`
- consumer version from resource `service.version`
- provider identity from `changeguard.target_service`, `peer.service`, `server.address`, or `net.peer.name`
- HTTP method from `http.request.method` or `http.method`
- path from `http.route`, `url.path`, `http.target`, `url.full`, or `http.url`
- status from `http.response.status_code` or `http.status_code`

Organizations with service-mesh or gateway-specific naming should normalize provider identity before ingestion or emit the explicit `changeguard.target_service` attribute.

## Consequences

This creates a new product boundary for ChangeGuard: static analysis becomes one evidence source in a broader contract-lifecycle system rather than the entire product.

A future production system should add continuous OTLP collection, deployment-version metadata, cross-repository graph snapshots, observation-source health, coverage-gap detection beyond interval merging, authentication, retention policy, and provider aliases. Those are intentionally not claimed by this slice.
