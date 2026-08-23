# ADR 0019: Enforce decision-critical evidence after model selection

## Status

Accepted for evaluation.

## Context

The first frozen `synthesis-selection-v2` evaluation of `grounded-selection-v2` showed that prompt hardening improved stability but did not make the model a reliable owner of hard coverage invariants.

The local Ollama holdout-style run was fully grounded and perfectly stable across the recorded batches, but it still omitted decision-critical evidence in repeatable ways. In particular, one verification-plus-two-consumer case consistently dropped the second active consumer, and a four-consumer case consistently omitted the shared semantic change. The same evaluation also showed that unrelated suppressed/security context could still be selected.

This is an architectural signal: deterministic evidence that affects the decision should not be optional merely because the language model omitted its ID.

## Decision

Add a deterministic decision-critical policy closure between selector output validation and report rendering.

The raw selector output is still validated first. ChangeGuard then deterministically preserves:

1. every supplied `verification_result` evidence item;
2. every active `impact` evidence item;
3. every `semantic_change` fact whose source-path provenance intersects an active impact's provenance.

Model-selected evidence remains eligible as optional context after those mandatory items. If the combined set exceeds the synthesis evidence budget, optional selector context is dropped first in the selector's original order.

If mandatory evidence by itself exceeds `MAX_SELECTED_EVIDENCE`, ChangeGuard fails closed instead of silently hiding active impact or verification evidence.

The effective selection records which IDs were added or dropped by policy closure for auditability.

## Why this boundary

The language model is good at choosing concise context, but the V5.2/V5.2.1 experiments show that it should not be the sole authority for consumer coverage or verification retention. Those invariants are derivable from ChangeGuard's deterministic evidence graph and belong on the deterministic side of the boundary.

This preserves the project principle:

> evidence -> inference -> verification -> grounded synthesis

The model remains a bounded evidence-ID selector rather than an authority that can erase deterministic findings.

## Consequences

- active impact and verification evidence can no longer disappear because of model under-selection;
- linked semantic change facts are retained when provenance ties them to active impact evidence;
- optional model context is still useful, but it is subordinate to deterministic coverage;
- the existing `evaluate-selector` command continues to measure raw selector behavior, not post-closure effective behavior;
- distractor filtering is not solved by this ADR; relevance filtering should be evaluated separately rather than mixed into the first closure change;
- a future structured/paginated synthesis format is needed for changes whose decision-critical evidence exceeds the current 12-item budget.

## Evaluation plan

1. Keep the raw selector benchmarks unchanged so model quality remains observable.
2. Add unit coverage for closure, budget handling, and fail-closed behavior.
3. Re-run the existing synthesis path with Ollama and verify that omitted active impacts/verification evidence are restored by the deterministic layer.
4. Add an effective-selection evaluator in a later milestone if we want aggregate post-closure recall/precision metrics without conflating them with raw model quality.
