from typer.testing import CliRunner

from changeguard.cli import app


runner = CliRunner()


def test_evaluate_release_deterministic_strict_passes_controlled_gates():
    result = runner.invoke(
        app,
        ["evaluate-release", "--selector", "deterministic", "--runs", "2", "--strict"],
    )

    assert result.exit_code == 0
    assert "ChangeGuard 1.0.0rc1 release evaluation" in result.stdout
    assert "corpus: rest-impact-v3 | exact: 24/24 (100.0%)" in result.stdout
    assert "corpus: synthesis-selection-runtime-v1" in result.stdout
    assert "runtime policy-mandatory retention:" in result.stdout
    assert "runtime corpus semantics: PASS" in result.stdout
    assert "overall: PASS" in result.stdout
    assert "not a production-accuracy claim" in result.stdout


def test_evaluate_release_json_is_machine_readable():
    result = runner.invoke(
        app,
        ["evaluate-release", "--selector", "deterministic", "--json"],
    )

    assert result.exit_code == 0
    assert '"release_candidate": "1.0.0rc1"' in result.stdout
    assert '"deterministic_impact"' in result.stdout
    assert '"runtime_selection"' in result.stdout
    assert '"release_gate_passed": true' in result.stdout
