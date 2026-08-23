from typer.testing import CliRunner

from changeguard.cli import app


runner = CliRunner()


def test_evaluate_command_reports_reference_corpus_metrics_and_technology_breakdown():
    result = runner.invoke(app, ["evaluate"])

    assert result.exit_code == 0
    assert "ChangeGuard 1.0.0rc1 impact evaluation | corpus: rest-impact-v3 | 24 case(s)" in result.stdout
    assert "24/24 (100.0%)" in result.stdout
    assert "TP=13 FP=0 TN=11 FN=0" in result.stdout
    assert "precision=1.000 recall=1.000 FPR=0.000" in result.stdout
    assert "consumer technology breakdown" in result.stdout
    assert "webclient: 3 case(s)" in result.stdout
    assert "feign: 1 case(s)" in result.stdout
    assert "resttemplate: 1 case(s)" in result.stdout
    assert "small controlled samples" in result.stdout
    assert "controlled corpus metrics only" in result.stdout


def test_evaluate_json_includes_technology_breakdown():
    result = runner.invoke(app, ["evaluate", "--json"])

    assert result.exit_code == 0
    assert '"corpus_version": "rest-impact-v3"' in result.stdout
    assert '"technology_breakdown"' in result.stdout
    assert '"technology": "webclient"' in result.stdout
    assert '"technology": "feign"' in result.stdout
    assert '"technology": "resttemplate"' in result.stdout
