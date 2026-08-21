# PR #16 client-style benchmark validation

Validated on Windows against the deliberately broken provider-path case.

Observed baseline:
- 65 Python tests passed before module-scoped identity work
- rest-impact-v2 strict evaluation remained 22/22
- client-style Maven baseline passed

Observed breaking case:
- semantic change: `ENDPOINT_PATH_CHANGED` from `GET /orders/{orderId}` to `GET /purchases/{orderId}`
- Feign consumer produced an endpoint-level impact candidate and verification plan
- RestTemplate consumer produced an endpoint-level impact candidate and verification plan
- explicit Feign verification failed on `provider no longer serves Feign route /orders/42`
- explicit RestTemplate verification failed on `provider no longer serves RestTemplate route /orders/42`

These are seeded benchmark results, not production-accuracy claims.
