# Public PR evaluation cases

ChangeGuard uses real public pull requests as regression and precision benchmarks. These cases are evidence-driven; they are not claims that the upstream pull requests were defective.

## Spring Petclinic microservices PR #494

Repository: `spring-petclinic/spring-petclinic-microservices`

Observed provider change:
- `ENDPOINT_ADDED`
- `GET /vets/health`
- provider service: `vets-service`
- direct dependent: `api-gateway`

Expected impact behavior:
- no active impact candidate

Why: an additive endpoint is not compatibility-sensitive under the current deterministic rules.

Validated locally:
- V1.1 recovered the full Spring route by joining unchanged class-level `/vets` with changed method-level `/health`.
- V2 linked `api-gateway` as a direct dependent of `vets-service`.
- V2.1 produced zero impact candidates.

## Spring Petclinic microservices PR #253

Repository: `spring-petclinic/spring-petclinic-microservices`

Observed provider changes in `OwnerResource`:
- `POST /owners`: request type changed from `Owner` to `OwnerRequest`
- `PUT /owners/{ownerId}`: request type changed from `Owner` to `OwnerRequest`

V2.1 behavior:
- two service-level `POTENTIAL_CONSUMER_IMPACT` candidates for `api-gateway`

Observed V2.2 consumer evidence at PR head `c93926c1e9c22fbcc72a6698b1a059ce9baf47f2`:
- `api-gateway -> customers-service GET /owners/{ownerId}`

Expected V2.2 behavior:
- active candidates: 0
- suppressed service-level candidates: 2

Why: explicit literal calls to `customers-service` exist for the consumer, but neither matches the changed provider method+path. Suppression is auditable rather than destructive because dynamic or unsupported call sites may still exist.

Additional regression discovered while evaluating PR #253:
- JavaParser initially rejected Java records because parser language level was not configured even though the analyzer compiled with JDK 17.
- ChangeGuard now configures JavaParser for Java 17 and includes a record parsing regression test.

## Validation snapshots

Current validated local suites after V2.2:
- JVM analyzer: 12 tests passed
- Python suite: 34 tests passed

These counts are snapshots, not permanent project metrics; they should be updated only when a later milestone is explicitly validated.
