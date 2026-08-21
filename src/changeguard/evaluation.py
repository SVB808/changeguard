from __future__ import annotations

import json
import math
import time
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from changeguard.impact_analysis import (
    generate_impact_candidates,
    refine_impact_candidates,
)
from changeguard.models import (
    ChangeStatus,
    ConsumerHttpCall,
    DependencyEdge,
    DependencyKind,
    EndpointChangeKind,
    EndpointSemanticChange,
    FileChange,
    ImpactMatchLevel,
    ServiceDependencyGraph,
    ServiceNode,
    SpringEndpoint,
)
from changeguard.verification import build_verification_plans


class EvaluationDisposition(str, Enum):
    NONE = "none"
    SUPPRESSED = "suppressed"
    SERVICE = "service"
    ENDPOINT = "endpoint"


class EndpointSpec(BaseModel):
    method: str
    path: str
    parameter_types: list[str] = Field(default_factory=list)
    return_type: str = "Object"


class ChangeSpec(BaseModel):
    kind: EndpointChangeKind
    before: EndpointSpec | None = None
    after: EndpointSpec | None = None


class ConsumerCallSpec(BaseModel):
    method: str
    path: str


class ExpectedOutcome(BaseModel):
    impact: bool
    disposition: EvaluationDisposition
    verification_plan: bool


class BenchmarkCase(BaseModel):
    id: str
    description: str
    source: str
    reference: str | None = None
    provider_service: str
    consumer_service: str
    dependency: bool = True
    change: ChangeSpec
    consumer_calls: list[ConsumerCallSpec] = Field(default_factory=list)
    expected: ExpectedOutcome


class BenchmarkCorpus(BaseModel):
    version: str
    description: str
    cases: list[BenchmarkCase]


class ConfusionMetrics(BaseModel):
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    false_positive_rate: float


class CaseEvaluation(BaseModel):
    id: str
    source: str
    reference: str | None = None
    trigger: EndpointChangeKind
    expected_impact: bool
    predicted_impact: bool
    expected_disposition: EvaluationDisposition
    actual_disposition: EvaluationDisposition
    expected_verification_plan: bool
    actual_verification_plan: bool
    analysis_ms: float

    @property
    def exact_match(self) -> bool:
        return (
            self.expected_disposition == self.actual_disposition
            and self.expected_verification_plan == self.actual_verification_plan
        )


class EvaluationReport(BaseModel):
    corpus_version: str
    total_cases: int
    exact_matches: int
    exact_accuracy: float
    impact_detection: ConfusionMetrics
    endpoint_evidence: ConfusionMetrics
    verification_plan_accuracy: float
    p50_analysis_ms: float
    p95_analysis_ms: float
    cases: list[CaseEvaluation]


def load_corpus(path: Path | str) -> BenchmarkCorpus:
    corpus_path = Path(path)
    payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    return BenchmarkCorpus.model_validate(payload)


def evaluate_corpus(corpus: BenchmarkCorpus) -> EvaluationReport:
    results = [_evaluate_case(case) for case in corpus.cases]

    impact_metrics = _confusion(
        expected=[result.expected_impact for result in results],
        predicted=[result.predicted_impact for result in results],
    )
    endpoint_metrics = _confusion(
        expected=[
            result.expected_disposition == EvaluationDisposition.ENDPOINT
            for result in results
        ],
        predicted=[
            result.actual_disposition == EvaluationDisposition.ENDPOINT
            for result in results
        ],
    )

    exact_matches = sum(result.exact_match for result in results)
    verification_matches = sum(
        result.expected_verification_plan == result.actual_verification_plan
        for result in results
    )
    durations = [result.analysis_ms for result in results]

    return EvaluationReport(
        corpus_version=corpus.version,
        total_cases=len(results),
        exact_matches=exact_matches,
        exact_accuracy=_ratio(exact_matches, len(results)),
        impact_detection=impact_metrics,
        endpoint_evidence=endpoint_metrics,
        verification_plan_accuracy=_ratio(verification_matches, len(results)),
        p50_analysis_ms=_percentile(durations, 0.50),
        p95_analysis_ms=_percentile(durations, 0.95),
        cases=results,
    )


def _evaluate_case(case: BenchmarkCase) -> CaseEvaluation:
    graph = _graph_for_case(case)
    file = _file_for_case(case)

    started = time.perf_counter()
    service_candidates = generate_impact_candidates([file], graph)
    active, suppressed = refine_impact_candidates(service_candidates, graph)
    plans = build_verification_plans(active, graph)
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    if any(candidate.match_level == ImpactMatchLevel.ENDPOINT for candidate in active):
        disposition = EvaluationDisposition.ENDPOINT
    elif active:
        disposition = EvaluationDisposition.SERVICE
    elif suppressed:
        disposition = EvaluationDisposition.SUPPRESSED
    else:
        disposition = EvaluationDisposition.NONE

    return CaseEvaluation(
        id=case.id,
        source=case.source,
        reference=case.reference,
        trigger=case.change.kind,
        expected_impact=case.expected.impact,
        predicted_impact=bool(active),
        expected_disposition=case.expected.disposition,
        actual_disposition=disposition,
        expected_verification_plan=case.expected.verification_plan,
        actual_verification_plan=bool(plans),
        analysis_ms=elapsed_ms,
    )


def _graph_for_case(case: BenchmarkCase) -> ServiceDependencyGraph:
    provider_module = f"benchmark/{case.id}/{case.provider_service}"
    consumer_module = f"benchmark/{case.id}/{case.consumer_service}"

    edges: list[DependencyEdge] = []
    if case.dependency:
        edges.append(
            DependencyEdge(
                source=case.consumer_service,
                target=case.provider_service,
                kind=DependencyKind.SERVICE_URL,
                evidence_path=f"{consumer_module}/Client.java",
                evidence=f"http://{case.provider_service}",
            )
        )

    calls = [
        ConsumerHttpCall(
            consumer_service=case.consumer_service,
            target_service=case.provider_service,
            http_method=call.method.upper(),
            path=call.path,
            evidence_path=f"{consumer_module}/Client.java",
            evidence=f"{call.method.upper()} {call.path}",
        )
        for call in case.consumer_calls
    ]

    return ServiceDependencyGraph(
        nodes=[
            ServiceNode(name=case.provider_service, module_path=provider_module),
            ServiceNode(name=case.consumer_service, module_path=consumer_module),
        ],
        edges=edges,
        consumer_calls=calls,
    )


def _file_for_case(case: BenchmarkCase) -> FileChange:
    provider_module = f"benchmark/{case.id}/{case.provider_service}"
    semantic_change = EndpointSemanticChange(
        kind=case.change.kind,
        before=_endpoint(case.change.before),
        after=_endpoint(case.change.after),
    )
    return FileChange(
        status=ChangeStatus.MODIFIED,
        path=f"{provider_module}/ProviderResource.java",
        language="java",
        service=case.provider_service,
        semantic_changes=[semantic_change],
    )


def _endpoint(spec: EndpointSpec | None) -> SpringEndpoint | None:
    if spec is None:
        return None
    return SpringEndpoint(
        controller="ProviderResource",
        methodName="handle",
        httpMethod=spec.method.upper(),
        path=spec.path,
        returnType=spec.return_type,
        parameterTypes=spec.parameter_types,
    )


def _confusion(expected: list[bool], predicted: list[bool]) -> ConfusionMetrics:
    tp = sum(e and p for e, p in zip(expected, predicted, strict=True))
    fp = sum((not e) and p for e, p in zip(expected, predicted, strict=True))
    tn = sum((not e) and (not p) for e, p in zip(expected, predicted, strict=True))
    fn = sum(e and (not p) for e, p in zip(expected, predicted, strict=True))
    return ConfusionMetrics(
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        precision=_ratio(tp, tp + fp),
        recall=_ratio(tp, tp + fn),
        false_positive_rate=_ratio(fp, fp + tn),
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]
