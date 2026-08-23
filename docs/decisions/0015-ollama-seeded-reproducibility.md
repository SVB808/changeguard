# ADR 0015: Pin an explicit Ollama generation seed

## Status

Accepted.

## Context

V5.2 local evaluation exposed a reproducibility gap. Two independent `llama3.2:3b` evaluation batches used the same corpus, temperature `0`, model, and machine, yet produced slightly different evidence selections. Within one batch, mean pairwise Jaccard was `0.963`; in a second batch it was `1.000`.

The grounding boundary remained intact in both batches: every returned ID was validated against deterministic ChangeGuard evidence. The difference was selection quality, not evidence invention.

Ollama exposes a generation `seed` option specifically for reproducible outputs. Relying on temperature alone leaves the sampling setup underspecified for evaluation.

## Decision

`OllamaEvidenceSelector` now sends both:

```json
{
  "temperature": 0,
  "seed": 42
}
```

The default seed is a named constant and can be overridden when constructing the selector. CLI behavior remains unchanged because ordinary `--selector ollama` calls inherit the explicit default seed.

This is an evaluation/reproducibility control, not a claim that every runtime, hardware backend, or Ollama version will be bit-for-bit deterministic. Reproducibility must still be measured empirically.

## Consequences

- repeated local evaluation has a fully specified sampling seed;
- quality comparisons between selector changes are less confounded by sampling variance;
- the existing deterministic grounding guardrail remains authoritative;
- no network, API-key, or autonomy boundary changes are introduced;
- V5.2 should be re-run in at least two independent batches before making a stronger stability claim.
