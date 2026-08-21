# ADR 0010: Maven reactor-root-aware verification planning

## Status

Accepted for V4.3 verification planning.

## Context

ChangeGuard originally generated targeted Maven plans as:

```text
mvn -pl <repository-relative-consumer-module> -am test
```

That command is valid only when the local verification workspace itself is the Maven reactor root. The seeded benchmarks exposed a common monorepo layout where the Git repository root contains several independent Maven workspaces and the relevant aggregator POM lives below the repository root.

For example, the Feign/RestTemplate benchmark lives under `benchmarks/client-style-path-break/`. Its consumer modules are valid Maven reactor members only when Maven is anchored to `benchmarks/client-style-path-break/pom.xml`.

Inferring a build root merely from directory ancestry would be unsafe and difficult to defend because a parent POM is not necessarily an aggregator for a child module.

## Decision

Verification planning discovers Maven reactor structure from explicit top-level `<modules>` declarations in `pom.xml` files at the exact analyzed Git ref.

For each Maven module, ChangeGuard records an execution layout containing:

- repository-relative module path
- reactor/build root
- build POM path
- module selector relative to the reactor root
- POM paths that provide the reactor evidence

Nested reactor declarations are followed transitively to the topmost unambiguous reactor root. If a module has multiple conflicting reactor parents or a declaration cycle, ChangeGuard does not guess a layout. A module with no enclosing reactor declaration is treated as a standalone Maven build using its own POM.

When layout evidence is available, an endpoint-backed verification plan becomes:

```text
mvn -f <reactor-pom> -pl <reactor-relative-module> -am test
```

For a standalone Maven module, the plan becomes:

```text
mvn -f <module>/pom.xml test
```

The verifier validates the selected build POM and consumer module stay inside the explicitly supplied local workspace before process execution. Remote PR analysis still never executes project build code.

## Consequences

- Generated plans are executable from the Git repository root even when the relevant Maven reactor is nested.
- Build-root selection is backed by explicit Maven reactor evidence instead of path heuristics.
- Multiple independent Maven workspaces can coexist in one repository.
- Profile-activated `<modules>` are not interpreted yet; only direct project-level `<modules>` declarations are used.
- The current implementation performs a second repository-tree read during verification planning; this can later be shared with dependency-graph construction as a performance optimization.
- Local workspace Git revision validation remains a separate future hardening step.
