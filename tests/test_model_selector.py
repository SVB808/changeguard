import json
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from changeguard.model_selector import (
    ModelSelectionError,
    OllamaEvidenceSelector,
    OpenAIEvidenceSelector,
)
from changeguard.synthesis import (
    EvidenceCategory,
    EvidenceItem,
    EvidenceTier,
)


class FakeResponses:
    def __init__(self, output_text: str, *, input_tokens: int = 41, output_tokens: int = 7):
        self.output_text = output_text
        self.usage = SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text, usage=self.usage)


class FakeClient:
    def __init__(self, responses: FakeResponses):
        self.responses = responses


class FakeHTTPResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _evidence() -> list[EvidenceItem]:
    return [
        EvidenceItem(
            id="impact:0",
            tier=EvidenceTier.INFERENCE,
            category=EvidenceCategory.IMPACT,
            statement="Endpoint-level impact evidence for provider -> consumer.",
            source_paths=["provider.java", "consumer.java"],
        ),
        EvidenceItem(
            id="semantic:0:0",
            tier=EvidenceTier.FACT,
            category=EvidenceCategory.SEMANTIC_CHANGE,
            statement="ENDPOINT_PATH_CHANGED: /orders/{id} -> /purchases/{id}.",
            source_paths=["provider.java"],
        ),
    ]


def test_openai_selector_uses_strict_structured_output_and_records_usage():
    responses = FakeResponses(
        '{"selected_evidence_ids":["impact:0","semantic:0:0"]}'
    )
    selector = OpenAIEvidenceSelector(
        model="test-model",
        client=FakeClient(responses),
    )

    selection = selector.select(_evidence())

    assert selection.selected_evidence_ids == ["impact:0", "semantic:0:0"]
    assert selection.selector == "openai"
    assert selection.model == "test-model"
    assert selection.input_tokens == 41
    assert selection.output_tokens == 7

    request = responses.calls[0]
    assert request["model"] == "test-model"
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["strict"] is True
    assert request["text"]["format"]["schema"]["additionalProperties"] is False
    assert "untrusted data" in request["instructions"]
    assert "impact:0" in request["input"]
    assert "semantic:0:0" in request["input"]
    assert "tools" not in request


def test_openai_selector_rejects_invalid_structured_payload():
    responses = FakeResponses("not-json")
    selector = OpenAIEvidenceSelector(client=FakeClient(responses))

    with pytest.raises(ModelSelectionError, match="invalid structured evidence"):
        selector.select(_evidence())


def test_openai_selector_rejects_more_than_grounding_limit():
    ids = [f"evidence:{index}" for index in range(13)]
    responses = FakeResponses(
        '{"selected_evidence_ids":' + str(ids).replace("'", '"') + "}"
    )
    selector = OpenAIEvidenceSelector(client=FakeClient(responses))

    with pytest.raises(ModelSelectionError, match="invalid structured evidence"):
        selector.select(_evidence())


def test_openai_selector_skips_provider_call_for_empty_evidence():
    responses = FakeResponses('{"selected_evidence_ids":[]}')
    selector = OpenAIEvidenceSelector(
        model="test-model",
        client=FakeClient(responses),
    )

    selection = selector.select([])

    assert selection.selected_evidence_ids == []
    assert selection.selector == "openai"
    assert selection.model == "test-model"
    assert responses.calls == []


def test_ollama_selector_uses_local_schema_and_records_usage():
    calls = []

    def opener(request, timeout):
        calls.append((request, timeout))
        return FakeHTTPResponse(
            {
                "message": {
                    "role": "assistant",
                    "content": '{"selected_evidence_ids":["impact:0"]}',
                },
                "prompt_eval_count": 73,
                "eval_count": 9,
            }
        )

    selector = OllamaEvidenceSelector(
        model="local-test-model",
        base_url="http://localhost:11434/",
        timeout_seconds=17,
        opener=opener,
    )

    selection = selector.select(_evidence())

    assert selection.selected_evidence_ids == ["impact:0"]
    assert selection.selector == "ollama"
    assert selection.model == "local-test-model"
    assert selection.input_tokens == 73
    assert selection.output_tokens == 9

    request, timeout = calls[0]
    assert request.full_url == "http://localhost:11434/api/chat"
    assert timeout == 17
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["model"] == "local-test-model"
    assert payload["stream"] is False
    assert payload["format"]["additionalProperties"] is False
    assert payload["options"]["temperature"] == 0
    assert "untrusted data" in payload["messages"][0]["content"]
    assert "impact:0" in payload["messages"][1]["content"]


def test_ollama_selector_rejects_invalid_structured_payload():
    def opener(request, timeout):
        return FakeHTTPResponse(
            {"message": {"role": "assistant", "content": "not-json"}}
        )

    selector = OllamaEvidenceSelector(opener=opener)

    with pytest.raises(ModelSelectionError, match="invalid structured evidence"):
        selector.select(_evidence())


def test_ollama_selector_reports_local_connection_failure():
    def opener(request, timeout):
        raise URLError("connection refused")

    selector = OllamaEvidenceSelector(opener=opener)

    with pytest.raises(ModelSelectionError, match="Could not connect to Ollama"):
        selector.select(_evidence())


def test_ollama_selector_skips_local_call_for_empty_evidence():
    calls = []

    def opener(request, timeout):
        calls.append(request)
        raise AssertionError("provider should not be called")

    selector = OllamaEvidenceSelector(model="local-test-model", opener=opener)
    selection = selector.select([])

    assert selection.selected_evidence_ids == []
    assert selection.selector == "ollama"
    assert selection.model == "local-test-model"
    assert calls == []
