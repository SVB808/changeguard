from typer.testing import CliRunner

from changeguard.cli import app
from changeguard.models import (
    ChangeManifest,
    EndpointChangeKind,
    VerificationPlan,
)


runner = CliRunner()


def _write_manifest(tmp_path, *, expected_head: str | None):
    manifest = ChangeManifest(
        repo="fixture/repo",
        base="a" * 40,
        head="b" * 40,
        verification_planning_enabled=True,
        verification_plans=[
            VerificationPlan(
                provider_service="provider",
                consumer_service="consumer",
                consumer_module="consumer",
                changed_file="provider/Resource.java",
                trigger_kind=EndpointChangeKind.ENDPOINT_REMOVED,
                command=["mvn", "-pl", "consumer", "-am", "test"],
                reason="fixture",
                expected_head=expected_head,
            )
        ],
    )
    path = tmp_path / "manifest.json"
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_verify_plan_rejects_unbound_legacy_manifest_before_execution(tmp_path):
    manifest_path = _write_manifest(tmp_path, expected_head=None)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = runner.invoke(
        app,
        [
            "verify-plan",
            "--manifest",
            str(manifest_path),
            "--repo",
            str(workspace),
        ],
    )

    assert result.exit_code == 2
    assert "not revision-bound" in result.stderr
    assert "Re-analyze the PR" in result.stderr


def test_verify_plan_rejects_out_of_range_plan_index(tmp_path):
    manifest_path = _write_manifest(tmp_path, expected_head="b" * 40)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = runner.invoke(
        app,
        [
            "verify-plan",
            "--manifest",
            str(manifest_path),
            "--repo",
            str(workspace),
            "--plan-index",
            "2",
        ],
    )

    assert result.exit_code == 2
    assert "out of range" in result.stderr
