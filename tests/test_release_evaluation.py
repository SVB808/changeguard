from changeguard.release_evaluation import evaluate_release_candidate
from changeguard.synthesis import DeterministicEvidenceSelector


def test_release_evaluation_passes_controlled_deterministic_gates():
    report = evaluate_release_candidate(DeterministicEvidenceSelector(), runs_per_case=2)

    assert report.release_candidate == "1.0.0rc1"
    assert report.deterministic_impact.exact_matches == 24
    assert report.deterministic_impact.total_cases == 24
    assert report.runtime_selection.corpus_version == "synthesis-selection-runtime-v1"
    assert report.runtime_selection.total_cases == 4
    assert report.runtime_selection.total_runs == 8
    assert report.runtime_selection.corpus_policy_diagnostics == []
    assert report.runtime_selection.policy_mandatory.effective_retention == 1.0
    assert report.deterministic_gate_passed
    assert report.grounding_gate_passed
    assert report.policy_mandatory_gate_passed
    assert report.corpus_policy_gate_passed
    assert report.release_gate_passed
