import subprocess

from changeguard.maven_layout import MavenModuleLayout
from changeguard.models import (
    DependencyEdge,
    DependencyKind,
    EndpointChangeKind,
    ImpactCandidate,
    ImpactMatchLevel,
    ServiceDependencyGraph,
    ServiceNode,
    SpringEndpoint,
    VerificationStatus,
)
from changeguard.verification import build_verification_plans, execute_verification_plan


def _graph() -> ServiceDependencyGraph:
    return ServiceDependencyGraph(
        nodes=[
            ServiceNode(
                name="provider-service",
                module_path="benchmarks/client-style-path-break/provider-service",
            ),
            ServiceNode(
                name="feign-consumer-service",
                module_path="benchmarks/client-style-path-break/feign-consumer-service",
            ),
        ],
        edges=[
            DependencyEdge(
                source="feign-consumer-service",
                target="provider-service",
                source_module="benchmarks/client-style-path-break/feign-consumer-service",
                target_module="benchmarks/client-style-path-break/provider-service",
                kind=DependencyKind.DECLARATIVE_CLIENT,
                evidence_path="OrdersFeign.java",
                evidence='@FeignClient(name = "provider-service")',
            )
        ],
    )


def _candidate() -> ImpactCandidate:
    return ImpactCandidate(
        provider_service="provider-service",
        consumer_service="feign-consumer-service",
        provider_module="benchmarks/client-style-path-break/provider-service",
        consumer_module="benchmarks/client-style-path-break/feign-consumer-service",
        changed_file=(
            "benchmarks/client-style-path-break/provider-service/"
            "src/main/java/benchmark/provider/OrderResource.java"
        ),
        trigger_kind=EndpointChangeKind.ENDPOINT_PATH_CHANGED,
        before=SpringEndpoint(
            controller="OrderResource",
            method_name="findOrder",
            http_method="GET",
            path="/orders/{orderId}",
            return_type="String",
            parameter_types=["int"],
        ),
        after=SpringEndpoint(
            controller="OrderResource",
            method_name="findOrder",
            http_method="GET",
            path="/purchases/{orderId}",
            return_type="String",
            parameter_types=["int"],
        ),
        match_level=ImpactMatchLevel.ENDPOINT,
        reason="Provider endpoint path changed.",
        dependency_evidence=_graph().edges,
    )


def _layout() -> dict[str, MavenModuleLayout]:
    module = "benchmarks/client-style-path-break/feign-consumer-service"
    return {
        module: MavenModuleLayout(
            module_path=module,
            build_root="benchmarks/client-style-path-break",
            build_pom="benchmarks/client-style-path-break/pom.xml",
            module_selector="feign-consumer-service",
            evidence_paths=("benchmarks/client-style-path-break/pom.xml",),
        )
    }


def test_plan_uses_nested_reactor_pom_and_relative_module_selector():
    plan = build_verification_plans(
        [_candidate()],
        _graph(),
        module_layout=_layout(),
    )[0]

    assert plan.command == [
        "mvn",
        "-f",
        "benchmarks/client-style-path-break/pom.xml",
        "-pl",
        "feign-consumer-service",
        "-am",
        "test",
    ]
    assert "explicit reactor evidence" in plan.reason
    assert "benchmarks/client-style-path-break/pom.xml" in plan.reason


def test_nested_reactor_plan_executes_from_repo_root_without_root_pom(tmp_path):
    build_root = tmp_path / "benchmarks" / "client-style-path-break"
    consumer = build_root / "feign-consumer-service"
    consumer.mkdir(parents=True)
    (build_root / "pom.xml").write_text("<project />", encoding="utf-8")
    (consumer / "pom.xml").write_text("<project />", encoding="utf-8")

    plan = build_verification_plans(
        [_candidate()],
        _graph(),
        module_layout=_layout(),
    )[0]
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="targeted tests passed\n",
            stderr="",
        )

    result = execute_verification_plan(plan, tmp_path, runner=fake_runner)

    assert result.status == VerificationStatus.PASSED
    assert result.exit_code == 0
    assert calls[0][0] == plan.command
    assert calls[0][1]["cwd"] == tmp_path.resolve()
