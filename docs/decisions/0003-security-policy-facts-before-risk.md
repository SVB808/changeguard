# ADR-0003: Extract security policy facts before assigning security risk

## Status

Accepted

## Context

Spring Security configuration is semantically meaningful but easy to overstate. A diff that contains `permitAll()` or `csrf(...::disable)` is not, by itself, enough evidence to label a change a vulnerability. The same configuration can be intentional in a demo service, constrained by an upstream gateway, limited to selected matchers, or unsafe in production.

ChangeGuard therefore needs to separate observable framework configuration from later risk reasoning.

## Decision

The Java/Spring analyzer will deterministically extract security policy snapshots from methods that return `SecurityFilterChain` or `SecurityWebFilterChain`.

The first supported facts are:

- authorization selectors such as `anyRequest`, `anyExchange`, `requestMatchers`, and `pathMatchers`;
- authorization actions such as `permitAll`, `denyAll`, `authenticated`, `hasRole`, and `hasAuthority`;
- explicitly disabled features including CSRF, CORS, HTTP Basic, and form login.

Before/after policy snapshots are compared and emitted as `SECURITY_POLICY_ADDED`, `SECURITY_POLICY_REMOVED`, or `SECURITY_POLICY_CHANGED`.

The semantic analyzer does **not** assign severity or call a policy safe/unsafe.

## Consequences

Positive:

- security findings have deterministic provenance;
- later agents can reason over structured facts instead of raw source text;
- ChangeGuard can distinguish broad rules (`anyExchange -> permitAll`) from narrow matcher rules;
- benchmark cases can assert exact extracted policy facts.

Tradeoffs:

- the first version does not resolve custom composed security DSLs;
- matcher expressions that are not string literals are preserved only partially;
- framework defaults and infrastructure outside the source file are not inferred.

Those limitations should remain explicit until a later analysis stage has evidence to resolve them.
