# ADR 0023: Use runtime-shaped evidence for release evaluation

## Status

Accepted.

## Context

Early model-selection corpora were intentionally hand-authored so they could expose prompt and policy failure modes. Those corpora are useful for model-quality experiments, but some evidence items do not reproduce the exact source-path provenance emitted by `collect_evidence()` at runtime. That can create apparent policy failures that are really benchmark-shape mismatches.

## Decision

Keep the original selector corpora immutable for experiment history, and add a separate `synthesis-selection-runtime-v1` corpus built from typed `ChangeManifest` and `VerificationResult` fixtures passed through the production `collect_evidence()` function.

Use the runtime-shaped corpus for release-policy invariants, especially effective decision-critical retention and corpus-policy semantic diagnostics. Continue using the older corpora for raw model-quality and reproducibility research.

`changeguard evaluate-release` combines the deterministic `rest-impact-v3` gate with runtime-shaped synthesis evaluation while preserving their separate scopes and metrics.

## Consequences

- Production policy invariants are tested against evidence with runtime provenance semantics.
- Historical prompt/model experiments remain reproducible and are not rewritten after inspection.
- Release readiness does not depend on live model access; deterministic selection is the CI-safe default.
- Model-backed release evaluation remains available locally and is reported separately from deterministic guarantees.
