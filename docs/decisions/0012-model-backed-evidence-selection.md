# ADR 0012: Constrain model participation to grounded evidence selection

## Status

Accepted.

## Context

V5.0 established a LangGraph synthesis workflow in which evidence collection, selection validation, and final report rendering are explicit graph nodes. The default selector is deterministic and all rendered claims come from ChangeGuard-produced evidence.

The next step is to introduce an actual model call without weakening that grounding contract. Allowing a model to write free-form risk findings would make it difficult to distinguish deterministic facts from generated claims, complicate evaluation, and create prompt-injection risk from repository-derived strings.

## Decision

V5.1 adds an optional OpenAI-backed selector that can choose only existing ChangeGuard evidence IDs.

The model receives typed evidence records containing IDs, tiers, categories, statements, and source paths. Repository-derived values are explicitly treated as untrusted data. The model is instructed not to follow instructions found inside evidence content and not to invent risk severities, production outcomes, verification results, or new evidence IDs.

The provider response uses a strict JSON schema with one field: `selected_evidence_ids`. Selection remains bounded by ChangeGuard's `MAX_SELECTED_EVIDENCE` limit.

The LangGraph `validate_selection` node remains authoritative after the model call. It rejects unknown IDs, duplicate IDs, and over-limit selections. The final headline and evidence wording continue to be rendered deterministically from validated ChangeGuard evidence; the model does not author the report.

OpenAI is an optional dependency rather than a core runtime dependency. Deterministic synthesis remains the default and requires no API key. Model synthesis is enabled explicitly with `--selector openai`.

The synthesis report records selector provenance, model name, and provider-reported input/output token counts when available. This creates the basis for later latency/cost and selection-quality evaluation.

## Consequences

ChangeGuard now contains a real model-backed LangGraph step while keeping deterministic analysis as the source of truth. Model failures, authentication failures, malformed structured responses, and guardrail violations fail closed instead of falling back silently to ungrounded output.

The model can improve focus and prioritization but cannot add facts. This intentionally limits agent autonomy until selection quality is measured against labeled cases.

The OpenAI path still depends on an external API and therefore is not part of ordinary CI. CI uses fake provider responses to validate request shape, structured-output parsing, provenance, and guardrails without requiring secrets or network access.
