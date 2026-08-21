# ADR 0011: Ground LangGraph synthesis in ChangeGuard evidence IDs

## Status

Accepted.

## Context

ChangeGuard now has deterministic evidence for semantic REST changes, repository-scoped service dependencies, explicit WebClient/OpenFeign/RestTemplate calls, impact candidates, Maven verification plans, and explicit local verification results.

Adding an agent layer too early can weaken that evidence model if a language model is allowed to invent findings, execute code implicitly, or turn process outcomes into stronger claims than the verifier supports.

## Decision

The first LangGraph slice is an evidence-synthesis workflow with four explicit nodes:

1. `collect_evidence` converts the supplied `ChangeManifest` and optional `VerificationResult` objects into typed evidence items.
2. `select_evidence` chooses evidence IDs only. The default selector is deterministic and offline; a future model-backed selector must implement the same contract.
3. `validate_selection` rejects unknown or duplicate evidence IDs and bounds the selected evidence count.
4. `render_report` produces the final report from validated evidence using deterministic wording and explicit caveats.

Evidence is separated into three tiers:

- **fact**: deterministic extracted facts and reviewable plans,
- **inference**: ChangeGuard impact/suppression conclusions derived from deterministic facts,
- **verification**: process evidence from an explicitly executed local verification command.

The graph does not fetch additional repository content, execute project code, or allow the selector to emit free-form findings. `FAILED` remains a non-zero command result rather than automatic proof of causal or production breakage; `PASSED` remains an exit-zero result rather than proof that a change is universally safe.

## Consequences

This gives ChangeGuard a real LangGraph orchestration boundary without making the LLM the source of truth. A later model adapter can rank or focus evidence while the guardrail still limits it to ChangeGuard-produced IDs. More capable agents can be added after their tool permissions and evaluation criteria are explicit.

The tradeoff is that V5.0 is intentionally conservative: the default synthesis is deterministic and does not yet call an external model. This is preferable to introducing an unmeasured free-form reasoning layer before grounding and evaluation exist.
