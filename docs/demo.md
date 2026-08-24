# ChangeGuard canonical end-to-end demo

This demo shows the stable V1 flow without granting a model authority over source parsing or command execution.

## 1. Prepare the environment

```powershell
cd C:\path\to\changeguard
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
mvn -f analyzers/java-spring/pom.xml package
```

Optional local-model path:

```powershell
ollama list
```

The examples below use `llama3.2:3b` when Ollama is enabled.

## 2. Analyze a public PR

The repository's historical PR #16 is a useful canonical input:

```powershell
changeguard pr `
  --repo SVB808/changeguard `
  --pr 16 `
  --verification-plan `
  --json |
  Out-File -Encoding utf8 manifest.json
```

This performs remote analysis only. It does not execute project code from the target PR.

The resulting `ChangeManifest` contains exact base/head SHAs, deterministic semantic changes, dependency/call evidence, impact candidates, suppressed candidates, and revision-bound verification plans.

## 3. Inspect the manifest

```powershell
Get-Content manifest.json
```

For generated verification plans, confirm that `expected_head` equals the manifest's analyzed `head`.

## 4. Synthesize grounded evidence

Offline deterministic selection:

```powershell
changeguard synthesize --manifest manifest.json
```

Local model-backed evidence selection:

```powershell
changeguard synthesize `
  --manifest manifest.json `
  --selector ollama `
  --model llama3.2:3b
```

The model can only return evidence IDs already produced by ChangeGuard. Unknown IDs, duplicates, and over-budget selections fail validation. Deterministic policy closure restores runtime-mandatory evidence before rendering.

## 5. Optional explicit local verification

Verification is intentionally a separate user action. Check out the exact analyzed PR head in a local repository workspace first.

```powershell
changeguard verify-plan `
  --manifest manifest.json `
  --repo C:\path\to\target-repository `
  --plan-index 0 `
  --json |
  Out-File -Encoding utf8 verification-result-0.json
```

Before Maven is resolved or project code runs, ChangeGuard executes `git rev-parse HEAD`. If the workspace revision differs from the plan's `expected_head`, the result is `ERROR` and the command is not executed.

## 6. Synthesize with verification evidence

```powershell
changeguard synthesize `
  --manifest manifest.json `
  --verification-result verification-result-0.json `
  --selector ollama `
  --model llama3.2:3b
```

A `FAILED` command is reported as process evidence, not automatic causal proof. A `PASSED` command confirms only that the selected command exited zero.

## 7. Run the stable V1 release evaluation

Offline release gate:

```powershell
changeguard evaluate-release `
  --selector deterministic `
  --runs 3 `
  --strict
```

Optional local-model measurement:

```powershell
changeguard evaluate-release `
  --selector ollama `
  --model llama3.2:3b `
  --warmup-runs 1 `
  --runs 3
```

The release report separates deterministic impact correctness, raw selector quality, effective post-policy quality, grounding, runtime policy-mandatory retention, and corpus-policy diagnostics.

## 8. Suggested 3-minute portfolio walkthrough

1. Start with the problem: a provider-side API change can break consumers in files untouched by the PR.
2. Show the generated manifest and point out exact base/head revisions, semantic changes, consumer-call evidence, and targeted verification plans.
3. Run grounded synthesis and explain that the model chooses only from existing evidence IDs; it does not inspect arbitrary source or execute commands.
4. Show revision-bound verification and explain why `HEAD` mismatch is a hard refusal instead of a warning.
5. End with `evaluate-release` and distinguish controlled-corpus/runtime-shaped metrics from production accuracy.

## Safety boundaries demonstrated

```text
remote PR
  -> deterministic source/evidence analysis
  -> impact inference
  -> reviewable revision-bound plan
  -> optional explicit local execution
  -> typed verification evidence
  -> constrained evidence-ID model selection
  -> deterministic grounding + policy closure
  -> deterministic report
```

ChangeGuard does not silently execute remote code, does not let the model invent evidence, and does not describe controlled benchmark results as production accuracy.
