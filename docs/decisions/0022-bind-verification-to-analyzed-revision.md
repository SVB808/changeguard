# ADR 0022: Bind verification execution to the analyzed Git revision

## Status

Accepted.

## Context

ChangeGuard can derive a targeted verification plan from a remote pull request and later execute that plan in a user-supplied local workspace. Without revision binding, a valid command could be executed against a different checkout from the revision that produced the impact evidence. That would make the resulting process evidence ambiguous and could create a false sense that the analyzed PR was actually tested.

## Decision

`VerificationPlan` carries an optional `expected_head` revision. Plans generated from GitHub pull-request analysis set it to the exact PR head SHA.

Before executing a bound plan, ChangeGuard validates the workspace shape and then reads `git rev-parse HEAD`. If the workspace HEAD differs from `expected_head`, execution returns `ERROR` before Maven resolution or project-code execution.

`changeguard verify-plan` accepts a manifest plan only when it is revision-bound. The older manual `changeguard verify` path remains an explicit user-created plan and may optionally be bound with `--expected-head`.

## Consequences

- Verification evidence can be tied to the same revision as analysis evidence.
- A stale or wrong checkout fails closed instead of silently running tests.
- Remote analysis still never executes target repository code.
- Users must check out the analyzed revision before executing a generated plan.
- Revision binding does not prove the workspace is otherwise clean or hermetic; it only guarantees exact committed HEAD identity.
