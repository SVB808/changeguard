# ADR 0014: Evaluate model evidence selection independently

## Status

Accepted for V5.2.

## Context

ChangeGuard V5.1 permits a model-backed selector to choose from deterministic evidence IDs. The model does not author findings, execute code, or bypass deterministic grounding validation.

The existing `rest-impact-v3` benchmark measures deterministic change-impact behavior. Reusing those metrics to describe model quality would conflate two different layers and encourage misleading claims.

Model selection also introduces failure modes that deterministic impact analysis does not have:

- provider/network failure,
- malformed or ungrounded output,
- omission of decision-critical evidence,
- retention of irrelevant evidence,
- loss of one consumer in a multi-consumer change,
- failure to prioritize verification evidence,
- instability across repeated runs,
- prompt-injection-like repository strings competing for attention.

## Decision

Introduce a separate, versioned evidence-selection benchmark and CLI.

Each benchmark case contains already-produced `EvidenceItem` records plus explicit labels for required, optional, and distractor evidence. Coverage groups identify distinct consumers that should remain represented. Verification-critical IDs identify observed verification evidence that should be retained.

The evaluator records provider success separately from deterministic grounding validation. Quality metrics are computed only for guardrail-valid selections.

The initial metrics are:

- selector success rate,
- grounding-guardrail pass rate,
- required-evidence recall,
- selection precision,
- distractor-selection rate,
- distinct-consumer coverage,
- verification-evidence retention,
- repeated-run Jaccard stability,
- selector latency,
- provider token counts when available.

Undefined ratios remain nullable and are rendered as `N/A`.

`--strict` gates selector availability and grounding only. V5.2 does not introduce arbitrary model-quality pass thresholds.

Live model evaluation remains explicit and is not required in ordinary CI. CI evaluates the deterministic baseline and uses fake provider selectors for evaluator/CLI behavior without network or API credentials.

## Consequences

Positive:

- deterministic impact accuracy and model-selection quality cannot be accidentally conflated,
- Ollama and OpenAI can be compared on identical labels,
- prompt-injection-like data is evaluated at the exact model boundary,
- model stability, latency, and token usage become measurable,
- future selector changes can be justified with data rather than anecdotes.

Tradeoffs:

- the corpus labels are human-authored and remain controlled rather than production ground truth,
- acceptable evidence can be non-unique, so exact-match accuracy is intentionally not the primary metric,
- model results may vary by model version, runtime, hardware, and repeated invocation,
- live cloud evaluation may incur cost.

## Non-goals

V5.2 does not:

- measure production breakage prediction accuracy,
- allow the model to invent evidence,
- execute verification automatically,
- add autonomous remediation or PR mutation,
- treat a controlled corpus score as production reliability.
