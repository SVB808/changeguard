# ADR 0008: Feign and RestTemplate consumer-call evidence

## Status

Accepted for deterministic REST consumer evidence expansion.

## Context

ChangeGuard's endpoint-level refinement originally extracted literal WebClient-style calls such as `.get().uri("http://service/path")`. That proved the method+route matching design, but Spring services commonly use declarative OpenFeign interfaces or `RestTemplate` instead.

Treating those clients as unparsed would unnecessarily leave compatibility findings at service scope. At the same time, ChangeGuard must not guess dynamic URLs or method mappings that are not explicit in source.

## Decision

ChangeGuard adds two deterministic consumer-evidence paths:

1. **OpenFeign declarations**: a Java client source annotated with `@FeignClient` may contribute a service dependency and method+route calls when the target service name and mapping paths are literal. Class-level `@RequestMapping` paths are combined with method-level `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, `@DeleteMapping`, or `@RequestMapping(method = RequestMethod.X)` paths.
2. **RestTemplate literal calls**: client-like Java sources may contribute method+route evidence for literal absolute service URLs used by `getForObject`, `getForEntity`, `postForObject`, `postForEntity`, `put`, `delete`, and `exchange(..., HttpMethod.X, ...)`.

Feign service references are represented as `declarative_client` dependency evidence rather than pretending that a declarative client annotation is a literal URL.

Only literal target names and literal routes are used. Property placeholders without an inline literal default, URI-builder composition, variables containing base URLs, custom Feign contracts, and computed `HttpMethod` values remain unresolved.

## Consequences

- Endpoint-level impact refinement can now use common WebClient, OpenFeign, and RestTemplate evidence.
- Feign clients can establish a direct dependency even when no `http://service` string exists in the repository.
- Existing WebClient behavior and the V4.1 corpus remain unchanged.
- The implementation remains intentionally conservative: absence of extracted evidence is not evidence of absence.

## Follow-up

Future work may move Java call extraction into the JVM analyzer for symbol-aware parsing, add `WebClient.builder().baseUrl(...)` flow analysis, support generated clients, and model gateway rewrite semantics separately from application-call evidence.
