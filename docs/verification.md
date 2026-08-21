# Targeted verification

ChangeGuard separates remote analysis from local build execution.

`changeguard pr` can analyze a public pull request, refine cross-service impact candidates, and create a deterministic verification plan. It does **not** execute the remote project's build scripts.

A V3.0 verification plan is created only when an impact candidate has endpoint-level evidence. Service-level candidates are intentionally not strong enough to trigger targeted execution.

For a Maven multi-module consumer, the initial plan is:

```text
mvn -pl <consumer-module> -am test
```

This runs the consumer module's existing tests and any required reactor dependencies. It is a coarse verification step, not an endpoint-specific contract test.

## Remote planning

```text
changeguard pr --repo owner/repository --pr 123 --verification-plan
```

`--verification-plan` implies semantic analysis, dependency analysis, and impact refinement. The output includes the proposed command and leaves the plan in `NOT_RUN` state.

## Local execution

Execution requires a local Maven repository workspace supplied explicitly by the user:

```text
changeguard verify \
  --repo /path/to/checked-out/repository \
  --consumer api-gateway \
  --module spring-petclinic-api-gateway
```

The local workspace should be checked out to the revision the user intends to verify. V3.0 does not yet enforce a specific Git SHA.

ChangeGuard records:
- verification status
- command
- exit code
- duration
- bounded stdout/stderr tails

Statuses describe the process only:
- `PASSED`: command exited with status 0
- `FAILED`: command completed with a non-zero exit status
- `ERROR`: ChangeGuard could not execute the command or validate the workspace
- `NOT_RUN`: a plan exists but has not been executed

A `PASSED` result is not automatically equivalent to "safe". A `FAILED` result is not automatically equivalent to "confirmed breakage". Attribution remains a separate step.

## Safety boundary

Maven builds can execute project-controlled plugins and scripts. ChangeGuard therefore never runs remote pull-request code as a side effect of `changeguard pr`. Local verification is a separate, explicit command.

Future verification layers can add targeted test selection, Pact, Testcontainers, sandboxed execution, and agent-proposed checks while preserving this boundary.
