# ADR 0016: Measure cold/normal-call and steady-state selector reproducibility separately

## Status

Accepted.

## Context

V5.2 introduced repeated evidence-selection evaluation, but its initial stability metric only compared runs inside one command invocation. Independent `llama3.2:3b` batches later produced materially different quality metrics even after Ollama sampling was configured with `temperature: 0` and an explicit `seed: 42`.

The observed pattern was especially important: in several cases the first call selected a different evidence set while later calls converged. A fixed seed therefore remains a useful sampling control, but it is not sufficient evidence that the full local inference path is deterministic.

Two measurement gaps remained:

1. first-call/cold behavior and later steady-state behavior were mixed together;
2. within-batch mean pairwise Jaccard could report a strong value without measuring whether an independent second batch reproduced the same selections.

## Decision

ChangeGuard V5.2.1 adds two explicit evaluation controls.

### Unscored per-case warmups

`changeguard evaluate-selector` accepts `--warmup-runs N`.

Warmup calls:

- happen before measured calls for each benchmark case;
- still pass through the same deterministic grounding validation;
- are reported for selector/guardrail availability;
- are excluded from quality metrics, measured latency percentiles, and measured token totals.

A run with `--warmup-runs 0` remains the cold/normal-call protocol. A run with one or more warmups is labeled steady-state. These are different protocols and should not be compared as if they were the same experiment.

### Cross-batch comparison

Two machine-readable `evaluate-selector --json` reports can be compared with:

```powershell
changeguard compare-selector-evals batch-a.json batch-b.json
```

The comparison requires matching corpus, selector, model, case count, measured runs per case, and warmup runs per case. It reports:

- aligned measured runs;
- comparable grounded run pairs;
- exact ordered evidence-ID list match rate;
- exact evidence-set match rate;
- mean cross-batch Jaccard similarity;
- right-minus-left deltas for the main quality metrics.

Exact ordered matching is intentionally stricter than set equality. Jaccard captures evidence-set overlap when exact reproduction fails.

## Consequences

- first-call effects can be measured instead of being silently hidden;
- steady-state results can be reported explicitly without rewriting cold-start history;
- cross-invocation reproducibility becomes a first-class metric rather than an inference from within-process stability;
- fixed-seed Ollama behavior is treated as empirically measured, not assumed deterministic;
- warmup cost is intentionally excluded from measured latency/token metrics and must not be confused with end-to-end runtime cost;
- the grounding boundary and no-autonomous-execution policy are unchanged.

## Claim discipline

Correct:

> On a controlled evidence-selection corpus, ChangeGuard measured both within-batch and independent cross-batch selector reproducibility. Fixed sampling parameters did not by themselves guarantee identical local-model selections.

Incorrect:

> Setting the Ollama seed makes ChangeGuard AI deterministic.
