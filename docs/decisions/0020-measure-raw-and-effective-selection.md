# ADR 0020: Measure raw and effective evidence selection separately

## Status

Accepted for evaluation.

## Context

The frozen `synthesis-selection-v2` evaluation showed that `grounded-selection-v2` can be fully grounded and highly stable while still omitting decision-critical evidence in repeatable ways. ADR 0019 therefore added a deterministic decision-critical policy closure before synthesis rendering.

Once that closure exists, a single post-policy score would hide model weaknesses, while a raw-model score alone would understate the guarantees of the runtime synthesis path.

## Decision

Add an explicit `evaluate-selector-policy` command that evaluates the raw selector output and the effective post-policy selection from the **same provider call**.

The evaluator reports two quality views:

1. raw selector quality, including required-evidence recall, precision, distractor rate, consumer coverage, verification retention, and within-batch stability;
2. effective quality after deterministic decision-critical closure using the same labels.

It also reports policy intervention counts, evidence IDs added/dropped by closure, provider latency, and token usage.

Warmup runs remain unscored. The raw `evaluate-selector` command is unchanged and remains the authoritative benchmark for model-only behavior.

## Why the same provider call matters

Calling a model twice and comparing the first output with the post-policy form of the second output would confound policy impact with model nondeterminism. Raw and effective metrics therefore must be derived from one selector response per measured run.

## Consequences

- raw model weaknesses remain visible;
- deterministic runtime guarantees can be quantified independently;
- policy intervention frequency becomes measurable rather than anecdotal;
- distractor evidence that survives closure remains visible instead of being silently reclassified as a success;
- effective metrics still describe a controlled evidence-selection corpus, not end-to-end production accuracy;
- future relevance filtering can be evaluated as a separate deterministic policy rather than being mixed into decision-critical coverage closure.

## Expected first use

Run `synthesis-selection-v2` with the already frozen `grounded-selection-v2` prompt and compare raw versus effective metrics. The existing holdout run suggests decision-critical closure should improve required-evidence recall and consumer coverage, while unrelated suppressed/security distractors may remain and should continue to count against precision.
