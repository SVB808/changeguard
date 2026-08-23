# ADR 0013: Add Ollama as a local evidence-selection provider

## Status

Accepted for the V5.1 provider layer.

## Context

The first model-backed ChangeGuard selector uses OpenAI Structured Outputs, but live cloud inference requires API billing. The synthesis architecture itself is intentionally provider-independent: a selector receives typed ChangeGuard evidence and may return only a bounded list of evidence IDs.

A free local path is useful for development, privacy-sensitive repositories, offline demonstrations, and model-selection evaluation. It must not weaken the grounding contract established by ADR 0011 and ADR 0012.

## Decision

Add an Ollama-backed `EvidenceSelector` implementation using Ollama's local `/api/chat` endpoint.

The Ollama selector:

- defaults to `http://localhost:11434`,
- defaults to the small `llama3.2:3b` model,
- sends only already-derived ChangeGuard evidence records,
- treats repository-derived strings as untrusted data,
- disables streaming,
- uses temperature `0`,
- supplies the evidence-selection JSON schema through Ollama's `format` field and repeats it in the prompt,
- parses only `selected_evidence_ids`,
- records provider/model and prompt/output token counts when Ollama reports them,
- still relies on ChangeGuard's downstream guardrail for unknown IDs, duplicates, and the maximum selection count.

The implementation uses Python's standard HTTP library so Ollama does not add another Python runtime dependency. OpenAI remains optional through the existing `ai` extra.

## Consequences

ChangeGuard can now demonstrate a real model-backed LangGraph path without paid API access while preserving the same deterministic evidence and rendering boundaries.

The provider layer is now practically testable across deterministic, local-model, and cloud-model modes. This creates a stronger basis for V5.2 selector evaluation because the same labeled selection cases can be run against multiple providers.

Local inference is not automatically better or safer than cloud inference. Model quality depends on the installed Ollama model and local hardware, and a user can deliberately point the selector at a non-local Ollama server. The report therefore records selector and model provenance rather than treating providers as interchangeable in measured results.
