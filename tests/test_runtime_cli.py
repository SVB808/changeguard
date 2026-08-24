import json

from typer.testing import CliRunner

from changeguard.runtime_cli import runtime_app


runner = CliRunner()


def test_runtime_cli_records_coverage_observation_and_blocks_removal(tmp_path):
    db = tmp_path / "runtime.db"

    coverage = runner.invoke(
        runtime_app,
        [
            "coverage",
            "--db",
            str(db),
            "--start",
            "2026-08-01T00:00:00+00:00",
            "--end",
            "2026-08-10T00:00:00+00:00",
        ],
    )
    assert coverage.exit_code == 0

    observe = runner.invoke(
        runtime_app,
        [
            "observe",
            "--db",
            str(db),
            "--consumer",
            "legacy-mobile",
            "--consumer-version",
            "11",
            "--provider",
            "orders-service",
            "--method",
            "GET",
            "--path",
            "/v1/orders/42",
            "--at",
            "2026-08-09T00:00:00+00:00",
            "--count",
            "17",
        ],
    )
    assert observe.exit_code == 0

    result = runner.invoke(
        runtime_app,
        [
            "removal-gate",
            "--db",
            str(db),
            "--provider",
            "orders-service",
            "--method",
            "GET",
            "--path",
            "/v1/orders/{orderId}",
            "--quiet-days",
            "7",
            "--as-of",
            "2026-08-10T00:00:00+00:00",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED_ACTIVE_RUNTIME"
    assert payload["runtime_request_count"] == 17
    assert payload["consumers"][0]["classification"] == "runtime_only"


def test_runtime_ingest_accepts_normalized_observation_bundle(tmp_path):
    db = tmp_path / "runtime.db"
    payload_path = tmp_path / "runtime.json"
    payload_path.write_text(
        json.dumps(
            {
                "observations": [
                    {
                        "observed_at": "2026-08-09T00:00:00+00:00",
                        "consumer_service": "checkout-service",
                        "provider_service": "orders-service",
                        "http_method": "GET",
                        "path": "/v1/orders/42",
                        "request_count": 3,
                        "event_id": "evt-1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        runtime_app,
        [
            "ingest",
            "--file",
            str(payload_path),
            "--db",
            str(db),
            "--coverage-start",
            "2026-08-01T00:00:00+00:00",
            "--coverage-end",
            "2026-08-10T00:00:00+00:00",
        ],
    )

    assert result.exit_code == 0
    assert "inserted=1" in result.stdout
    assert "parsed=1" in result.stdout
