from types import SimpleNamespace

import pytest

from changeguard.model_selector import ModelSelectionError, OpenAIEvidenceSelector
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
