# ADR 0004: Build the first cross-service graph from explicit repository evidence

## Status

Accepted

## Context

V1 can now extract deterministic Spring REST and Spring Security facts from changed Java files, but ChangeGuard still cannot answer its core cross-service question: which other services depend on the service being changed?

A complete dependency graph could require understanding every HTTP client library, messaging framework, service-discovery abstraction, configuration convention, and runtime topology. Trying to solve all of that at once would make the graph difficult to validate and would mix high-confidence facts with guesses.

## Decision

V2 begins with a deliberately narrow, deterministic service graph built from repository-wide evidence at an exact Git ref.

Service nodes are inferred from top-level Maven modules named `spring-petclinic-*`.

The first edge extractors use only explicit evidence:

- Spring Cloud Gateway `lb://service` routes
- literal service URLs in `application*.yml`, `application*.yaml`, and `application*.properties`
- literal service URLs in Java classes named `*Client`, `*Gateway`, or `*Connector`

Each edge records its source service, target service, dependency kind, evidence file, and literal evidence.

PR analysis can optionally attach the owning service and its direct dependents to each changed file using `--dependencies`.

## Consequences

This gives ChangeGuard its first repository-wide cross-service context without using an LLM and without cloning the target repository.

The graph is intentionally incomplete. It does not yet discover dynamic URL construction, arbitrary WebClient/RestTemplate call sites, Feign clients, messaging topics, database sharing, or transitive dependencies.

A direct dependent is a graph fact, not a statement that the dependent will break. V2.1 will combine graph edges with semantic contract changes to produce evidence-backed impact candidates.
