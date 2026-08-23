# ChangeGuard release evaluation

ChangeGuard 1.0.0rc1 has one consolidated offline release-candidate gate:

```powershell
changeguard evaluate-release --selector deterministic --runs 3 --strict
```

The command deliberately combines two different types of evidence instead of collapsing them into one accuracy number.

## Deterministic impact gate

`rest-impact-v3` validates the deterministic change-impact vertical. It measures exact disposition + verification-plan decisions, impact/endpoint confusion matrices, and a small technology breakdown.

A passing release gate requires every controlled case to match its expected disposition and verification-plan decision.

These are controlled-corpus metrics, not production accuracy.

## Runtime-shaped synthesis gate

`synthesis-selection-runtime-v1` is built from typed `ChangeManifest` and `VerificationResult` objects and then passed through the same `collect_evidence()` function used by production synthesis. That gives impact evidence the same provider/consumer source-path provenance used by deterministic decision-critical closure.

The release gate requires:

- every selector call to succeed,
- raw and effective selections to pass grounding,
- 100% effective retention of runtime policy-mandatory evidence,
- zero corpus-policy semantic contradictions.

The release command also reports raw/effective summary quality so model weaknesses remain visible even when deterministic policy closure preserves runtime invariants.

## CI

CI runs the consolidated deterministic release gate on Python 3.12 in addition to the full unit suite, deterministic impact benchmark, deterministic selector grounding gate, Java analyzer build, and seeded Maven fixtures.

The release gate is offline by default and never requires Ollama or OpenAI.

## Local Ollama measurement

A local model can be measured against the same production-shaped corpus without changing the release invariants:

```powershell
changeguard evaluate-release `
  --selector ollama `
  --model llama3.2:3b `
  --warmup-runs 1 `
  --runs 3
```

Model quality can vary by provider/runtime. The deterministic release gate therefore does not depend on a live model call.

## Final V1 checklist

Before tagging the release candidate/final V1:

```powershell
pytest
mvn -f analyzers/java-spring/pom.xml test
changeguard evaluate --strict
changeguard evaluate-release --selector deterministic --runs 3 --strict
changeguard --help
```

The final merge/tag is intentionally separate from implementation work and should happen only after explicit release approval.
