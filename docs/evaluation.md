# V4 benchmark evaluation

ChangeGuard's V4 evaluation layer turns deterministic impact behavior into repeatable measurements.

The first corpus is `benchmarks/evaluation/rest-impact-v1.json`. It contains controlled REST compatibility cases derived from three sources:

- public PR observations, including Petclinic PR #494 and #253,
- the seeded ChangeGuard REST path-break benchmark PR #9,
- synthetic cases that isolate specific compatibility-change classes and evidence conditions.

## What the metrics mean

The evaluator reports three different questions instead of collapsing everything into one score.

### Impact detection

A case is predicted positive when ChangeGuard leaves at least one active impact candidate after call-site refinement. This includes both conservative service-level candidates and endpoint-level candidates.

The corpus label states whether the controlled case is expected to have a consumer compatibility impact. From this, the evaluator reports true positives, false positives, true negatives, false negatives, precision, recall, and false-positive rate.

### Endpoint evidence

A case is endpoint-positive only when ChangeGuard has an exact consumer HTTP method + normalized route match for the previous provider contract. This measures whether the evidence layer reaches endpoint scope, not whether production will fail.

### Verification planning

A verification plan is expected only for endpoint-level active candidates. The evaluator reports plan-decision accuracy separately from impact detection.

## Latency

The evaluator measures only the in-process deterministic core for each corpus case:

`semantic fact -> service candidate -> call-site refinement -> verification planning`

It reports p50 and p95 analysis time over the corpus. These numbers intentionally exclude GitHub network requests, JVM parsing, Maven execution, and model inference. They must not be presented as end-to-end PR analysis latency.

## Current corpus coverage

`rest-impact-v1` includes:

1. additive endpoint change with no expected impact,
2. two Petclinic PR #253 request-signature changes suppressed by an unrelated GET call,
3. the seeded PR #9 path break with an exact old-route consumer call,
4. HTTP method change with an exact old-method call,
5. endpoint removal with an exact call,
6. response-type change with an exact call,
7. request-signature change with an exact POST call,
8. an unparsed/dynamic-call case that must remain conservative at service scope,
9. an unrelated explicit route that should suppress a coarse service candidate,
10. a compatibility-sensitive change with no known dependency.

## Important limitation

A perfect score on this corpus means the current deterministic policy matches the labels in this small controlled benchmark. It is **not** a claim of 100% production precision or recall.

The next evaluation expansions should add larger seeded repositories, Feign/RestTemplate/dynamic URI cases, real Spring application contexts, and separate end-to-end latency/cost measurements.
