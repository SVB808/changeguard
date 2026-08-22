# ADR 0018: Freeze an unseen evidence-selection corpus before further policy tuning

## Status

Accepted.

## Context

`grounded-selection-v2` was designed after inspecting failures on `synthesis-selection-v1`. Live local evaluation on that same corpus showed a useful but mixed result: selectivity and reproducibility improved, while required-evidence recall and distinct-consumer coverage regressed in some cases. Because the policy was tuned after observing v1, further claims based only on v1 would be development-set claims.

The model selector already exposes `grounded-selection-v2` in code, but V5.2.1 evaluation JSON does not yet persist selector-policy provenance. Until that schema is hardened, policy/version context must be recorded with benchmark artifacts and comparisons must not silently mix reports produced from different policy branches.

## Decision

1. Freeze a new `synthesis-selection-v2` corpus before making any additional prompt-policy change.
2. Treat the first evaluation of `grounded-selection-v2` on this new corpus as a holdout-style measurement. Once results from v2 are used to tune the policy, v2 stops being an unseen holdout for that policy family and must be described as development data thereafter.
3. Keep deterministic grounding validation unchanged.
4. Track persistence of selector-policy provenance as a separate schema-hardening follow-up rather than changing the evaluation schema in the same PR that freezes the holdout.

The v2 corpus uses new combinations rather than simple rewrites of v1 cases. It includes mixed verification/consumer scenarios, relevant-vs-unrelated security evidence, higher consumer fan-out, suppressed-vs-active competition, dense distractors, and repository-derived instruction-like text.

## Consequences

- `synthesis-selection-v1` remains a development corpus for `grounded-selection-v2`;
- the first v2 run is useful as controlled unseen-combination evidence, but only until the result is inspected and used for tuning;
- policy/version provenance must be preserved operationally until it becomes a first-class report field;
- no production-accuracy claim follows from either corpus;
- no model gains permission to invent evidence, execute code, fetch repository content, or mutate GitHub.

## Claim discipline

Correct:

> `grounded-selection-v2` was first evaluated on a separately frozen controlled corpus containing unseen evidence combinations.

Incorrect:

> ChangeGuard's model selector generalizes to production repositories.
