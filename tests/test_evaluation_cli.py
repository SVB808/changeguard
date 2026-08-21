from typer.testing import CliRunner

from changeguard.cli import app


runner = CliRunner()


def test_evaluate_command_reports_reference_corpus_metrics():
    result = runner.invoke(app, ["evaluate"])

    assert result.exit_code == 0
    assert "ChangeGuard V4.1 | corpus: rest-impact-v2 | 22 case(s)" in result.stdout
    assert "22/22 (100.0%)" in result.stdout
    assert "TP=11 FP=0 TN=11 FN=0" in result.stdout
    assert "precision=1.000 recall=1.000 FPR=0.000" in result.stdout
    assert "controlled corpus metrics only" in result.stdout
