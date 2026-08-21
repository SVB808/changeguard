# ADR-0006: Refine service-level impact candidates with explicit HTTP call sites

## Status

Accepted for V2.2.

## Context

V2.1 joins provider-side semantic changes with service-level dependency edges. That is useful for recall, but it can produce false positives because a service may depend on another service without calling the particular endpoint that changed.

Petclinic PR #253 is the motivating public case. `customers-service` changes the request types for `POST /owners` and `PUT /owners/{ownerId}`. The dependency graph correctly finds `api-gateway -> customers-service`, but the explicit `CustomersServiceClient` call at that revision is `GET /owners/{ownerId}`. A service-level candidate therefore overstates the evidence.

## Decision

V2.2 extracts a narrow, deterministic set of explicit consumer HTTP calls from Java classes named `*Client`, `*Gateway`, or `*Connector` when the call uses a literal service URL in a fluent form such as:

```java
webClientBuilder.build().get()
    .uri("http://customers-service/owners/{ownerId}", ownerId)
```

The extracted fact contains:

- consumer service
- target service
- HTTP method
- normalized path
- evidence file
- source expression

Impact refinement uses the provider endpoint's previous contract when available. HTTP method and normalized route must match. Path-variable names are normalized, so `/owners/{ownerId}` and `/owners/{id}` are treated as the same route shape.

If an exact call matches, the candidate is upgraded from `service` to `endpoint` match level.

If explicit literal calls to the same provider are available but none match the changed endpoint, the service-level candidate is removed from the active list and retained separately as a suppressed candidate with the observed call evidence and a suppression explanation.

If no explicit call-site evidence is available for the consumer/provider pair, the service-level candidate remains active. Absence of parsed evidence is not treated as proof that no call exists.

## Why suppression is auditable instead of deletion

The extractor intentionally does not resolve dynamic URI construction, helper methods, generated clients, Feign interfaces, RestTemplate variants, or reflection. A non-match therefore reduces confidence but cannot prove the absence of every consumer call. Keeping suppressed candidates separately preserves the reasoning trail and avoids converting a precision heuristic into a false certainty.

## Consequences

Positive:

- lowers false positives when concrete call-site evidence contradicts a service-level candidate
- provides stronger endpoint-level evidence when method and route match
- keeps deterministic evidence separate from later risk/severity reasoning
- creates a measurable precision-improvement benchmark using PR #253

Limitations:

- only literal fluent HTTP calls are extracted in V2.2
- dynamic host/path composition is not resolved
- gateway forwarding is still represented as dependency evidence, not as an application call site
- no request-body type comparison at the consumer call site yet
- no runtime verification yet

## Next steps

Broaden call extraction carefully (for example dynamic base URLs and additional client APIs), then add verifier stages that can run targeted consumer/provider tests before any LLM-based reasoning assigns release risk.
