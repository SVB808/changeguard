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

The default selector is deterministic so CI and offline use remain reproducible. V5.1 supports optional model-backed selectors through the same narrow contract: the model may choose evidence IDs only. OpenAI is the cloud provider path and Ollama is the local provider path. The `validate_selection` node rejects unknown, duplicate, or over-limit IDs before the deterministic renderer sees them.

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

## Local Ollama evidence selector

Ollama gives ChangeGuard a free local model path without API billing. On Windows, install Ollama, ensure the application is running, then pull the default ChangeGuard model:

```powershell
ollama pull llama3.2:3b
```

The local Ollama API is expected at `http://localhost:11434`. Run grounded local synthesis with:

```powershell
changeguard synthesize `
  --manifest manifest.json `
  --selector ollama
```

Override the local model when desired:

```powershell
changeguard synthesize `
  --manifest manifest.json `
  --selector ollama `
  --model qwen3:4b
```

A non-default Ollama API location can be supplied explicitly:

```powershell
changeguard synthesize `
  --manifest manifest.json `
  --selector ollama `
  --ollama-url http://127.0.0.1:11434
```

ChangeGuard calls Ollama's local `/api/chat` endpoint with streaming disabled, temperature `0`, and a JSON schema in the `format` field. The same schema is repeated in the prompt as additional grounding. The returned `selected_evidence_ids` are still revalidated by the LangGraph guardrail before deterministic rendering.

No OpenAI key is required for the Ollama selector. The repository-derived evidence stays on the machine running Ollama unless the user deliberately points `--ollama-url` at another server.

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

## Provider-independent provenance

Human output records selector provenance and model token usage when the provider reports it. JSON output includes `selector`, `model`, `input_tokens`, and `output_tokens`. Ollama maps `prompt_eval_count` and `eval_count` into the same token fields used by the OpenAI selector.

This lets later evaluation compare model-selection behavior, latency, and token usage without changing the deterministic analysis or rendering contract.

## Claim semantics

- `fact` is deterministic extracted or planned evidence.
- `inference` is a ChangeGuard impact/suppression conclusion.
- `verification` is the observed outcome of an explicitly executed local command.

A verification `FAILED` status means the selected command returned non-zero. A `PASSED` status means the selected command exited zero. Neither status is silently promoted into a universal production claim.

Model-backed selection does not change these semantics. It can only choose which existing evidence items are included in a synthesis; deterministic ChangeGuard code still controls the wording and caveats.
