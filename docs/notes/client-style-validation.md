# Seeded client-style validation

Validated locally on Windows on 2026-08-21.

- Python tests: 65 passed.
- Controlled REST corpus: 22/22 strict decisions.
- Feign/RestTemplate baseline Maven reactor: BUILD SUCCESS.
- Seeded PR #16: one provider `ENDPOINT_PATH_CHANGED`, two endpoint-level impact candidates, two verification plans.
- Explicit local verification on the broken branch failed for both `feign-consumer-service` and `resttemplate-consumer-service`, with contract-test evidence that `/orders/42` is no longer served.

The same repository-wide graph also exposed an unrelated suppressed candidate from the earlier WebClient benchmark because both benchmark workspaces use the logical service name `provider-service`. This is a useful ambiguity case: service names alone are not globally unique identifiers in a monorepo. Follow-up work should scope service identity by module/workspace rather than treating logical names as repository-global keys.
