# V4.1 benchmark evaluation

ChangeGuard's evaluation layer turns deterministic impact behavior into repeatable measurements.

The current default corpus is `benchmarks/evaluation/rest-impact-v2.json`. The previous `rest-impact-v1.json` remains versioned and unchanged so benchmark evolution is auditable.

The V2 corpus contains controlled REST compatibility cases derived from three sources:

- public PR observations, including Petclinic PR #494 and #253,
- the seeded ChangeGuard REST path-break benchmark PR #9,
- synthetic/adversarial cases that isolate specific compatibility-change classes and route-matching boundaries.

## What the metrics mean

The evaluator reports three different questions instead of collapsing everything into one score.

### Impact detection

A case is predicted positive when ChangeGuard leaves at least one active impact candidate after call-site refinement. This includes both conservative service-level candidates and endpoint-level candidates.

The corpus label states whether the controlled case is expected to have a consumer compatibility impact. From this, the evaluator reports true positives, false positives, true negatives, false negatives, precision, recall, and false-positive rate.

### Endpoint evidence

A case is endpoint-positive only when ChangeGuard has compatible consumer HTTP method + route evidence for the previous provider contract. Route matching is structural rather than raw-string equality:

- path-variable names may differ,
- query strings are ignored for endpoint routing,
- provider method `ANY` can match a concrete consumer method,
- Spring-style `*` and `**` path wildcards are supported,
- literal route case is preserved.

This measures whether the evidence layer reaches endpoint scope, not whether production will fail.

### Verification planning

A verification plan is expected only for endpoint-level active candidates. The evaluator reports plan-decision accuracy separately from impact detection.

## Latency

The evaluator measures only the in-process deterministic core for each corpus case:

`semantic fact -> service candidate -> call-site refinement -> verification planning`

It reports p50 and p95 analysis time over the corpus. These numbers intentionally exclude GitHub network requests, JVM parsing, Maven execution, and model inference. They must not be presented as end-to-end PR analysis latency.

## Current corpus coverage

`rest-impact-v2` contains 22 cases. It preserves the V1 cases and adds adversarial coverage for:

1. query strings on otherwise matching consumer routes,
2. `ANY` provider mappings with concrete consumer methods,
3. multiple observed consumer calls where at least one matches,
4. the same route with the wrong HTTP method,
5. case-sensitive literal route mismatches,
6. recursive Spring `**` route matching,
7. one-segment Spring `*` route matching,
8. rejection when a single `*` would have to cross path segments,
9. additive endpoints even when a same-shaped consumer call exists,
10. exact-looking call evidence without a known service dependency,
11. response-type changes where all observed calls target unrelated routes.

The original public/seeded cases remain important anchors:

- Petclinic PR #494: additive endpoint -> no candidate,
- Petclinic PR #253: two request-signature changes -> service candidates suppressed by unrelated GET evidence,
- ChangeGuard PR #9: seeded provider path break -> endpoint candidate + verification plan + failing consumer contract test.

## Important limitations

A perfect score on this corpus means the current deterministic policy matches the labels in this controlled benchmark. It is **not** a claim of 100% production precision or recall.

The route matcher intentionally does not interpret arbitrary regex constraints inside path-variable declarations. The consumer extractor also remains limited to supported literal HTTP call patterns; dynamic URI construction can therefore leave a candidate at conservative service scope.

Future evaluation expansion should include larger seeded repositories, Feign/RestTemplate/dynamic URI extraction, gateway route rewriting, real Spring application contexts, multiple consumers per provider, and separate end-to-end latency/cost measurements.
