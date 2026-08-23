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
from changeguard.verification import build_verification_plans, execute_verification_plan


EXPECTED_HEAD = "a" * 40
OTHER_HEAD = "b" * 40


def _graph() -> ServiceDependencyGraph:
    return ServiceDependencyGraph(
        nodes=[
            ServiceNode(name="provider", module_path="provider"),
            ServiceNode(name="consumer", module_path="consumer"),
        ],
        edges=[
            DependencyEdge(
                source="consumer",
                target="provider",
                source_module="consumer",
                target_module="provider",
                kind=DependencyKind.DECLARATIVE_CLIENT,
                evidence_path="consumer/Client.java",
                evidence='@FeignClient(name = "provider")',
            )
        ],
    )


def _candidate() -> ImpactCandidate:
    return ImpactCandidate(
        provider_service="provider",
        consumer_service="consumer",
        provider_module="provider",
        consumer_module="consumer",
        changed_file="provider/src/main/java/ProviderResource.java",
        trigger_kind=EndpointChangeKind.ENDPOINT_PATH_CHANGED,
        before=SpringEndpoint(
            controller="ProviderResource",
            method_name="get",
            http_method="GET",
            path="/old/{id}",
            return_type="String",
            parameter_types=["String"],
        ),
        after=SpringEndpoint(
            controller="ProviderResource",
            method_name="get",
            http_method="GET",
            path="/new/{id}",
            return_type="String",
            parameter_types=["String"],
        ),
        match_level=ImpactMatchLevel.ENDPOINT,
        reason="Provider endpoint path changed.",
        dependency_evidence=_graph().edges,
    )


def _workspace(tmp_path):
    (tmp_path / "pom.xml").write_text("<project />", encoding="utf-8")
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "pom.xml").write_text("<project />", encoding="utf-8")
    return tmp_path


def test_generated_plan_records_expected_head():
    plan = build_verification_plans(
        [_candidate()],
        _graph(),
        expected_head=EXPECTED_HEAD,
    )[0]

    assert plan.expected_head == EXPECTED_HEAD


def test_revision_mismatch_returns_error_without_executing_project_code(tmp_path):
    workspace = _workspace(tmp_path)
    plan = build_verification_plans(
        [_candidate()],
        _graph(),
        expected_head=EXPECTED_HEAD,
    )[0]

    def should_not_run(*args, **kwargs):
        raise AssertionError("Maven runner must not execute for a revision mismatch")

    result = execute_verification_plan(
        plan,
        workspace,
        runner=should_not_run,
        revision_reader=lambda _: OTHER_HEAD,
    )

    assert result.status == VerificationStatus.ERROR
    assert result.exit_code is None
    assert result.error is not None
    assert "revision mismatch" in result.error.lower()
    assert EXPECTED_HEAD in result.error
    assert OTHER_HEAD in result.error


def test_matching_revision_allows_explicit_verification(tmp_path):
    workspace = _workspace(tmp_path)
    plan = build_verification_plans(
        [_candidate()],
        _graph(),
        expected_head=EXPECTED_HEAD,
    )[0]
    calls = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="ok\n",
            stderr="",
        )

    result = execute_verification_plan(
        plan,
        workspace,
        runner=fake_runner,
        revision_reader=lambda _: EXPECTED_HEAD,
    )

    assert result.status == VerificationStatus.PASSED
    assert calls == [plan.command]
