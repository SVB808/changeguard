# ChangeGuard Java/Spring Analyzer

This JVM module is ChangeGuard's deterministic Java semantic-analysis layer.

V1.1 focuses narrowly on Spring REST endpoints. It parses complete Java source files, extracts endpoint snapshots, compares before/after versions, and emits structured JSON describing semantic changes.

## Why full source instead of the diff?

A diff hunk may contain:

```java
@GetMapping("/health")
```

while the unchanged class declaration contains:

```java
@RequestMapping("/vets")
@RestController
class VetResource { ... }
```

The real endpoint is therefore `GET /vets/health`. ChangeGuard should derive that deterministically instead of asking an LLM to infer missing context.

## Build and test

Requires JDK 17+ and Maven.

```bash
mvn -f analyzers/java-spring/pom.xml test
mvn -f analyzers/java-spring/pom.xml package
```

The package step creates:

```text
analyzers/java-spring/target/changeguard-java-analyzer.jar
```

## Standalone usage

```bash
java -jar analyzers/java-spring/target/changeguard-java-analyzer.jar \
  --before path/to/BeforeController.java \
  --after path/to/AfterController.java \
  --pretty
```

The output contains:

- endpoint snapshots before the change,
- endpoint snapshots after the change,
- semantic changes such as `ENDPOINT_ADDED`, `ENDPOINT_PATH_CHANGED`, and `RESPONSE_TYPE_CHANGED`.

## V1.1 scope

Supported mapping annotations:

- `@RequestMapping`
- `@GetMapping`
- `@PostMapping`
- `@PutMapping`
- `@PatchMapping`
- `@DeleteMapping`

Extracted endpoint facts:

- controller class
- Java method name
- HTTP method
- complete path including class-level mappings
- return type as written in source
- parameter types as written in source

Not yet supported:

- composed/meta-annotations
- constant-expression resolution in mapping paths
- fully qualified type resolution
- cross-file DTO schema analysis
- overloaded controller method identity beyond simple method grouping
- Spring Security semantics
