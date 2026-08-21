# Grounded evidence synthesis

ChangeGuard V5 uses a LangGraph workflow that summarizes evidence already produced by deterministic analysis. It does not execute project code and it does not inspect additional repository content during synthesis.

## Workflow

```text
ChangeManifest + optional VerificationResult(s)
        ↓
collect_evidence
        ↓
select_evidence
        ↓
validate_selection
        ↓
render_report
```

The default selector is deterministic so CI and offline use remain reproducible. V5.1 adds an optional OpenAI-backed selector, but the selector interface stays intentionally narrow: it may choose evidence IDs only. The `validate_selection` node rejects unknown, duplicate, or over-limit IDs before the deterministic renderer sees them.

The model never receives authority to invent findings, execute code, fetch repository content, or author the final claims. Repository-derived evidence text is treated as untrusted data in the model instructions.

## CLI

First produce a manifest from deterministic PR analysis:

```powershell
changeguard pr `
  --repo SVB808/changeguard `
  --pr 16 `
  --verification-plan `
  --json | Out-File -Encoding utf8 manifest.json
```

PowerShell may add a UTF-8 BOM; synthesis accepts both ordinary UTF-8 and BOM-prefixed UTF-8.

Deterministic synthesis remains the default:

```powershell
changeguard synthesize --manifest manifest.json
```

Machine-readable output:

```powershell
changeguard synthesize --manifest manifest.json --json
```

An explicit local verification result can also be supplied. `--verification-result` is repeatable:

```powershell
changeguard synthesize `
  --manifest manifest.json `
  --verification-result feign-verification.json `
  --verification-result resttemplate-verification.json
```

## Optional OpenAI evidence selector

Install the optional provider dependency:

```powershell
python -m pip install -e ".[dev,ai]"
```

Set `OPENAI_API_KEY` in the environment, then opt into model selection explicitly:

```powershell
changeguard synthesize `
  --manifest manifest.json `
  --selector openai
```

The model can be overridden:

```powershell
changeguard synthesize `
  --manifest manifest.json `
  --selector openai `
  --model gpt-5.6-luna
```

The model response is constrained by a strict JSON schema containing only `selected_evidence_ids`. The graph then re-validates the IDs against the evidence ChangeGuard actually produced.

Human output records selector provenance and model token usage when the provider reports it. JSON output includes `selector`, `model`, `input_tokens`, and `output_tokens` fields so later evaluation can measure model latency/cost and selection behavior separately from deterministic analysis.

## Claim semantics

- `fact` is deterministic extracted or planned evidence.
- `inference` is a ChangeGuard impact/suppression conclusion.
- `verification` is the observed outcome of an explicitly executed local command.

A verification `FAILED` status means the selected command returned non-zero. A `PASSED` status means the selected command exited zero. Neither status is silently promoted into a universal production claim.

Model-backed selection does not change these semantics. It can only choose which existing evidence items are included in a synthesis; deterministic ChangeGuard code still controls the wording and caveats.
