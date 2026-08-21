# Seeded Feign + RestTemplate path-break benchmark

This Maven workspace gives ChangeGuard deterministic ground truth for two common Spring consumer styles.

Baseline provider contract:

```text
GET /orders/{orderId}
```

Consumers:

- `feign-consumer-service` declares the route through `@FeignClient` + Spring mapping annotations.
- `resttemplate-consumer-service` calls the same route through a literal `RestTemplate.getForEntity(...)`-style invocation.

The baseline must pass. A paired benchmark PR changes only the provider route to `GET /purchases/{orderId}` while both consumers remain on `/orders/{orderId}`. ChangeGuard should therefore produce two endpoint-level impact candidates and two targeted Maven verification plans. Running either consumer module's contract test against the changed provider should fail.

The Java sources use tiny local annotation/client stubs so the benchmark tests contract behavior without pulling Spring runtime dependencies. The source shapes are intentionally representative of the deterministic evidence ChangeGuard parses.
