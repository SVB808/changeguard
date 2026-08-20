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

## V2 — Cross-service graph
- service nodes
- REST/provider-consumer edges
- messaging edges
- database dependencies
- graph-based blast-radius computation

Exit criterion:
- given a changed contract, list potentially affected services with evidence

## V3 — Agent orchestration
- contract-risk reviewer
- DB-migration reviewer
- security reviewer
- test-gap reviewer
- verifier
- risk aggregator
- checkpointing/retries

Exit criterion:
- every LLM finding links back to deterministic evidence
- verifier can reject unsupported findings

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
