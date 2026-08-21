# Grounded evidence synthesis

ChangeGuard V5.0 introduces a LangGraph workflow that summarizes evidence already produced by deterministic analysis. It does not execute project code and it does not inspect additional repository content.

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

The default selector is deterministic so CI remains reproducible. The selector interface is intentionally narrow: it may choose evidence IDs, but the final claims are rendered from ChangeGuard-produced evidence. This is the boundary a later model-backed selector must preserve.

## CLI

First produce a manifest from deterministic PR analysis:

```powershell
changeguard pr `
  --repo SVB808/changeguard `
  --pr 16 `
  --verification-plan `
  --json > manifest.json
```

Then synthesize it:

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

## Claim semantics

- `fact` is deterministic extracted or planned evidence.
- `inference` is a ChangeGuard impact/suppression conclusion.
- `verification` is the observed outcome of an explicitly executed local command.

A verification `FAILED` status means the selected command returned non-zero. A `PASSED` status means the selected command exited zero. Neither status is silently promoted into a universal production claim.
