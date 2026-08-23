# Canonical end-to-end demo

This workflow demonstrates the supported ChangeGuard vertical on a public ChangeGuard PR without granting the model source-code parsing or execution authority.

The demo PR is `SVB808/changeguard#16`, which contains the seeded client-style path-break benchmark used during development. The provider changes `GET /orders/{orderId}` to `GET /purchases/{orderId}` while Feign and RestTemplate consumers retain the previous route.

## 1. Analyze the public PR and create revision-bound plans

```powershell
changeguard pr `
  --repo SVB808/changeguard `
  --pr 16 `
  --verification-plan `
  --json |
  Out-File -Encoding utf8 manifest.json
```

The manifest records the exact PR base/head revisions. Every generated `VerificationPlan` also carries `expected_head`, binding later local execution to the revision that was analyzed.

The validated development run for this PR produced two endpoint-level consumer impacts and two targeted Maven verification plans. Treat that as a controlled project fixture, not a general production-accuracy claim.

## 2. Synthesize grounded evidence

Deterministic/offline:

```powershell
changeguard synthesize `
  --manifest manifest.json
```

Local Ollama selector:

```powershell
changeguard synthesize `
  --manifest manifest.json `
  --selector ollama `
  --model llama3.2:3b
```

The model may select only evidence IDs that ChangeGuard already produced. Unknown, duplicate and over-budget IDs are rejected, then deterministic policy closure preserves runtime-mandatory evidence before deterministic rendering.

## 3. Explicitly execute one targeted plan at the analyzed revision

This step executes project test code and is intentionally separate from remote PR analysis.

Check out the exact manifest head in a local clone:

```powershell
$manifest = Get-Content manifest.json -Raw | ConvertFrom-Json
git checkout $manifest.head
```

Then execute a single plan:

```powershell
changeguard verify-plan `
  --manifest manifest.json `
  --repo . `
  --plan-index 0
```

Before Maven is launched, ChangeGuard runs `git rev-parse HEAD`. If the workspace HEAD differs from `expected_head`, verification returns `ERROR` and refuses to execute project code.

To retain machine-readable process evidence:

```powershell
changeguard verify-plan `
  --manifest manifest.json `
  --repo . `
  --plan-index 0 `
  --json |
  Out-File -Encoding utf8 verification-result.json
```

A non-zero Maven exit is recorded as `FAILED`; it is not automatically labeled as causal proof that the PR is broken.

## 4. Synthesize again with verification evidence

```powershell
changeguard synthesize `
  --manifest manifest.json `
  --verification-result verification-result.json `
  --selector ollama `
  --model llama3.2:3b
```

This closes the intended evidence loop:

```text
exact PR revisions
    -> semantic + dependency + consumer-call evidence
    -> impact candidates
    -> revision-bound verification plan
    -> explicit local verification result
    -> grounded model evidence selection
    -> deterministic decision-critical closure
    -> deterministic report
```

## What this demo does not claim

- A passing targeted test proves universal safety.
- A failing targeted test proves causality.
- Controlled benchmark results equal production accuracy.
- Ollama/OpenAI is allowed to invent findings or execute project code.
- ChangeGuard currently understands every build system, dynamic HTTP client, database contract or messaging contract.
