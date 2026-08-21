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
    / "rest-impact-v2.json"
)


def test_loads_labeled_rest_corpus():
    corpus = load_corpus(CORPUS_PATH)

    assert corpus.version == "rest-impact-v2"
    assert len(corpus.cases) == 22
    assert {case.source for case in corpus.cases} == {
        "public-pr",
        "seeded-pr",
        "synthetic",
    }


def test_reference_corpus_matches_expected_dispositions_and_metrics():
    report = evaluate_corpus(load_corpus(CORPUS_PATH))

    assert report.total_cases == 22
    assert report.exact_matches == 22
    assert report.exact_accuracy == 1.0

    assert report.impact_detection.true_positive == 11
    assert report.impact_detection.false_positive == 0
    assert report.impact_detection.true_negative == 11
    assert report.impact_detection.false_negative == 0
    assert report.impact_detection.precision == 1.0
    assert report.impact_detection.recall == 1.0
    assert report.impact_detection.false_positive_rate == 0.0

    assert report.endpoint_evidence.true_positive == 10
    assert report.endpoint_evidence.false_positive == 0
    assert report.endpoint_evidence.true_negative == 12
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


def test_wildcard_route_cases_distinguish_single_and_recursive_scope():
    report = evaluate_corpus(load_corpus(CORPUS_PATH))
    by_id = {case.id: case for case in report.cases}

    assert by_id["recursive_wildcard_nested_call"].actual_disposition == EvaluationDisposition.ENDPOINT
    assert by_id["single_wildcard_one_segment"].actual_disposition == EvaluationDisposition.ENDPOINT
    assert by_id["single_wildcard_crosses_segments"].actual_disposition == EvaluationDisposition.SUPPRESSED


def test_query_any_and_multiple_call_cases_retain_endpoint_evidence():
    report = evaluate_corpus(load_corpus(CORPUS_PATH))
    by_id = {case.id: case for case in report.cases}

    for case_id in (
        "query_string_exact_call",
        "any_method_mapping_post_consumer",
        "multiple_calls_one_exact",
    ):
        assert by_id[case_id].actual_disposition == EvaluationDisposition.ENDPOINT
        assert by_id[case_id].actual_verification_plan is True
