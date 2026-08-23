# ChangeGuard roadmap

ChangeGuard is currently at **1.0.0rc1**. The V1 portfolio/release-candidate scope is intentionally narrow: Java/Spring REST impact analysis, explicit consumer-call refinement, revision-bound Maven verification, grounded evidence selection, deterministic policy closure, and repeatable evaluation.

## V1 release-candidate scope — complete

### Deterministic analysis
- local Git and public GitHub PR inputs
- structured Pydantic `ChangeManifest`
- engineering-surface classification
- Java/Spring AST analysis for REST endpoint and Spring Security semantics
- module-scoped service identity
- dependency graph construction
- WebClient, OpenFeign, and RestTemplate consumer-call evidence
- service-level and endpoint-level impact candidates
- auditable suppressed-impact candidates

### Verification
- endpoint-backed verification planning
- Maven module targeting
- nested reactor-root-aware commands
- explicit local execution only
- bounded stdout/stderr evidence
- `PASSED`, `FAILED`, and `ERROR` kept separate from causal claims
- generated plans bound to the analyzed Git `expected_head`
- execution refuses a mismatched local revision before project code runs

### Grounded synthesis
- LangGraph orchestration over typed ChangeGuard evidence
- deterministic default selector
- optional OpenAI evidence-ID selector
- local Ollama evidence-ID selector
- strict unknown/duplicate/budget guardrails
- deterministic decision-critical policy closure
- mandatory evidence over budget fails closed
- deterministic rendering and calibrated caveats

### Evaluation
- `rest-impact-v3` deterministic controlled corpus
- client-style seeded Maven fixtures
- raw evidence-selection corpus
- repeated-run and cross-batch reproducibility measurement
- raw-versus-effective selector-policy evaluation
- policy-semantics diagnostics
- production-shaped synthesis corpus generated through `collect_evidence()`
- consolidated `evaluate-release` release-candidate gate
- CI on Python 3.11/3.12, Java 17 analyzer, seeded Maven baselines, and offline provider contracts

### Portfolio packaging
- problem-first README
- architecture diagram
- explicit supported scope and limitations
- canonical end-to-end demo guide
- release-evaluation guide
- ADR history for major design choices
- package/CLI version `1.0.0rc1`

## V1 exit criteria

The V1 release candidate is ready when all of the following hold on the release branch:

1. Python and JVM test suites are green.
2. `changeguard evaluate --strict` passes the controlled deterministic corpus.
3. `changeguard evaluate-release --selector deterministic --strict` passes every release gate.
4. Generated verification plans are revision-bound and mismatches fail closed.
5. Model-backed synthesis cannot invent evidence IDs or remove runtime-mandatory evidence from the effective report.
6. The README/demo can be followed from a fresh environment without relying on undocumented steps.
7. Claims remain scoped to controlled benchmarks and supported evidence, not production accuracy.

The final merge/tag is intentionally a separate explicit release action.

## Post-V1 extensions — do not block the portfolio release

### Broader contract coverage
- Gradle verification planning
- deeper database migration compatibility analysis
- messaging schema/consumer compatibility
- broader dynamic HTTP-client extraction
- additional JVM/client frameworks

### Stronger verification
- clean-worktree/hermetic execution checks beyond exact HEAD binding
- sandbox/container execution
- Pact/Testcontainers-backed targeted verification
- richer failure attribution

### Product integration
- GitHub Check / PR comment output
- GitHub App installation flow
- observability/tracing
- small hosted UI
- persisted analysis history

### Agent orchestration
- narrowly permissioned contract-risk reviewer
- database-migration reviewer
- security reviewer
- test-gap reviewer
- verifier agent
- risk aggregator
- checkpointing/retries

These are follow-on product directions. They are not prerequisites for demonstrating ChangeGuard's deterministic-first architecture, measured model behavior, and explicit runtime safety invariants.
