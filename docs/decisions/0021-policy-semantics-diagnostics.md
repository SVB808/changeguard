# ADR 0021: Measure runtime policy invariants separately from benchmark labels

## Status

Accepted

## Context

V5.3 measures raw selector quality and post-policy effective quality on the same provider call. Holdout evaluation showed that benchmark-required evidence and runtime policy guarantees are not always the same concept.

Two controlled-corpus patterns exposed this distinction:

- a required semantic-change fact can lack shared source-path provenance with active impact evidence, so deterministic decision-critical closure cannot infer that it belongs to the impact;
- a corpus can label an `impact` evidence item as a distractor even though runtime policy treats every active impact item as mandatory.

Changing runtime policy solely to maximize corpus required-evidence recall would blur the distinction between summary-quality labels and safety invariants. Editing an already-inspected holdout corpus would also contaminate the evaluation history.

## Decision

Expose the runtime policy's mandatory evidence IDs through one shared helper and use it both for synthesis closure and evaluation.

`evaluate-selector-policy` now reports two separate concepts:

1. benchmark quality metrics such as required-evidence recall, selection precision, distractor rate, consumer coverage, and verification retention;
2. runtime policy-mandatory retention before and after deterministic closure.

The evaluator also emits corpus-policy diagnostics when benchmark semantics conflict with or cannot be guaranteed by runtime policy:

- `distractor-is-policy-mandatory` when a corpus labels an evidence ID as a distractor but runtime closure must preserve it;
- `required-semantic-not-provenance-linked` when required semantic evidence does not share source provenance with active impact evidence and therefore is not guaranteed by closure.

The existing corpus is not rewritten after observation.

## Consequences

- Raw LLM quality remains observable rather than being hidden behind deterministic closure.
- Runtime invariant coverage can be stated separately and more precisely.
- Benchmark-policy mismatches become explicit data instead of motivating ad-hoc policy changes.
- Controlled-corpus required-evidence recall may remain below 100% even when runtime policy-mandatory retention is 100%.
- A future production-like corpus should preserve the same provenance shapes produced by `collect_evidence()` when testing runtime guarantees.
