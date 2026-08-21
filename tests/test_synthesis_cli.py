from typer.testing import CliRunner

from changeguard.cli import app
from changeguard.models import ChangeManifest


runner = CliRunner()


def test_synthesize_command_reads_manifest_and_emits_grounded_report(tmp_path):
    manifest = ChangeManifest(
        repo="acme/empty",
        base="a" * 40,
        head="b" * 40,
    )
    path = tmp_path / "manifest.json"
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    result = runner.invoke(app, ["synthesize", "--manifest", str(path)])

    assert result.exit_code == 0
    assert "ChangeGuard V5.0 synthesis | acme/empty" in result.stdout
    assert "No active cross-service impact candidate" in result.stdout
    assert "Only supplied ChangeGuard evidence" in result.stdout


def test_synthesize_command_accepts_utf8_bom_manifest(tmp_path):
    manifest = ChangeManifest(
        repo="acme/powershell",
        base="a" * 40,
        head="b" * 40,
    )
    path = tmp_path / "manifest-with-bom.json"
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8-sig")

    result = runner.invoke(app, ["synthesize", "--manifest", str(path)])

    assert result.exit_code == 0
    assert "ChangeGuard V5.0 synthesis | acme/powershell" in result.stdout


def test_synthesize_json_is_machine_readable(tmp_path):
    manifest = ChangeManifest(
        repo="acme/empty",
        base="a" * 40,
        head="b" * 40,
    )
    path = tmp_path / "manifest.json"
    path.write_text(manifest.model_dump_json(), encoding="utf-8")

    result = runner.invoke(
        app,
        ["synthesize", "--manifest", str(path), "--json"],
    )

    assert result.exit_code == 0
    assert '"repo": "acme/empty"' in result.stdout
    assert '"evidence": []' in result.stdout
    assert '"caveats"' in result.stdout
