from __future__ import annotations

import re
from pathlib import PurePosixPath

from changeguard.git_client import RawGitChange
from changeguard.models import ChangeStatus, EngineeringSurface, FileChange


SPRING_WEB_PATTERNS = (
    r"@RestController\b",
    r"@Controller\b",
    r"@RequestMapping\b",
    r"@GetMapping\b",
    r"@PostMapping\b",
    r"@PutMapping\b",
    r"@PatchMapping\b",
    r"@DeleteMapping\b",
)

SECURITY_PATTERNS = (
    r"@PreAuthorize\b",
    r"@PostAuthorize\b",
    r"@Secured\b",
    r"SecurityFilterChain\b",
    r"HttpSecurity\b",
    r"authorizeHttpRequests\b",
)

MESSAGING_PATTERNS = (
    r"@KafkaListener\b",
    r"KafkaTemplate\b",
    r"ProducerRecord\b",
    r"ConsumerRecord\b",
    r"RabbitTemplate\b",
    r"@RabbitListener\b",
)

RUNTIME_CONFIG_PATTERNS = (
    r"\benvironment\s*:",
    r"\bJAVA_OPTS\b",
    r"\bSPRING_PROFILES_ACTIVE\b",
    r"\bSERVER_PORT\b",
)

OBSERVABILITY_PATTERNS = (
    r"\bscrape_configs\s*:",
    r"\bmetrics_path\s*:",
    r"/actuator/prometheus\b",
    r"\bprometheus\b",
    r"\bgrafana\b",
    r"\bzipkin\b",
)

DTO_HINTS = (
    "/dto/",
    "/request/",
    "/response/",
)

BUILD_FILES = {
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "gradle.properties",
}

CONFIG_SUFFIXES = (
    ".yml",
    ".yaml",
    ".properties",
)

API_SPEC_HINTS = (
    "openapi",
    "swagger",
)

MESSAGE_SCHEMA_SUFFIXES = (
    ".avsc",
    ".proto",
)

OBSERVABILITY_PATH_HINTS = (
    "/monitoring/",
    "/prometheus/",
    "/grafana/",
    "/zipkin/",
)


def _status(token: str) -> ChangeStatus:
    if token.startswith("A"):
        return ChangeStatus.ADDED
    if token.startswith("M"):
        return ChangeStatus.MODIFIED
    if token.startswith("D"):
        return ChangeStatus.DELETED
    if token.startswith("R"):
        return ChangeStatus.RENAMED
    if token.startswith("C"):
        return ChangeStatus.COPIED
    return ChangeStatus.UNKNOWN


def _language(path: str) -> str:
    pure_path = PurePosixPath(path)
    filename = pure_path.name.lower()
    suffix = pure_path.suffix.lower()

    if filename == "dockerfile":
        return "dockerfile"
    if filename == ".dockerignore":
        return "dockerignore"

    return {
        ".java": "java",
        ".kt": "kotlin",
        ".sql": "sql",
        ".xml": "xml",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".properties": "properties",
        ".json": "json",
        ".avsc": "avro",
        ".proto": "protobuf",
        ".md": "markdown",
    }.get(suffix, "unknown")


def _has_any(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _is_compose_file(filename: str) -> bool:
    return filename.startswith("docker-compose") and filename.endswith((".yml", ".yaml"))


def classify(change: RawGitChange, patch: str) -> FileChange:
    normalized = change.path.replace("\\", "/")
    lowered = normalized.lower()
    filename = PurePosixPath(normalized).name.lower()
    is_documentation = (
        lowered.endswith(".md")
        or lowered.startswith("docs/")
        or "/docs/" in lowered
    )

    surfaces: list[EngineeringSurface] = []
    evidence: list[str] = []

    def add(surface: EngineeringSurface, reason: str) -> None:
        if surface not in surfaces:
            surfaces.append(surface)
        if reason not in evidence:
            evidence.append(reason)

    if lowered.endswith(".java") or lowered.endswith(".kt"):
        add(EngineeringSurface.JAVA_CODE, "Java/Kotlin source changed")

    if (
        "/db/migration/" in lowered
        or "/db/changelog/" in lowered
        or ("migration" in lowered and lowered.endswith(".sql"))
    ):
        add(EngineeringSurface.DATABASE, "Database migration file changed")

    if filename in BUILD_FILES:
        add(EngineeringSurface.DEPENDENCY, "Build/dependency descriptor changed")

    if filename.startswith("application") and filename.endswith(CONFIG_SUFFIXES):
        add(EngineeringSurface.CONFIG, "Spring application configuration changed")

    if filename in {"dockerfile", ".dockerignore"}:
        add(EngineeringSurface.DEPLOYMENT, "Container build configuration changed")

    if _is_compose_file(filename):
        add(EngineeringSurface.DEPLOYMENT, "Docker Compose deployment topology changed")
        if _has_any(RUNTIME_CONFIG_PATTERNS, patch):
            add(EngineeringSurface.CONFIG, "Runtime environment configuration changed")

    if not is_documentation and (
        any(hint in lowered for hint in OBSERVABILITY_PATH_HINTS)
        or _has_any(OBSERVABILITY_PATTERNS, patch)
    ):
        add(
            EngineeringSurface.OBSERVABILITY,
            "Observability configuration or integration changed",
        )

    if any(hint in lowered for hint in API_SPEC_HINTS):
        add(EngineeringSurface.API_CONTRACT, "OpenAPI/Swagger specification changed")

    if lowered.endswith(MESSAGE_SCHEMA_SUFFIXES):
        add(EngineeringSurface.MESSAGING, "Messaging schema changed")

    if not is_documentation and _has_any(SPRING_WEB_PATTERNS, patch):
        add(EngineeringSurface.API_CONTRACT, "Spring web annotation changed")

    if any(hint in lowered for hint in DTO_HINTS) and lowered.endswith((".java", ".kt")):
        add(EngineeringSurface.API_CONTRACT, "DTO/request/response type changed")

    if not is_documentation and (
        _has_any(SECURITY_PATTERNS, patch) or "security" in lowered
    ):
        add(EngineeringSurface.SECURITY, "Security-sensitive code or annotation changed")

    if not is_documentation and (
        _has_any(MESSAGING_PATTERNS, patch)
        or "kafka" in lowered
        or "rabbit" in lowered
    ):
        add(EngineeringSurface.MESSAGING, "Messaging producer/consumer code changed")

    return FileChange(
        status=_status(change.status_token),
        path=normalized,
        old_path=change.old_path,
        language=_language(normalized),
        surfaces=surfaces,
        evidence=evidence,
    )
