# ADR 0007: Repository-agnostic Maven service discovery

## Status

Accepted for the deterministic Maven graph builder.

## Context

The first ChangeGuard dependency-graph implementation identified services by a repository-specific `spring-petclinic-` module-name prefix. That was useful for proving the graph on a public benchmark, but it made a benchmark convention part of product architecture.

Cross-service analysis needs a service identity that can be derived from repository evidence without knowing the repository name in advance.

## Decision

ChangeGuard discovers Maven-backed service nodes from repository `pom.xml` paths instead of a project-specific prefix.

Service identity is resolved in this order:

1. Prefer a literal `spring.application.name` found in the module's `application*.yml`, `application*.yaml`, or `application*.properties`.
2. Accept a literal default from `${ENV_VAR:default-service-name}` because the fallback value is present in source and therefore deterministic.
3. Otherwise use the Maven module basename.
4. For sibling modules only, a common prefix may be removed when every remaining name still ends in the conventional `service`, `server`, or `gateway` role. This preserves conventional monorepo names such as `acme-orders-service` / `acme-api-gateway` without baking `acme` into ChangeGuard.

Pure Maven aggregator modules are excluded when they contain child modules and have no `src/main` content. Leaf modules remain candidates even when ChangeGuard cannot prove that they are deployable applications; downstream dependency evidence determines whether they participate in the cross-service graph.

Application configuration is read through a per-build cache so service-name discovery does not cause the same file to be fetched again during dependency extraction.

## Why not infer arbitrary service names from URLs alone?

A URL proves that a target name is referenced, but it does not reliably identify which Maven module owns that target. Guessing ownership from arbitrary string similarity would turn repository naming conventions into hidden fuzzy logic.

`spring.application.name` is stronger ownership evidence. Module basenames and the constrained sibling-prefix fallback are explicit, inspectable fallbacks.

## Consequences

- ChangeGuard no longer contains the Petclinic-specific `spring-petclinic-` discovery constant.
- Existing Petclinic and seeded benchmark module layouts remain discoverable through the constrained sibling-prefix fallback.
- Generic Maven repositories can use their real `spring.application.name` values even when module directories have unrelated names such as `billing-app` or `edge-router`.
- Shared-library Maven modules can appear as nodes when they are leaf modules. They do not become dependency edges unless supported by existing deterministic URL/route evidence.
- Dynamic or computed application names without a literal default are not resolved.
- Duplicate `spring.application.name` values across modules remain an ambiguity to address separately rather than silently inventing unique identities.

## Follow-up

Future work may add Gradle module discovery, stronger Maven packaging/plugin evidence, duplicate-name diagnostics, Feign/RestTemplate call extraction, and explicit discovery evidence on `ServiceNode` output.