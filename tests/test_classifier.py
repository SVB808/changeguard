from changeguard.classifier import classify
from changeguard.git_client import RawGitChange
from changeguard.models import ChangeStatus, EngineeringSurface


def test_controller_change_is_api_contract():
    change = RawGitChange(
        status_token="M",
        path="src/main/java/com/acme/orders/OrderController.java",
    )
    patch = """
+    @GetMapping("/orders/{id}")
+    public OrderResponse find(@PathVariable long id) {
"""

    result = classify(change, patch)

    assert result.status == ChangeStatus.MODIFIED
    assert EngineeringSurface.JAVA_CODE in result.surfaces
    assert EngineeringSurface.API_CONTRACT in result.surfaces


def test_flyway_migration_is_database_change():
    change = RawGitChange(
        status_token="A",
        path="src/main/resources/db/migration/V12__add_status.sql",
    )

    result = classify(change, "+ALTER TABLE orders ADD COLUMN status varchar(32);")

    assert result.status == ChangeStatus.ADDED
    assert EngineeringSurface.DATABASE in result.surfaces


def test_security_annotation_is_security_change():
    change = RawGitChange(
        status_token="M",
        path="src/main/java/com/acme/orders/OrderService.java",
    )

    result = classify(
        change,
        '-    @PreAuthorize("hasRole(\'ADMIN\')")\n'
        '+    @PreAuthorize("hasRole(\'USER\')")',
    )

    assert EngineeringSurface.SECURITY in result.surfaces


def test_pom_is_dependency_change():
    change = RawGitChange(
        status_token="M",
        path="pom.xml",
    )

    result = classify(change, "+<version>3.5.0</version>")

    assert EngineeringSurface.DEPENDENCY in result.surfaces


def test_dockerfile_is_deployment_change():
    change = RawGitChange(
        status_token="A",
        path="orders-service/Dockerfile",
    )

    result = classify(change, "+FROM eclipse-temurin:17-jre-alpine")

    assert result.language == "dockerfile"
    assert EngineeringSurface.DEPLOYMENT in result.surfaces


def test_docker_compose_detects_deployment_runtime_config_and_observability():
    change = RawGitChange(
        status_token="M",
        path="docker-compose.yml",
    )
    patch = """
+services:
+  api-gateway:
+    environment:
+      SPRING_PROFILES_ACTIVE: docker
+  prometheus:
+    image: prom/prometheus:latest
"""

    result = classify(change, patch)

    assert EngineeringSurface.DEPLOYMENT in result.surfaces
    assert EngineeringSurface.CONFIG in result.surfaces
    assert EngineeringSurface.OBSERVABILITY in result.surfaces


def test_prometheus_config_is_observability_change():
    change = RawGitChange(
        status_token="A",
        path="monitoring/prometheus/prometheus.yml",
    )
    patch = """
+scrape_configs:
+  - job_name: 'api-gateway'
+    metrics_path: '/actuator/prometheus'
"""

    result = classify(change, patch)

    assert result.language == "yaml"
    assert EngineeringSurface.OBSERVABILITY in result.surfaces


def test_markdown_document_does_not_become_runtime_surface():
    change = RawGitChange(
        status_token="A",
        path="docs/runtime-validation/README.md",
    )

    result = classify(change, "+Document Prometheus and Docker validation steps")

    assert result.language == "markdown"
    assert result.surfaces == []
