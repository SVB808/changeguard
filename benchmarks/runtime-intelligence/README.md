# Runtime contract-intelligence benchmark

This seeded fixture demonstrates the new product question:

> Can an endpoint be removed when static source evidence looks incomplete or clean, but deployed runtime traffic still exists?

The static graph contains one known source consumer:

```text
checkout-service -> orders-service GET /v1/orders/{orderId}
```

The runtime fixture contains traffic from a different consumer:

```text
legacy-mobile:v11 -> orders-service GET /v1/orders/42
17 requests
```

Because `legacy-mobile` is not represented by the supplied static call graph, ChangeGuard should classify it as a `runtime_only` ghost dependency and block contract removal.

## Run

```powershell
Remove-Item .changeguard/runtime-demo.db -ErrorAction SilentlyContinue

changeguard-runtime ingest `
  --file benchmarks/runtime-intelligence/runtime-observations.json `
  --db .changeguard/runtime-demo.db `
  --coverage-start 2026-08-16T00:00:00+00:00 `
  --coverage-end 2026-08-24T00:00:00+00:00

changeguard-runtime removal-gate `
  --db .changeguard/runtime-demo.db `
  --provider orders-service `
  --method GET `
  --path '/v1/orders/{orderId}' `
  --graph benchmarks/runtime-intelligence/service-graph.json `
  --quiet-days 7 `
  --as-of 2026-08-24T00:00:00+00:00
```

Expected high-level result:

```text
decision: BLOCKED_ACTIVE_RUNTIME
runtime requests: 17
static consumers: 1

checkout-service: static_only
legacy-mobile: runtime_only
```

This is controlled seeded evidence. It demonstrates reconciliation behavior, not production traffic coverage.
