from pathlib import Path

from changeguard.selection_evaluation import load_selection_corpus


EVAL_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "evaluation"


def test_selection_v2_corpus_loads_and_uses_new_case_ids():
    v1 = load_selection_corpus(EVAL_DIR / "synthesis-selection-v1.json")
    v2 = load_selection_corpus(EVAL_DIR / "synthesis-selection-v2.json")

    assert v2.version == "synthesis-selection-v2"
    assert len(v2.cases) == 8
    assert {case.id for case in v1.cases}.isdisjoint({case.id for case in v2.cases})


def test_selection_v2_corpus_has_holdout_stress_dimensions():
    v2 = load_selection_corpus(EVAL_DIR / "synthesis-selection-v2.json")

    assert any(len(case.coverage_groups) >= 4 for case in v2.cases)
    assert any(case.verification_critical_ids for case in v2.cases)
    assert any(len(case.distractor_evidence_ids) >= 7 for case in v2.cases)
    assert any(
        any("SYSTEM OVERRIDE" in item.statement for item in case.evidence)
        for case in v2.cases
    )
