from typer.testing import CliRunner

from changeguard.cli import app
from changeguard.synthesis import SynthesisSelection


runner = CliRunner()


def test_evaluate_selector_defaults_to_deterministic_baseline():
    result = runner.invoke(app, ["evaluate-selector", "--runs", "2", "--strict"])

    assert result.exit_code == 0
    assert "ChangeGuard V5.2" in result.stdout
    assert "corpus: synthesis-selection-v1" in result.stdout
    assert "selector=deterministic" in result.stdout
    assert "selector success: 18/18 (100.0%)" in result.stdout
    assert "grounding guardrail pass: 18/18" in result.stdout
    assert "run-to-run stability (mean pairwise Jaccard): 1.000" in result.stdout
    assert "controlled evidence-selection corpus only" in result.stdout


def test_evaluate_selector_json_is_machine_readable():
    result = runner.invoke(app, ["evaluate-selector", "--json"])

    assert result.exit_code == 0
    assert '"corpus_version": "synthesis-selection-v1"' in result.stdout
    assert '"selector": "deterministic"' in result.stdout
    assert '"selection_success_rate": 1.0' in result.stdout


def test_evaluate_selector_ollama_wiring_uses_provider_without_network(monkeypatch):
    class FakeOllamaSelector:
        def __init__(self, model: str, base_url: str):
            self.model = model
            self.base_url = base_url

        def select(self, evidence):
            selected = [item.id for item in evidence[:2]]
            return SynthesisSelection(
                selected_evidence_ids=selected,
                selector="ollama",
                model=self.model,
                input_tokens=17,
                output_tokens=3,
            )

    monkeypatch.setattr(
        "changeguard.selection_evaluation_cli.OllamaEvidenceSelector",
        FakeOllamaSelector,
    )

    result = runner.invoke(
        app,
        [
            "evaluate-selector",
            "--selector",
            "ollama",
            "--model",
            "fake-local-model",
            "--ollama-url",
            "http://127.0.0.1:11434",
        ],
    )

    assert result.exit_code == 0
    assert "selector=ollama | model=fake-local-model" in result.stdout
    assert "provider tokens: input=" in result.stdout


def test_evaluate_selector_rejects_unknown_selector():
    result = runner.invoke(
        app,
        ["evaluate-selector", "--selector", "unknown"],
    )

    assert result.exit_code == 2
    assert "use deterministic, openai, or ollama" in result.stderr


def test_evaluate_selector_strict_fails_on_guardrail_violation(monkeypatch):
    class BadSelector:
        def __init__(self, model: str, base_url: str):
            pass

        def select(self, evidence):
            return SynthesisSelection(
                selected_evidence_ids=["invented:outage"],
                selector="ollama",
                model="bad-model",
            )

    monkeypatch.setattr(
        "changeguard.selection_evaluation_cli.OllamaEvidenceSelector",
        BadSelector,
    )

    result = runner.invoke(
        app,
        ["evaluate-selector", "--selector", "ollama", "--strict"],
    )

    assert result.exit_code == 1
    assert "grounding guardrail pass: 0/9" in result.stdout
