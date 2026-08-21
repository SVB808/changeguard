import subprocess

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
from changeguard.verification import (
    build_verification_plans,
    create_maven_module_plan,
    execute_verification_plan,
)


def _endpoint() -> SpringEndpoint:
    return SpringEndpoint(
        controller="OwnerResource",
        method_name="findOwner",
        http_method="GET",
        path="/owners/{ownerId}",
        return_type="OwnerDetails",
        parameter_types=["int"],
    )


def _graph() -> ServiceDependencyGraph:
    return ServiceDependencyGraph(
        nodes=[
            ServiceNode(
                name="api-gateway",
                module_path="spring-petclinic-api-gateway",
            ),
            ServiceNode(
                name="customers-service",
                module_path="spring-petclinic-customers-service",
            ),
        ],
        edges=[
            DependencyEdge(
                source="api-gateway",
                target="customers-service",
                kind=DependencyKind.SERVICE_URL,
                evidence_path="CustomersServiceClient.java",
                evidence="http://customers-service",
            )
        ],
    )


def _candidate(match_level: ImpactMatchLevel) -> ImpactCandidate:
    return ImpactCandidate(
        provider_service="customers-service",
        consumer_service="api-gateway",
        changed_file=(
            "spring-petclinic-customers-service/src/main/java/example/"
            "OwnerResource.java"
        ),
        trigger_kind=EndpointChangeKind.ENDPOINT_REMOVED,
        before=_endpoint(),
        match_level=match_level,
        reason="Provider endpoint was removed.",
        dependency_evidence=_graph().edges,
    )


def _workspace(tmp_path):
    (tmp_path / "pom.xml").write_text("<project />", encoding="utf-8")
    module = tmp_path / "spring-petclinic-api-gateway"
    module.mkdir()
    (module / "pom.xml").write_text("<project />", encoding="utf-8")
    return tmp_path


def test_endpoint_level_candidate_creates_targeted_maven_plan():
    plans = build_verification_plans(
        [_candidate(ImpactMatchLevel.ENDPOINT)],
        _graph(),
    )

    assert len(plans) == 1
    plan = plans[0]
    assert plan.consumer_service == "api-gateway"
    assert plan.consumer_module == "spring-petclinic-api-gateway"
    assert plan.command == [
        "mvn",
        "-pl",
        "spring-petclinic-api-gateway",
        "-am",
        "test",
    ]
    assert plan.status == VerificationStatus.NOT_RUN


def test_service_level_candidate_does_not_create_verification_plan():
    plans = build_verification_plans(
        [_candidate(ImpactMatchLevel.SERVICE)],
        _graph(),
    )

    assert plans == []


def test_successful_local_verification_records_process_evidence(tmp_path):
    workspace = _workspace(tmp_path)
    plan = build_verification_plans(
        [_candidate(ImpactMatchLevel.ENDPOINT)],
        _graph(),
    )[0]
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="all tests passed\n",
            stderr="",
        )

    result = execute_verification_plan(
        plan,
        workspace,
        timeout_seconds=45,
        runner=fake_runner,
    )

    assert result.status == VerificationStatus.PASSED
    assert result.exit_code == 0
    assert result.stdout_tail == "all tests passed\n"
    assert result.error is None
    assert calls[0][0] == plan.command
    assert calls[0][1]["cwd"] == workspace.resolve()
    assert calls[0][1]["timeout"] == 45


def test_non_zero_verification_exit_is_failed_not_confirmed_breakage(tmp_path):
    workspace = _workspace(tmp_path)
    plan = build_verification_plans(
        [_candidate(ImpactMatchLevel.ENDPOINT)],
        _graph(),
    )[0]

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(
            args=command,
            returncode=7,
            stdout="",
            stderr="test failure\n",
        )

    result = execute_verification_plan(plan, workspace, runner=fake_runner)

    assert result.status == VerificationStatus.FAILED
    assert result.exit_code == 7
    assert result.stderr_tail == "test failure\n"
    assert result.error is None


def test_invalid_workspace_returns_error_without_running_command(tmp_path):
    plan = build_verification_plans(
        [_candidate(ImpactMatchLevel.ENDPOINT)],
        _graph(),
    )[0]

    def should_not_run(*args, **kwargs):
        raise AssertionError("runner should not execute for invalid workspace")

    result = execute_verification_plan(plan, tmp_path, runner=should_not_run)

    assert result.status == VerificationStatus.ERROR
    assert result.exit_code is None
    assert result.error is not None
    assert "root pom.xml" in result.error


def test_verification_module_cannot_escape_workspace(tmp_path):
    workspace = _workspace(tmp_path)
    outside = tmp_path.parent / "outside-module"
    outside.mkdir(exist_ok=True)
    (outside / "pom.xml").write_text("<project />", encoding="utf-8")
    plan = create_maven_module_plan("api-gateway", "../outside-module")

    def should_not_run(*args, **kwargs):
        raise AssertionError("runner should not execute for escaping module path")

    result = execute_verification_plan(plan, workspace, runner=should_not_run)

    assert result.status == VerificationStatus.ERROR
    assert result.error is not None
    assert "must remain inside" in result.error
