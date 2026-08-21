from typer.testing import CliRunner

from changeguard.cli import app


runner = CliRunner()


def test_evaluate_command_reports_reference_corpus_metrics():
    result = runner.invoke(app, ["evaluate"])

    assert result.exit_code == 0
    assert "ChangeGuard V4 | corpus: rest-impact-v1 | 11 case(s)" in result.stdout
    assert "11/11 (100.0%)" in result.stdout
    assert "precision=1.000 recall=1.000 FPR=0.000" in result.stdout
    assert "controlled corpus metrics only" in result.stdout
