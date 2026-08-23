# Release-candidate evaluation

`changeguard evaluate-release` is the consolidated V1 readiness command. It deliberately combines two different controlled evaluations without collapsing their meanings.

## Deterministic impact gate

The first section runs the versioned `rest-impact-v3` corpus through ChangeGuard's deterministic impact/refinement/planning core. The current CI gate requires exact disposition + verification-plan agreement for all 24 controlled cases.

This is not a production-accuracy claim. The corpus is small and intentionally controlled, and the latency excludes GitHub access, JVM parsing, Maven execution and model inference.

## Runtime-shaped synthesis gate

The second section uses `synthesis-selection-runtime-v1`. These cases are built from typed `ChangeManifest` and `VerificationResult` fixtures and then passed through the same `collect_evidence()` function used by runtime synthesis.

That distinction matters: active impact evidence contains the provider changed-file provenance that production ChangeGuard attaches, so deterministic semantic-to-impact linkage is evaluated against realistic evidence shape rather than hand-authored source paths.

The report separates:

- raw selector quality,
- post-policy effective quality,
- grounding success,
- verification-evidence retention,
- distinct-consumer coverage,
- runtime policy-mandatory retention,
- corpus-policy diagnostics.

The runtime gate requires 100% effective retention of policy-mandatory evidence. It does **not** require an LLM to achieve perfect general summary precision or recall.

## Offline release gate

```powershell
changeguard evaluate-release `
  --selector deterministic `
  --runs 3 `
  --strict
```

This path is suitable for CI because it has no network/model dependency.

## Local model release evaluation

```powershell
changeguard evaluate-release `
  --selector ollama `
  --model llama3.2:3b `
  --warmup-runs 1 `
  --runs 3
```

This measures the local model on production-shaped evidence while still reporting deterministic effective-policy guarantees separately.

OpenAI can be selected explicitly when an API key and active billing are available:

```powershell
changeguard evaluate-release `
  --selector openai `
  --runs 3
```

Live provider evaluation is never required by CI.

## Release gates

The consolidated command reports four gates:

1. deterministic impact corpus exactness,
2. selector and effective grounding,
3. 100% effective runtime policy-mandatory retention,
4. absence of corpus-policy semantic contradictions in the runtime-shaped corpus.

The overall gate passes only if all four pass.
