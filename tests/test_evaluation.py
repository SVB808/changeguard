from pathlib import Path

from changeguard.evaluation import (
    EvaluationDisposition,
    evaluate_corpus,
    load_corpus,
)


CORPUS_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "evaluation"
    / "rest-impact-v1.json"
)


def test_loads_labeled_rest_corpus():
    corpus = load_corpus(CORPUS_PATH)

    assert corpus.version == "rest-impact-v1"
    assert len(corpus.cases) == 11
    assert {case.source for case in corpus.cases} == {
        "public-pr",
        "seeded-pr",
        "synthetic",
    }


def test_reference_corpus_matches_expected_dispositions_and_metrics():
    report = evaluate_corpus(load_corpus(CORPUS_PATH))

    assert report.total_cases == 11
    assert report.exact_matches == 11
    assert report.exact_accuracy == 1.0

    assert report.impact_detection.true_positive == 6
    assert report.impact_detection.false_positive == 0
    assert report.impact_detection.true_negative == 5
    assert report.impact_detection.false_negative == 0
    assert report.impact_detection.precision == 1.0
    assert report.impact_detection.recall == 1.0
    assert report.impact_detection.false_positive_rate == 0.0

    assert report.endpoint_evidence.true_positive == 5
    assert report.endpoint_evidence.false_positive == 0
    assert report.endpoint_evidence.true_negative == 6
    assert report.endpoint_evidence.false_negative == 0
    assert report.verification_plan_accuracy == 1.0


def test_public_pr253_cases_are_suppressed_not_active_impacts():
    report = evaluate_corpus(load_corpus(CORPUS_PATH))
    pr253 = [case for case in report.cases if case.reference and case.reference.endswith("#253")]

    assert len(pr253) == 2
    assert all(case.predicted_impact is False for case in pr253)
    assert all(
        case.actual_disposition == EvaluationDisposition.SUPPRESSED
        for case in pr253
    )
    assert all(case.actual_verification_plan is False for case in pr253)


def test_dynamic_call_case_remains_conservative_at_service_scope():
    report = evaluate_corpus(load_corpus(CORPUS_PATH))
    case = next(
        item for item in report.cases if item.id == "dynamic_unparsed_consumer_call"
    )

    assert case.predicted_impact is True
    assert case.actual_disposition == EvaluationDisposition.SERVICE
    assert case.actual_verification_plan is False
    assert case.analysis_ms >= 0.0
