# ADR-0008: Verification results are evidence, not causality claims

## Status
Accepted for the first verifier milestone.

## Decision
ChangeGuard records targeted verification as one of four process outcomes:

- `PASSED`: the selected command exited with status 0.
- `FAILED`: the selected command completed and exited non-zero.
- `ERROR`: ChangeGuard could not execute the command or workspace validation failed.
- `NOT_RUN`: a plan exists but execution has not occurred.

These labels describe the verification process, not the truth of the impact candidate.

A passing consumer test run can reduce concern but does not prove that every integration path is compatible. A failing run is supporting evidence that requires attribution; unrelated failures may exist.

## Consequence
The verifier remains consistent with ChangeGuard's evidence-first architecture. Later LLM or agent layers may summarize verification evidence, but they must not rewrite `PASSED` into "safe" or `FAILED` into "confirmed breakage" without additional causal evidence.
