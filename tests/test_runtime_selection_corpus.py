from changeguard.effective_selection_evaluation import _diagnose_corpus_policy
from changeguard.runtime_selection_corpus import build_runtime_selection_corpus
from changeguard.synthesis import EvidenceCategory, decision_critical_evidence_ids


def test_runtime_selection_corpus_uses_runtime_provenance_for_active_impacts():
    corpus = build_runtime_selection_corpus()

    assert corpus.version == "synthesis-selection-runtime-v1"
    assert len(corpus.cases) == 4

    for case in corpus.cases:
        evidence_by_id = {item.id: item for item in case.evidence}
        semantic_paths = {
            path
            for item in case.evidence
            if item.category == EvidenceCategory.SEMANTIC_CHANGE
            for path in item.source_paths
        }
        for item in case.evidence:
            if item.category == EvidenceCategory.IMPACT and semantic_paths:
                assert semantic_paths.intersection(item.source_paths)

        mandatory = set(decision_critical_evidence_ids(case.evidence))
        active_impact_ids = {
            item.id for item in case.evidence if item.category == EvidenceCategory.IMPACT
        }
        assert active_impact_ids <= mandatory
        assert set(case.verification_critical_ids) <= mandatory
        assert set(evidence_by_id) == (
            set(case.required_evidence_ids)
            | set(case.optional_evidence_ids)
            | set(case.distractor_evidence_ids)
        )


def test_runtime_selection_corpus_has_no_policy_semantics_warnings():
    corpus = build_runtime_selection_corpus()

    assert _diagnose_corpus_policy(corpus) == []
