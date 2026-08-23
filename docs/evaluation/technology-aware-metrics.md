# V4.2 technology-aware evaluation

ChangeGuard V4.2 keeps the aggregate REST compatibility benchmark and adds a deliberately narrower breakdown by observed consumer technology.

## Corpus versioning

`rest-impact-v3.json` extends `rest-impact-v2.json` instead of copying it. The child corpus can attach metadata to inherited case IDs and append new cases. This preserves the V4.1 corpus as an immutable benchmark artifact while keeping later versions reviewable.

V3 adds two seeded cases from `SVB808/changeguard#16`:

- OpenFeign consumer calling the old `GET /orders/{orderId}` contract after the provider moves to `/purchases/{orderId}`.
- RestTemplate consumer making the same old-route call after the provider move.

The existing PR #253 negative cases and PR #9 seeded positive case are labeled as WebClient-backed observations.

## Reported technology groups

The evaluator reports aggregate metrics across all cases and a separate breakdown for explicitly labeled:

- `webclient`
- `feign`
- `resttemplate`

Unlabeled generic and synthetic route-shape cases still contribute to aggregate REST metrics but are intentionally excluded from the technology breakdown.

## Interpretation boundary

Per-technology samples are currently small. A `1.000` precision or recall value means only that the labeled controlled cases in that technology group matched the expected outcomes. It is not a production accuracy claim, not a framework-wide guarantee, and not evidence that dynamic or generated clients are fully understood.

The purpose of this breakdown is regression visibility: if support for one client style changes, the benchmark should reveal which evidence path regressed instead of hiding it inside one aggregate REST number.
