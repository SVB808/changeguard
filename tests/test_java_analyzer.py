import json

import pytest

from changeguard.java_analyzer import JavaAnalyzerError, parse_semantic_changes
from changeguard.models import EndpointChangeKind


def test_parses_java_analyzer_change_payload():
    payload = {
        "beforeEndpoints": [],
        "afterEndpoints": [
            {
                "controller": "VetResource",
                "methodName": "health",
                "httpMethod": "GET",
                "path": "/vets/health",
                "returnType": "String",
                "parameterTypes": [],
            }
        ],
        "changes": [
            {
                "kind": "ENDPOINT_ADDED",
                "before": None,
                "after": {
                    "controller": "VetResource",
                    "methodName": "health",
                    "httpMethod": "GET",
                    "path": "/vets/health",
                    "returnType": "String",
                    "parameterTypes": [],
                },
            }
        ],
    }

    changes = parse_semantic_changes(json.dumps(payload))

    assert len(changes) == 1
    change = changes[0]
    assert change.kind == EndpointChangeKind.ENDPOINT_ADDED
    assert change.after is not None
    assert change.after.controller == "VetResource"
    assert change.after.method_name == "health"
    assert change.after.http_method == "GET"
    assert change.after.path == "/vets/health"
    assert change.after.return_type == "String"


def test_rejects_invalid_java_analyzer_json():
    with pytest.raises(JavaAnalyzerError):
        parse_semantic_changes("not-json")
