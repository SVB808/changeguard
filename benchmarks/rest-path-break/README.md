# Seeded benchmark: REST path break

This benchmark is a deliberately small two-module Maven workspace used to exercise ChangeGuard's evidence -> inference -> verification pipeline.

Baseline contract:
- provider service exposes `GET /owners/{ownerId}`
- consumer service explicitly calls `GET http://provider-service/owners/{ownerId}`
- the consumer contract test passes

Seeded breaking change:
- provider route moves to `GET /customers/{ownerId}`
- the consumer keeps calling `/owners/{ownerId}`
- ChangeGuard should detect `ENDPOINT_PATH_CHANGED`
- the explicit consumer call should match the *previous* provider endpoint
- the impact candidate should be upgraded to `match level: endpoint`
- a targeted Maven verification plan should be generated for the consumer module
- executing the changed benchmark workspace should produce a failing consumer contract test

The benchmark uses tiny local annotations named `RestController`, `RequestMapping`, and `GetMapping`. JavaParser only needs the source-level annotation names for deterministic endpoint extraction; no Spring runtime is required for this seeded verification case.

The verification test does not claim to emulate all Spring runtime behavior. It is a controlled regression corpus entry whose ground truth is known in advance: the consumer route and provider route become incompatible.

## Baseline

From this directory:

```bash
mvn test
```

The baseline should pass.

## Changed-case branch

The companion benchmark PR changes only the provider route. Analyze that PR with:

```bash
changeguard pr --repo SVB808/changeguard --pr <benchmark-pr-number> --verification-plan
```

Expected evidence:

```text
ENDPOINT_PATH_CHANGED
before: GET /owners/{ownerId}
after:  GET /customers/{ownerId}

impact candidates: 1
match level: endpoint
consumer call: GET /owners/{ownerId}

verification plans: 1
```

After checking out the benchmark case branch, explicitly execute the consumer test from this workspace:

```bash
changeguard verify \
  --repo . \
  --consumer consumer-service \
  --module spring-petclinic-consumer-service
```

Expected process result: `FAILED`. That failure is verification evidence for this seeded case; ChangeGuard still does not generalize a non-zero build exit into a universal claim that every production deployment would fail.
