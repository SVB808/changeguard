from typer.testing import CliRunner

from changeguard.cli import app
from changeguard.models import ChangeManifest
from changeguard.synthesis import SynthesisSelection


runner = CliRunner()


def _write_manifest(tmp_path, repo: str = "acme/empty"):
    manifest = ChangeManifest(
        repo=repo,
        base="a" * 40,
        head="b" * 40,
    )
    path = tmp_path / "manifest.json"
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_synthesize_command_reads_manifest_and_emits_grounded_report(tmp_path):
    path = _write_manifest(tmp_path)

    result = runner.invoke(app, ["synthesize", "--manifest", str(path)])

    assert result.exit_code == 0
    assert "ChangeGuard V5.0 synthesis | acme/empty" in result.stdout
    assert "selector: deterministic" in result.stdout
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
    path = _write_manifest(tmp_path)

    result = runner.invoke(
        app,
        ["synthesize", "--manifest", str(path), "--json"],
    )

    assert result.exit_code == 0
    assert '"repo": "acme/empty"' in result.stdout
    assert '"evidence": []' in result.stdout
    assert '"selector": "deterministic"' in result.stdout
    assert '"caveats"' in result.stdout


def test_synthesize_openai_selector_is_wired_without_provider_call(tmp_path, monkeypatch):
    path = _write_manifest(tmp_path, repo="acme/model")

    class FakeOpenAISelector:
        def __init__(self, model: str):
            self.model = model

        def select(self, evidence):
            return SynthesisSelection(
                selected_evidence_ids=[],
                selector="openai",
                model=self.model,
                input_tokens=19,
                output_tokens=4,
            )

    monkeypatch.setattr(
        "changeguard.synthesis_cli.OpenAIEvidenceSelector",
        FakeOpenAISelector,
    )

    result = runner.invoke(
        app,
        [
            "synthesize",
            "--manifest",
            str(path),
            "--selector",
            "openai",
            "--model",
            "fake-model",
        ],
    )

    assert result.exit_code == 0
    assert "ChangeGuard V5.1 synthesis | acme/model" in result.stdout
    assert "selector: openai | model: fake-model | tokens: input=19 output=4" in result.stdout
    assert "Model participation is limited to evidence-ID selection" in result.stdout


def test_synthesize_rejects_unknown_selector(tmp_path):
    path = _write_manifest(tmp_path)

    result = runner.invoke(
        app,
        ["synthesize", "--manifest", str(path), "--selector", "unknown"],
    )

    assert result.exit_code == 2
    assert "use deterministic or openai" in result.stdout
