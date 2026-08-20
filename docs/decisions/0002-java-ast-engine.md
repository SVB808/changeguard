# ADR-0002: Use JavaParser for the first Java/Spring semantic analyzer

## Status

Accepted for V1.1.

## Context

ChangeGuard V0 classifies changed files and diff hunks, but Spring REST semantics can depend on source outside the changed hunk. For example, a method-level `@GetMapping("/health")` may be nested under a class-level `@RequestMapping("/vets")`, so the real endpoint is `/vets/health`.

We need a deterministic Java syntax tree before adding probabilistic reasoning.

OpenRewrite was considered because its lossless semantic tree is attractive for large-scale Java analysis and transformation. However, the current OpenRewrite distribution path for recent modules requires Code Genome Project repository authentication. That adds setup friction for an open-source portfolio project whose first analyzer only needs reliable Java AST traversal.

JavaParser is available from Maven Central and provides a mature Java AST. Its symbol solver can be introduced later when ChangeGuard needs type attribution across files and dependencies.

## Decision

Use JavaParser for V1.1 to extract Spring controller and endpoint facts from full Java source files.

The analyzer will:

- parse complete source files rather than raw diff hunks,
- extract class-level and method-level Spring request mappings,
- emit deterministic endpoint snapshots,
- compare before/after snapshots,
- report semantic changes without assigning risk severity.

## Consequences

Positive:

- reproducible public build with Maven Central dependencies,
- no LLM required for endpoint discovery,
- full-file context solves class-level mapping blind spots,
- isolated JVM analyzer preserves Java ecosystem fidelity,
- clear upgrade path to symbol solving and deeper Spring semantics.

Trade-offs:

- V1.1 is syntax-aware rather than fully type-attributed,
- composed/meta-annotations are not resolved yet,
- overloaded controller methods and dynamic mapping constants require stronger identity/type resolution later,
- OpenRewrite may still be revisited for rewrite-aware or type-attributed analysis.
