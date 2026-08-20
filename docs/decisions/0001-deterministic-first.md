# ADR-0001: Build deterministic evidence extraction before agent reasoning

## Status

Accepted.

## Context

ChangeGuard will eventually use multiple agents to reason about cross-service release risk.
However, Git metadata, source structure, framework annotations, API schemas, database
migrations, and build descriptors are observable facts. Asking an LLM to rediscover
those facts would introduce avoidable cost and nondeterminism.

## Decision

V0 will produce a structured `ChangeManifest` using deterministic Git and rule-based
analysis only.

Later stages may enrich the manifest with semantic AST analysis and graph data before
the manifest is exposed to LLM-based reviewers.

## Consequences

Positive:

- easier unit testing
- reproducible benchmark inputs
- cheaper agent prompts
- clearer provenance for every finding
- deterministic facts can be separated from probabilistic judgments

Trade-off:

- the first milestone looks less "AI-heavy", but creates a stronger foundation for
  evaluation and production reliability.
