# ADR 0018: Freeze an unseen evidence-selection corpus before further policy tuning

## Status

Accepted.

## Context

`grounded-selection-v2` was designed after inspecting failures on `synthesis-selection-v1`. Live local evaluation on that same corpus showed a useful but mixed result: selectivity and reproducibility improved, while required-evidence recall and distinct-consumer coverage regressed in some cases. Because the policy was tuned after observing v1, further claims based only on v1 would be development-set claims.

The evaluation reports also need to preserve the active model-selection policy version. Without that provenance, two reports produced by different prompt policies can look protocol-compatible even though the selector behavior changed.

## Decision

1. Persist selector policy provenance in evidence-selection evaluation reports and treat it as part of the comparison protocol.
2. Freeze a new `synthesis-selection-v2` corpus before making any additional prompt-policy change.
3. Treat the first evaluation of `grounded-selection-v2` on this new corpus as a holdout-style measurement. Once results from v2 are used to tune the policy, v2 stops being an unseen holdout for that policy family and must be described as a development corpus thereafter.
4. Keep deterministic grounding validation unchanged.

The v2 corpus uses new combinations rather than simple rewrites of v1 cases. It includes mixed verification/consumer scenarios, relevant-vs-unrelated security evidence, higher consumer fan-out, suppressed-vs-active competition, dense distractors, and repository-derived instruction-like text.

## Consequences

- reports can no longer silently compare different model-selection policies;
- `synthesis-selection-v1` remains a development corpus for `grounded-selection-v2`;
- the first v2 run is useful for generalization evidence, but only until the result is inspected and used for tuning;
- no production-accuracy claim follows from either corpus;
- no model gains permission to invent evidence, execute code, fetch repository content, or mutate GitHub.

## Claim discipline

Correct:

> `grounded-selection-v2` was first evaluated on a separately frozen controlled corpus containing unseen evidence combinations.

Incorrect:

> ChangeGuard's model selector generalizes to production repositories.
