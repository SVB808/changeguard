# V5.2.1 evidence-selection evaluation

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
- mean pairwise Jaccard similarity across repeated measured runs,
- p50/p95 selector latency,
- provider input/output token totals when the provider reports them.

Undefined ratios are reported as `N/A` rather than silently treated as zero. Within-batch stability is `N/A` unless `--runs` is at least 2.

## Deterministic baseline

The deterministic selector remains useful as a reproducible baseline:

```powershell
changeguard evaluate-selector --selector deterministic --runs 3 --details
```

It is expected to be perfectly stable and grounded, but it is not designed to be maximally selective. In particular, it may retain distractors and can lose lower-priority evidence when more than 12 items compete for the selection budget.

That is intentional: the model-backed evaluation asks whether a selector improves evidence prioritization without weakening grounding.

## Local Ollama evaluation

With Ollama running locally:

```powershell
changeguard evaluate-selector `
  --selector ollama `
  --model llama3.2:3b `
  --runs 3 `
  --details
```

This is the cold/normal-call protocol: no unscored warmup is performed. It intentionally preserves first-call behavior.

Machine-readable output:

```powershell
changeguard evaluate-selector `
  --selector ollama `
  --model llama3.2:3b `
  --runs 3 `
  --json |
  Out-File -Encoding utf8 ollama-cold-batch.json
```

## Steady-state evaluation with warmups

V5.2.1 can explicitly separate later steady-state behavior from first-call effects:

```powershell
changeguard evaluate-selector `
  --selector ollama `
  --model llama3.2:3b `
  --warmup-runs 1 `
  --runs 3 `
  --details
```

Warmups are performed once per benchmark case before measured runs. They still pass through deterministic grounding validation, but they are **unscored** and excluded from:

- required/optional/distractor quality metrics,
- measured latency percentiles,
- measured provider token totals.

A steady-state report is therefore a different protocol from a cold/normal-call report. Do not compare them as if only the model changed.

## Cross-batch reproducibility

Within-command Jaccard does not prove that an independent second invocation reproduces the same selections. Save two reports produced with the same protocol and compare them directly:

```powershell
changeguard compare-selector-evals `
  ollama-steady-batch-a.json `
  ollama-steady-batch-b.json
```

The comparator requires matching corpus, selector, model, case count, measured runs/case, and warmups/case. It reports:

- aligned measured runs,
- comparable grounded run pairs,
- exact ordered evidence-ID list match rate,
- exact evidence-set match rate,
- mean cross-batch Jaccard similarity,
- right-minus-left deltas for the main quality metrics.

The ordered-list metric is deliberately stricter than set equality. Jaccard shows how much the selected evidence overlaps even when exact reproduction fails.

PowerShell BOM-prefixed UTF-8 evaluation JSON is accepted by the comparator.

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

- a warmup or measured selector invocation fails, or
- a returned warmup or measured selection fails deterministic grounding validation.

It does not currently fail on a chosen quality threshold such as 95% required recall. Quality thresholds should be introduced only after enough controlled and live measurements exist to justify them.

## Reproducibility discipline

The Ollama selector uses `temperature: 0` and an explicit default seed as sampling controls. Local validation showed that these settings do **not** guarantee identical structured-output selections across independent invocations in the tested runtime. ChangeGuard therefore measures reproducibility empirically instead of inferring it from configuration.

See ADR 0015 for the seed control and ADR 0016 for the cold-vs-steady-state and cross-batch protocol.

## Claim discipline

Correct wording:

> Evidence-selection quality and reproducibility were measured on the controlled `synthesis-selection-v1` corpus, separately from deterministic impact-detection metrics.

Do not say:

> The model is X% accurate at predicting production breakage.

The selector does not predict production breakage. It ranks already-produced ChangeGuard evidence for a grounded synthesis.
