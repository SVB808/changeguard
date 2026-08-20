# ADR 0005: Keep impact candidates evidence-scoped

## Status

Accepted

## Context

V1 extracts deterministic endpoint facts. V2 adds explicit service dependency edges. A direct service dependency does not prove that a consumer invokes the exact endpoint that changed.

## Decision

V2.1 emits `POTENTIAL_CONSUMER_IMPACT` only when a compatibility-sensitive endpoint change and a direct service dependency both exist.

Compatibility-sensitive changes are endpoint removal, path change, HTTP method change, request signature change, and response type change. Endpoint additions are excluded.

Each candidate records the provider, consumer, changed file, semantic trigger, before/after endpoint snapshots, dependency evidence, and a `service` match level. The match level makes clear that exact call-site matching has not yet been proven.

## Consequences

The system can surface cross-service candidates without presenting them as confirmed breakages. A later stage can match exact call sites and run verification tests before stronger conclusions are made.
