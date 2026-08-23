# ADR-0007: Verification execution requires an explicit local workspace

## Status
Accepted for the first verifier milestone.

## Context
ChangeGuard now produces endpoint-level cross-service impact candidates from deterministic provider and consumer evidence. The next architectural step is verification: attempt to falsify or support a candidate with targeted builds or tests.

Automatically cloning and executing arbitrary public pull-request code is a security boundary, not just an implementation detail. Build tools can execute project-controlled plugins and scripts.

## Decision
The first verifier will separate planning from execution.

1. Remote PR analysis may create a deterministic verification plan for an active endpoint-level candidate.
2. A plan identifies the consumer module and a targeted Maven command.
3. ChangeGuard will not automatically execute code from the remote pull request during `changeguard pr`.
4. Execution requires a user-supplied local repository workspace and an explicit `changeguard verify` command.
5. Verification results are process evidence only: command, exit status, duration, and bounded output. A passing build does not prove semantic compatibility, and a failing build does not by itself prove the candidate caused the failure.

## Initial Maven strategy
For a consumer module in a Maven multi-module repository, the deterministic default command is:

`mvn -pl <consumer-module> -am test`

This compiles/tests the consumer and required reactor dependencies while avoiding a full-repository test run.

## Consequences
- Safer default behavior: remote analysis never executes untrusted project code.
- Reproducible verifier commands can be reviewed before execution.
- The first verifier is intentionally coarse: it runs the consumer module's existing tests rather than synthesizing endpoint-specific tests.
- Later milestones can add Testcontainers, Pact, targeted test selection, sandboxed execution, and agent-proposed verification steps behind the same explicit execution boundary.
