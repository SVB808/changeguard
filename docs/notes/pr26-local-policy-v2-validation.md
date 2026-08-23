# PR 26 local grounded-selection-v2 validation

Local Ollama evaluation used `llama3.2:3b` with one unscored warmup per case and three measured runs per case on `synthesis-selection-v1`.

Two independent measured batches were identical across all 27 aligned runs:

- selector success: 27/27 in each batch
- grounding guardrail pass: 27/27 in each batch
- required evidence recall: 83.3%
- selection precision: 92.9%
- distractor selection rate: 7.1%
- distinct-consumer coverage: 81.8%
- verification-evidence retention: 100.0%
- within-batch mean pairwise Jaccard: 1.000
- cross-batch exact ordered match: 27/27 (100.0%)
- cross-batch exact set match: 27/27 (100.0%)
- cross-batch mean Jaccard: 1.000

The policy improved selectivity, verification retention, prompt-injection distractor rejection, and observed reproducibility on this development corpus, but it also regressed required-evidence recall and distinct-consumer coverage. In particular, the three-consumer case retained only one active consumer, and the two-consumer case omitted the semantic change fact.

These results are development-set measurements because the policy was designed after inspecting `synthesis-selection-v1`. They are not evidence of generalization. A fresh frozen corpus is required before stronger claims.
