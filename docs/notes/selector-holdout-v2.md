# Selection holdout v2

`synthesis-selection-v2` was frozen after `grounded-selection-v2` was implemented and before live model evaluation on these cases.

Use it with an explicit corpus path:

```powershell
changeguard evaluate-selector `
  --corpus benchmarks/evaluation/synthesis-selection-v2.json `
  --selector ollama `
  --model llama3.2:3b `
  --warmup-runs 1 `
  --runs 3 `
  --details
```

For the first evaluation, do not change the prompt, labels, or corpus after seeing model results. Record the output before deciding whether another policy revision is warranted. If results from this corpus are later used to tune the selector, stop calling v2 unseen holdout data for subsequent revisions.
