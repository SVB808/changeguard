# ADR 0022: Freeze the ChangeGuard V1 release-candidate scope

## Status

Accepted.

## Context

ChangeGuard now spans deterministic change extraction, Java/Spring semantic analysis, service/consumer graphs, endpoint-level impact refinement, revision-bound Maven verification, grounded evidence selection, deterministic decision-critical closure, and repeatable evaluation.

Continuing to add new risk domains before a first release would make the supported boundary harder to explain and validate. The strongest V1 story is not broad feature count; it is a narrow system with explicit guarantees, measured model behavior, and controlled claims.

## Decision

Freeze V1 at the following supported release-candidate scope:

- Java/Spring REST and Spring Security semantic evidence
- WebClient, OpenFeign, and RestTemplate consumer-call evidence
- module-scoped cross-service impact analysis
- endpoint-backed Maven verification planning
- exact Git-head binding before local project execution
- deterministic, Ollama, and optional OpenAI evidence-ID selectors
- deterministic grounding and policy closure
- controlled deterministic, selector, reproducibility, policy, and runtime-shaped release evaluation

Database/messaging deep semantics, Gradle, hosted UI, GitHub Check integration, and autonomous multi-agent workflows are explicitly post-V1.

## Consequences

- V1 can be documented and interviewed as a coherent end-to-end system rather than an unfinished platform.
- Release claims remain scoped to controlled corpora and supported evidence types.
- CI can enforce one consolidated deterministic release-candidate gate.
- Future domains can be added without weakening the current invariants or silently expanding claimed coverage.
- Final merge/tag remains a separate explicit release action.
