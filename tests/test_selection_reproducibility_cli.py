from pathlib import Path

from typer.testing import CliRunner

from changeguard import __version__
from changeguard.cli import app
from changeguard.selection_evaluation import evaluate_selector, load_selection_corpus
from changeguard.synthesis import DeterministicEvidenceSelector


runner = CliRunner()
DEFAULT_CORPUS = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "evaluation"
    / "synthesis-selection-v1.json"
)


def test_evaluate_selector_reports_steady_state_warmup_protocol():
    result = runner.invoke(
        app,
        [
            "evaluate-selector",
            "--selector",
            "deterministic",
            "--warmup-runs",
            "1",
            "--runs",
            "2",
            "--strict",
        ],
    )

    assert result.exit_code == 0
    assert f"ChangeGuard {__version__} selector evaluation" in result.stdout
    assert "measurement mode: steady-state after 1 unscored warmup run(s) per case" in result.stdout
    assert "warmups: selector success=9/9 | grounding=9/9" in result.stdout
    assert "measured total: 18" in result.stdout
    assert "within-batch stability" in result.stdout


def test_compare_selector_evals_accepts_powershell_bom_and_reports_exact_match(tmp_path):
    corpus = load_selection_corpus(DEFAULT_CORPUS)
    left_report = evaluate_selector(
        corpus,
        DeterministicEvidenceSelector(),
        runs_per_case=2,
        warmup_runs_per_case=1,
    )
    right_report = evaluate_selector(
        corpus,
        DeterministicEvidenceSelector(),
        runs_per_case=2,
        warmup_runs_per_case=1,
    )

    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(left_report.model_dump_json(indent=2), encoding="utf-8-sig")
    right.write_text(right_report.model_dump_json(indent=2), encoding="utf-8")

    result = runner.invoke(app, ["compare-selector-evals", str(left), str(right)])

    assert result.exit_code == 0
    assert f"ChangeGuard {__version__} selector reproducibility" in result.stdout
    assert "aligned measured runs: 18" in result.stdout
    assert "exact ordered selection match: 18/18 (100.0%)" in result.stdout
    assert "exact evidence-set match: 18/18 (100.0%)" in result.stdout
    assert "mean cross-batch Jaccard: 1.000" in result.stdout


def test_compare_selector_evals_rejects_protocol_mismatch(tmp_path):
    corpus = load_selection_corpus(DEFAULT_CORPUS)
    left_report = evaluate_selector(
        corpus,
        DeterministicEvidenceSelector(),
        runs_per_case=1,
        warmup_runs_per_case=0,
    )
    right_report = evaluate_selector(
        corpus,
        DeterministicEvidenceSelector(),
        runs_per_case=1,
        warmup_runs_per_case=1,
    )

    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(left_report.model_dump_json(), encoding="utf-8")
    right.write_text(right_report.model_dump_json(), encoding="utf-8")

    result = runner.invoke(app, ["compare-selector-evals", str(left), str(right)])

    assert result.exit_code == 2
    assert "different protocols" in result.stderr
