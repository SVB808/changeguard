# V5.2 evidence-selection evaluation

ChangeGuard evaluates the model-backed evidence selector separately from deterministic change-impact analysis.

This separation matters because the two layers answer different questions:

- `changeguard evaluate` measures deterministic impact/refinement and verification-plan decisions on the REST compatibility corpus.
- `changeguard evaluate-selector` measures which already-produced evidence items a selector keeps for synthesis.

A strong result from one evaluator must not be presented as a result from the other.

## Controlled corpus

The initial selection corpus is `benchmarks/evaluation/synthesis-selection-v1.json`.

Each case labels every evidence item exactly once as:

- `required_evidence_ids`: decision-critical evidence the selector should retain,
- `optional_evidence_ids`: useful supporting context that is acceptable to retain,
- `distractor_evidence_ids`: irrelevant or adversarial context that should not consume the selection budget.

Cases also label distinct-consumer coverage groups and verification-critical evidence where applicable.

The first corpus includes:

- two-consumer endpoint impact,
- failed verification priority,
- passed verification priority,
- suppressed-only impact context,
- semantic-only evidence,
- prompt-injection-like repository text,
- three-consumer coverage,
- selection-budget pressure above the 12-item cap,
- empty evidence.

The prompt-injection case is intentionally repository-derived *data*. It does not grant the model new authority; the same deterministic unknown-ID/duplicate/selection-limit guardrail still runs after every model response.

## Metrics

`evaluate-selector` reports:

- selector success rate,
- deterministic grounding-guardrail pass rate,
- required-evidence recall,
- selection precision (`required + optional` among selected items),
- distractor-selection rate,
- distinct-consumer coverage,
- verification-evidence retention,
- mean pairwise Jaccard similarity across repeated runs,
- p50/p95 selector latency,
- provider input/output token totals when the provider reports them.

Undefined ratios are reported as `N/A` rather than silently treated as zero. Stability is `N/A` unless `--runs` is at least 2.

## Deterministic baseline

The deterministic selector remains useful as a reproducible baseline:

```powershell
changeguard evaluate-selector --selector deterministic --runs 3 --details
```

It is expected to be perfectly stable and grounded, but it is not designed to be maximally selective. In particular, it may retain distractors and can lose lower-priority evidence when more than 12 items compete for the selection budget.

That is intentional: V5.2 evaluates whether a model-backed selector improves evidence prioritization without weakening grounding.

## Local Ollama evaluation

With Ollama running locally:

```powershell
changeguard evaluate-selector `
  --selector ollama `
  --model llama3.2:3b `
  --runs 3 `
  --details
```

`--runs 3` is a useful first stability check. Model evaluation is explicit because it can be slower and, for cloud providers, may incur cost.

Machine-readable output:

```powershell
changeguard evaluate-selector `
  --selector ollama `
  --runs 3 `
  --json
```

## OpenAI evaluation

The same corpus can be evaluated through the optional OpenAI selector when API billing is active:

```powershell
changeguard evaluate-selector `
  --selector openai `
  --runs 3
```

OpenAI and Ollama are evaluated against identical labels and downstream deterministic guardrails.

## Strict mode

```powershell
changeguard evaluate-selector --selector ollama --strict
```

`--strict` is deliberately a **safety/availability gate**, not a model-quality gate. It fails when:

- a selector invocation fails, or
- a returned selection fails deterministic grounding validation.

It does not currently fail on a chosen quality threshold such as 95% required recall. Quality thresholds should be introduced only after enough controlled and live measurements exist to justify them.

## Claim discipline

Correct wording:

> Evidence-selection quality was measured on the controlled `synthesis-selection-v1` corpus, separately from deterministic impact-detection metrics.

Do not say:

> The model is X% accurate at predicting production breakage.

The selector does not predict production breakage. It ranks already-produced ChangeGuard evidence for a grounded synthesis.
