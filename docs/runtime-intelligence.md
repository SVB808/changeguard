# Runtime contract intelligence

ChangeGuard's V1 static engine answers which known source consumers can be affected by a contract change. This experimental V2 slice adds a different question:

> **Is this contract still being used at runtime, and do static and runtime reality disagree?**

The feature is intentionally deterministic. Runtime observations are normalized and stored locally; no telemetry is sent to an LLM.

## Why this exists

A source migration can appear complete while an older deployment, external client, script, generated caller, or repository outside the scan still sends traffic to the old endpoint. Conversely, source code may retain an old client that no deployed version has called for weeks.

The useful reconciliation matrix is:

| Static reference | Runtime traffic | Interpretation |
| --- | --- | --- |
| yes | yes | known active dependency |
| yes | no | static-only dependency; review for dead/stale code |
| no | yes | runtime-only / ghost dependency |
| no | no | removal candidate only after sufficient telemetry coverage |

## Install

After installing the project from this branch, a second CLI entry point is available:

```powershell
changeguard-runtime --help
```

The existing `changeguard` CLI remains unchanged.

## 1. Build/export static graph evidence

For each repository you want to include in the decision:

```powershell
changeguard graph `
  --repo owner/repository `
  --ref main `
  --json |
  Out-File -Encoding utf8 repository-graph.json
```

`removal-gate` accepts `--graph` multiple times, so independently generated repository/service graph snapshots can be reconciled together.

## 2. Ingest OTLP JSON

```powershell
changeguard-runtime ingest `
  --file traces.json `
  --db .changeguard/runtime.db `
  --coverage-start 2026-08-01T00:00:00+00:00 `
  --coverage-end 2026-08-24T00:00:00+00:00
```

Supported input forms:

- OTLP JSON with `resourceSpans`
- a JSON array of normalized observations
- `{ "observations": [...] }`
- one normalized observation object

A normalized observation looks like:

```json
{
  "observed_at": "2026-08-23T10:30:00+00:00",
  "consumer_service": "mobile-backend",
  "consumer_version": "11",
  "provider_service": "orders-service",
  "http_method": "GET",
  "path": "/v1/orders/42",
  "request_count": 17,
  "event_id": "trace-or-span-id"
}
```

## 3. Record zero-traffic telemetry coverage

A period with no matching request is useful only when we know telemetry was actually being collected. Record coverage explicitly:

```powershell
changeguard-runtime coverage `
  --db .changeguard/runtime.db `
  --start 2026-08-01T00:00:00+00:00 `
  --end 2026-08-24T00:00:00+00:00 `
  --source otel-prod
```

This prevents an empty database from being interpreted as proof of no traffic.

## 4. Evaluate an endpoint removal

```powershell
changeguard-runtime removal-gate `
  --db .changeguard/runtime.db `
  --provider orders-service `
  --method GET `
  --path /v1/orders/{orderId} `
  --graph checkout-graph.json `
  --graph billing-graph.json `
  --quiet-days 7
```

Possible decisions:

```text
BLOCKED_ACTIVE_RUNTIME
BLOCKED_STATIC_REFERENCE
INSUFFICIENT_OBSERVATION
REMOVAL_CANDIDATE
```

`REMOVAL_CANDIDATE` means only that the supplied evidence passed the gate. It is not a universal safety claim.

## Example: ghost dependency

Suppose source analysis finds no reference from `legacy-mobile`, but telemetry shows:

```text
legacy-mobile:v11 -> orders-service GET /v1/orders/42
17 requests in the last 7 days
```

The report classifies `legacy-mobile` as `runtime_only` and blocks removal. This is the key capability that a source-only coding assistant does not inherently possess: evidence from deployed reality rather than only the code it can inspect.

## Demo helpers

For adapters that are not yet OTLP-based, one normalized observation can be recorded manually:

```powershell
changeguard-runtime observe `
  --db .changeguard/runtime.db `
  --consumer legacy-mobile `
  --consumer-version 11 `
  --provider orders-service `
  --method GET `
  --path /v1/orders/42 `
  --at 2026-08-23T10:30:00+00:00 `
  --count 17
```

## Current scope

This is a production-shaped local evidence engine, not yet a production telemetry platform. Current limitations include:

- HTTP only
- file/import-based OTLP JSON rather than a long-running OTLP receiver
- provider identity must normalize to the same service name used by static graphs
- no deployment orchestrator integration yet
- no source-health/collector-health model beyond explicit coverage intervals
- static graphs are supplied snapshots rather than continuously synchronized org-wide inventory
- no authorization/multi-tenant layer

The next production step would be a real OTLP receiver plus deployment metadata so reports can say which deployed version made the last call and whether that version still receives traffic.
