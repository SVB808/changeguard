from pathlib import Path

from changeguard.evaluation import (
    ConsumerTechnology,
    EvaluationDisposition,
    evaluate_corpus,
    load_corpus,
)


EVALUATION_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "evaluation"
V2_CORPUS_PATH = EVALUATION_DIR / "rest-impact-v2.json"
CORPUS_PATH = EVALUATION_DIR / "rest-impact-v3.json"


def test_loads_inherited_technology_aware_rest_corpus():
    v2 = load_corpus(V2_CORPUS_PATH)
    corpus = load_corpus(CORPUS_PATH)

    assert v2.version == "rest-impact-v2"
    assert len(v2.cases) == 22
    assert corpus.version == "rest-impact-v3"
    assert len(corpus.cases) == 24
    assert {case.source for case in corpus.cases} == {
        "public-pr",
        "seeded-pr",
        "synthetic",
    }


def test_reference_corpus_matches_expected_dispositions_and_metrics():
    report = evaluate_corpus(load_corpus(CORPUS_PATH))

    assert report.total_cases == 24
    assert report.exact_matches == 24
    assert report.exact_accuracy == 1.0

    assert report.impact_detection.true_positive == 13
    assert report.impact_detection.false_positive == 0
    assert report.impact_detection.true_negative == 11
    assert report.impact_detection.false_negative == 0
    assert report.impact_detection.precision == 1.0
    assert report.impact_detection.recall == 1.0
    assert report.impact_detection.false_positive_rate == 0.0

    assert report.endpoint_evidence.true_positive == 12
    assert report.endpoint_evidence.false_positive == 0
    assert report.endpoint_evidence.true_negative == 12
    assert report.endpoint_evidence.false_negative == 0
    assert report.verification_plan_accuracy == 1.0


def test_technology_breakdown_reports_webclient_feign_and_resttemplate():
    report = evaluate_corpus(load_corpus(CORPUS_PATH))
    by_technology = {
        item.technology: item for item in report.technology_breakdown
    }

    assert set(by_technology) == {
        ConsumerTechnology.WEBCLIENT,
        ConsumerTechnology.FEIGN,
        ConsumerTechnology.RESTTEMPLATE,
    }

    webclient = by_technology[ConsumerTechnology.WEBCLIENT]
    assert webclient.total_cases == 3
    assert webclient.exact_matches == 3
    assert webclient.impact_detection.true_positive == 1
    assert webclient.impact_detection.true_negative == 2
    assert webclient.endpoint_evidence.true_positive == 1
    assert webclient.endpoint_evidence.true_negative == 2
    assert webclient.verification_plan_accuracy == 1.0

    for technology in (
        ConsumerTechnology.FEIGN,
        ConsumerTechnology.RESTTEMPLATE,
    ):
        metrics = by_technology[technology]
        assert metrics.total_cases == 1
        assert metrics.exact_matches == 1
        assert metrics.impact_detection.true_positive == 1
        assert metrics.impact_detection.false_positive == 0
        assert metrics.endpoint_evidence.true_positive == 1
        assert metrics.verification_plan_accuracy == 1.0


def test_seeded_client_style_cases_are_endpoint_impacts_with_plans():
    report = evaluate_corpus(load_corpus(CORPUS_PATH))
    seeded = [
        case
        for case in report.cases
        if case.reference == "SVB808/changeguard#16"
    ]

    assert len(seeded) == 2
    assert {case.consumer_technology for case in seeded} == {
        ConsumerTechnology.FEIGN,
        ConsumerTechnology.RESTTEMPLATE,
    }
    assert all(case.predicted_impact is True for case in seeded)
    assert all(
        case.actual_disposition == EvaluationDisposition.ENDPOINT
        for case in seeded
    )
    assert all(case.actual_verification_plan is True for case in seeded)


def test_public_pr253_cases_are_suppressed_not_active_impacts():
    report = evaluate_corpus(load_corpus(CORPUS_PATH))
    pr253 = [case for case in report.cases if case.reference and case.reference.endswith("#253")]

    assert len(pr253) == 2
    assert all(case.consumer_technology == ConsumerTechnology.WEBCLIENT for case in pr253)
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
