from typer.testing import CliRunner

from changeguard.cli import app


runner = CliRunner()


def test_effective_selector_cli_reports_raw_and_post_policy_quality():
    result = runner.invoke(
        app,
        ["evaluate-selector-policy", "--runs", "2", "--strict"],
    )

    assert result.exit_code == 0
    assert "ChangeGuard V5.3.1" in result.stdout
    assert "corpus: synthesis-selection-v1" in result.stdout
    assert "raw selector quality:" in result.stdout
    assert "effective quality after deterministic decision-critical closure:" in result.stdout
    assert "runtime policy-mandatory retention:" in result.stdout
    assert "policy interventions:" in result.stdout
    assert "corpus-policy diagnostics:" in result.stdout
    assert "controlled evidence-selection corpus only" in result.stdout


def test_effective_selector_cli_json_is_machine_readable():
    result = runner.invoke(
        app,
        ["evaluate-selector-policy", "--runs", "1", "--json"],
    )

    assert result.exit_code == 0
    assert '"corpus_version": "synthesis-selection-v1"' in result.stdout
    assert '"raw_quality"' in result.stdout
    assert '"effective_quality"' in result.stdout
    assert '"policy_mandatory"' in result.stdout
    assert '"corpus_policy_diagnostics"' in result.stdout
    assert '"policy_intervention_runs"' in result.stdout
