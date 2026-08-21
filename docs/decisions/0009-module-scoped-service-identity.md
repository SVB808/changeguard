# ADR 0009: Module-scoped service identity

## Status

Accepted after seeded multi-workspace validation.

## Context

ChangeGuard historically treated `spring.application.name` (or a fallback module-derived name) as a repository-global service identifier. That works when each logical service name is unique across a repository, but a monorepo can contain multiple Maven workspaces or benchmark fixtures that legitimately reuse the same logical name.

The seeded Feign/RestTemplate benchmark exposed this directly: both `benchmarks/rest-path-break` and `benchmarks/client-style-path-break` contain a logical `provider-service`. Name-only dependency joins caused the WebClient benchmark consumer to appear as an unrelated dependent of the client-style benchmark provider.

## Decision

Keep the logical service name for human-readable output, but use Maven module path as the unique repository-local service identity for dependency and call-site joins.

Dependency edges and consumer HTTP-call evidence record both logical names and source/target module paths. When a literal target name maps to multiple modules, ChangeGuard resolves it only when one target has a uniquely closest common path ancestry with the source module. Ties remain unresolved rather than guessed.

PR impact analysis resolves the changed provider by file path, then joins only edges whose `target_module` matches that provider module. Consumer call refinement likewise joins by consumer and provider module paths. Verification planning uses the candidate's resolved consumer module directly.

## Consequences

- Duplicate logical service names in separate Maven workspaces no longer create cross-workspace impact candidates.
- CLI output can continue to display readable service names.
- Existing repositories with unique service names retain the same behavior.
- Ambiguous duplicate names at the same structural distance remain unresolved conservatively.
- Maven module path is a repository-local identity, not a globally stable deployment identifier.

## Follow-up

Future graph models may expose an explicit stable service identity object and diagnostics for unresolved ambiguous target names.
