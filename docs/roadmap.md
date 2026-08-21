# ChangeGuard roadmap

## V0 — Deterministic evidence pipeline
- local Git refs as input
- structured change manifest
- path/diff-based engineering-surface classification
- unit tests

Exit criterion:
- a real Spring Boot repository can be scanned reproducibly
- output is valid structured JSON
- classifiers have test coverage

## V1 — Java/Spring semantic analyzer
- AST/LST analysis
- endpoint signature extraction
- DTO/schema changes
- Spring Security annotation changes
- Flyway/Liquibase metadata
- dependency changes

Exit criterion:
- identify semantic changes without asking an LLM to parse raw source

## V2 — Cross-service graph and impact refinement
- service nodes
- REST/provider-consumer edges
- explicit consumer HTTP call extraction
- endpoint-level matching
- graph-based impact candidates
- auditable suppression of unsupported service-level candidates

Exit criterion:
- given a changed contract, list potentially affected services with evidence
- distinguish service-level dependency from endpoint-level consumer evidence

## V3 — Verification + agent orchestration

### V3.0 — Targeted deterministic verification
- create reviewable verification plans only for endpoint-level candidates
- target the affected consumer Maven module
- execute only in an explicit user-supplied local workspace
- record exit status, duration, and bounded process output
- keep process results separate from causality claims

### Later V3 — Agent orchestration
- contract-risk reviewer
- DB-migration reviewer
- security reviewer
- test-gap reviewer
- verifier agent
- risk aggregator
- checkpointing/retries

Exit criterion:
- every LLM finding links back to deterministic evidence
- verification evidence can support or falsify agent findings
- remote PR analysis never silently executes untrusted project build code

## V4 — Benchmark + evaluation
- seeded regression corpus
- per-risk-class precision/recall
- false-positive rate
- p95 latency
- model/token cost

Exit criterion:
- project has repeatable before/after benchmark numbers

## V5 — GitHub integration
- GitHub App / Check output
- PR annotations
- human approval for mutating actions
- observability/tracing

Exit criterion:
- another developer can install and run ChangeGuard on a repository
