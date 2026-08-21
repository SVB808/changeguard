# ADR 0006: Structural route matching for consumer evidence

## Status

Accepted for V4.1.

## Context

V2.2 initially compared normalized consumer and provider routes primarily by structural path-variable equality. The V4.1 adversarial corpus adds cases where raw route strings are not sufficient:

- query strings appear on consumer URIs,
- provider mappings may use `ANY` HTTP method semantics,
- Spring routes may contain `*` or `**` wildcards,
- path-variable names can differ between provider and consumer code.

Treating these as literal strings would suppress legitimate endpoint-level evidence and create false negatives in the controlled benchmark.

## Decision

ChangeGuard will keep endpoint matching deterministic and evidence-based while making route comparison structural.

For the previous provider contract:

- query strings are removed from consumer paths before route comparison,
- path-variable declarations match one path segment regardless of variable name,
- provider HTTP method `ANY` matches a concrete consumer method,
- `*` matches within one slash-delimited path segment,
- `**` can match across path segments,
- literal route characters remain case-sensitive.

This logic is used only to decide whether explicit consumer-call evidence supports an endpoint-level impact candidate. It does not claim runtime reachability or production failure.

## Rejected alternatives

### Raw string equality

Too strict. It misses equivalent path-variable names and supported Spring wildcard routes.

### LLM-based route interpretation

Unnecessary and less reproducible for syntax that can be handled deterministically.

### Full Spring runtime route resolution

More faithful but much heavier. It would require application context construction and potentially executing target-repository code, which violates the current remote-analysis safety boundary.

## Limitations

The V4.1 matcher does not interpret arbitrary regex constraints embedded inside path-variable declarations. It also does not model gateway rewrite filters, custom path matchers, or dynamically constructed consumer URIs.

Those cases should remain explicit benchmark gaps rather than being guessed.
