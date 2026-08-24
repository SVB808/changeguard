from datetime import datetime, timezone

from changeguard.models import ConsumerHttpCall, ServiceDependencyGraph
from changeguard.runtime_contracts import (
    RemovalGateStatus,
    RuntimeConsumerClassification,
    RuntimeObservation,
    parse_runtime_payload,
    route_matches,
)
from changeguard.runtime_intelligence import evaluate_removal_gate
from changeguard.runtime_store import RuntimeStore


def _dt(day: int) -> datetime:
    return datetime(2026, 8, day, 12, 0, tzinfo=timezone.utc)


def _graph() -> ServiceDependencyGraph:
    return ServiceDependencyGraph(
        consumer_calls=[
            ConsumerHttpCall(
                consumer_service="checkout-service",
                target_service="orders-service",
                http_method="GET",
                path="/v1/orders/{orderId}",
                evidence_path="checkout/OrdersClient.java",
                evidence="GET old orders route",
            )
        ]
    )


def test_route_matching_handles_runtime_values_and_path_variables():
    assert route_matches("/v1/orders/42?expand=true", "/v1/orders/{orderId}")
    assert route_matches("/v1/orders/{id}", "/v1/orders/{orderId}")
    assert not route_matches("/v2/orders/42", "/v1/orders/{orderId}")


def test_otlp_json_is_normalized_to_runtime_observations():
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "mobile-api"}},
                        {"key": "service.version", "value": {"stringValue": "11"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "spanId": "abc123",
                                "startTimeUnixNano": "1785585600000000000",
                                "attributes": [
                                    {"key": "peer.service", "value": {"stringValue": "orders-service"}},
                                    {"key": "http.request.method", "value": {"stringValue": "GET"}},
                                    {"key": "url.path", "value": {"stringValue": "/v1/orders/42"}},
                                    {"key": "http.response.status_code", "value": {"intValue": "200"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    observations = parse_runtime_payload(payload)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.consumer_service == "mobile-api"
    assert observation.consumer_version == "11"
    assert observation.provider_service == "orders-service"
    assert observation.http_method == "GET"
    assert observation.path == "/v1/orders/42"
    assert observation.status_code == 200
    assert observation.event_id == "abc123"


def test_runtime_store_deduplicates_and_preserves_coverage(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    observation = RuntimeObservation(
        observed_at=_dt(9),
        consumer_service="mobile-api",
        provider_service="orders-service",
        http_method="GET",
        path="/v1/orders/42",
        event_id="span-1",
    )

    assert store.ingest([observation]) == (1, 0)
    assert store.ingest([observation]) == (0, 1)

    store.record_coverage(_dt(1), _dt(5), "otel-a")
    store.record_coverage(_dt(5), _dt(10), "otel-b")
    assert store.latest_contiguous_coverage() == (_dt(1), _dt(10))


def test_runtime_usage_blocks_removal_and_exposes_ghost_dependency(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    store.record_coverage(_dt(1), _dt(10), "otel")
    store.ingest(
        [
            RuntimeObservation(
                observed_at=_dt(9),
                consumer_service="legacy-mobile",
                consumer_version="11",
                provider_service="orders-service",
                http_method="GET",
                path="/v1/orders/42",
                request_count=284,
                event_id="legacy-traffic",
            )
        ]
    )

    report = evaluate_removal_gate(
        store,
        [_graph()],
        provider_service="orders-service",
        http_method="GET",
        path="/v1/orders/{orderId}",
        quiet_window_days=7,
        as_of=_dt(10),
    )

    assert report.status == RemovalGateStatus.BLOCKED_ACTIVE_RUNTIME
    assert report.runtime_request_count == 284
    assert report.static_reference_count == 1
    classifications = {item.consumer_service: item.classification for item in report.consumers}
    assert classifications == {
        "checkout-service": RuntimeConsumerClassification.STATIC_ONLY,
        "legacy-mobile": RuntimeConsumerClassification.RUNTIME_ONLY,
    }
    assert any("Runtime-only consumer" in blocker for blocker in report.blockers)


def test_static_reference_blocks_after_runtime_goes_quiet(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    store.record_coverage(_dt(1), _dt(10), "otel")

    report = evaluate_removal_gate(
        store,
        [_graph()],
        provider_service="orders-service",
        http_method="GET",
        path="/v1/orders/{orderId}",
        quiet_window_days=7,
        as_of=_dt(10),
    )

    assert report.status == RemovalGateStatus.BLOCKED_STATIC_REFERENCE
    assert report.telemetry_coverage_sufficient is True
    assert report.runtime_request_count == 0


def test_contract_becomes_removal_candidate_only_with_quiet_coverage_and_no_static_refs(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    store.record_coverage(_dt(1), _dt(10), "otel")

    report = evaluate_removal_gate(
        store,
        [],
        provider_service="orders-service",
        http_method="GET",
        path="/v1/orders/{orderId}",
        quiet_window_days=7,
        as_of=_dt(10),
    )

    assert report.status == RemovalGateStatus.REMOVAL_CANDIDATE
    assert report.telemetry_coverage_sufficient is True
    assert report.runtime_request_count == 0
    assert report.static_reference_count == 0
    assert "not proof" in report.caveats[-1]


def test_missing_telemetry_coverage_never_clears_contract(tmp_path):
    report = evaluate_removal_gate(
        RuntimeStore(tmp_path / "runtime.db"),
        [],
        provider_service="orders-service",
        http_method="GET",
        path="/v1/orders/{orderId}",
        quiet_window_days=7,
        as_of=_dt(10),
    )

    assert report.status == RemovalGateStatus.INSUFFICIENT_OBSERVATION
    assert report.telemetry_coverage_sufficient is False
