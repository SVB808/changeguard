from __future__ import annotations

from enum import Enum
from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from changeguard.models import (
    ChangeManifest,
    ImpactMatchLevel,
    VerificationResult,
    VerificationStatus,
)


MAX_SELECTED_EVIDENCE = 12


class EvidenceTier(str, Enum):
    FACT = "fact"
    INFERENCE = "inference"
    VERIFICATION = "verification"


class EvidenceCategory(str, Enum):
    SEMANTIC_CHANGE = "semantic_change"
    SECURITY_CHANGE = "security_change"
    IMPACT = "impact"
    SUPPRESSED_IMPACT = "suppressed_impact"
    VERIFICATION_PLAN = "verification_plan"
    VERIFICATION_RESULT = "verification_result"


class EvidenceItem(BaseModel):
    id: str
    tier: EvidenceTier
    category: EvidenceCategory
    statement: str
    source_paths: list[str] = Field(default_factory=list)


class SynthesisSelection(BaseModel):
    selected_evidence_ids: list[str] = Field(default_factory=list)
    selector: str = "deterministic"
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class SynthesisReport(BaseModel):
    repo: str
    base: str
    head: str
    headline: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    omitted_evidence_count: int = 0
    caveats: list[str] = Field(default_factory=list)
    selector: str = "deterministic"
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class EvidenceSelector(Protocol):
    def select(self, evidence: list[EvidenceItem]) -> SynthesisSelection: ...


class SynthesisGuardrailError(ValueError):
    pass


class DeterministicEvidenceSelector:
    """Stable default selector used for CI and offline operation."""

    def select(self, evidence: list[EvidenceItem]) -> SynthesisSelection:
        priority = {
            EvidenceTier.VERIFICATION: 0,
            EvidenceTier.INFERENCE: 1,
            EvidenceTier.FACT: 2,
        }
        ordered = sorted(
            evidence,
            key=lambda item: (priority[item.tier], item.id),
        )
        return SynthesisSelection(
            selected_evidence_ids=[item.id for item in ordered[:MAX_SELECTED_EVIDENCE]],
            selector="deterministic",
        )


class SynthesisState(TypedDict, total=False):
    manifest: ChangeManifest
    verification_results: list[VerificationResult]
    evidence: list[EvidenceItem]
    selection: SynthesisSelection
    report: SynthesisReport


def collect_evidence(
    manifest: ChangeManifest,
    verification_results: list[VerificationResult] | None = None,
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []

    for file_index, file in enumerate(manifest.files):
        for change_index, change in enumerate(file.semantic_changes):
            items.append(
                EvidenceItem(
                    id=f"semantic:{file_index}:{change_index}",
                    tier=EvidenceTier.FACT,
                    category=EvidenceCategory.SEMANTIC_CHANGE,
                    statement=_semantic_statement(file.path, change),
                    source_paths=[file.path],
                )
            )
        for change_index, change in enumerate(file.security_changes):
            items.append(
                EvidenceItem(
                    id=f"security:{file_index}:{change_index}",
                    tier=EvidenceTier.FACT,
                    category=EvidenceCategory.SECURITY_CHANGE,
                    statement=(
                        f"{change.kind.value} was extracted from {file.path}. "
                        "This is a deterministic security-policy fact, not a severity rating."
                    ),
                    source_paths=[file.path],
                )
            )

    for index, candidate in enumerate(manifest.impact_candidates):
        scope = candidate.match_level.value
        detail = (
            " Exact consumer HTTP method+route evidence matched the prior provider contract."
            if candidate.match_level == ImpactMatchLevel.ENDPOINT
            else " Exact endpoint call evidence has not been established."
        )
        source_paths = [candidate.changed_file]
        source_paths.extend(edge.evidence_path for edge in candidate.dependency_evidence)
        source_paths.extend(call.evidence_path for call in candidate.consumer_call_evidence)
        items.append(
            EvidenceItem(
                id=f"impact:{index}",
                tier=EvidenceTier.INFERENCE,
                category=EvidenceCategory.IMPACT,
                statement=(
                    f"{scope.capitalize()}-level potential consumer impact: "
                    f"{candidate.provider_service} -> {candidate.consumer_service} for "
                    f"{candidate.trigger_kind.value}.{detail}"
                ),
                source_paths=_dedupe(source_paths),
            )
        )

    for index, candidate in enumerate(manifest.suppressed_impact_candidates):
        source_paths = [candidate.changed_file]
        source_paths.extend(edge.evidence_path for edge in candidate.dependency_evidence)
        source_paths.extend(call.evidence_path for call in candidate.consumer_call_evidence)
        items.append(
            EvidenceItem(
                id=f"suppressed-impact:{index}",
                tier=EvidenceTier.INFERENCE,
                category=EvidenceCategory.SUPPRESSED_IMPACT,
                statement=(
                    f"Service-level candidate {candidate.provider_service} -> "
                    f"{candidate.consumer_service} was suppressed after explicit call-site "
                    f"refinement. {candidate.suppression_reason or ''}"
                ).strip(),
                source_paths=_dedupe(source_paths),
            )
        )

    for index, plan in enumerate(manifest.verification_plans):
        items.append(
            EvidenceItem(
                id=f"verification-plan:{index}",
                tier=EvidenceTier.FACT,
                category=EvidenceCategory.VERIFICATION_PLAN,
                statement=(
                    f"Targeted verification plan exists for {plan.consumer_service}: "
                    f"{' '.join(plan.command)}; current status is {plan.status.value}."
                ),
                source_paths=[plan.changed_file],
            )
        )

    for index, result in enumerate(verification_results or []):
        items.append(_verification_result_item(index, result))

    return items


def build_synthesis_graph(selector: EvidenceSelector | None = None):
    selector = selector or DeterministicEvidenceSelector()

    def collect_node(state: SynthesisState) -> dict:
        return {
            "evidence": collect_evidence(
                state["manifest"],
                state.get("verification_results", []),
            )
        }

    def select_node(state: SynthesisState) -> dict:
        return {"selection": selector.select(state["evidence"])}

    def validate_node(state: SynthesisState) -> dict:
        _validate_selection(state["evidence"], state["selection"])
        return {}

    def render_node(state: SynthesisState) -> dict:
        return {
            "report": _render_report(
                state["manifest"],
                state.get("verification_results", []),
                state["evidence"],
                state["selection"],
            )
        }

    builder = StateGraph(SynthesisState)
    builder.add_node("collect_evidence", collect_node)
    builder.add_node("select_evidence", select_node)
    builder.add_node("validate_selection", validate_node)
    builder.add_node("render_report", render_node)
    builder.add_edge(START, "collect_evidence")
    builder.add_edge("collect_evidence", "select_evidence")
    builder.add_edge("select_evidence", "validate_selection")
    builder.add_edge("validate_selection", "render_report")
    builder.add_edge("render_report", END)
    return builder.compile()


def synthesize_manifest(
    manifest: ChangeManifest,
    verification_results: list[VerificationResult] | None = None,
    selector: EvidenceSelector | None = None,
) -> SynthesisReport:
    graph = build_synthesis_graph(selector)
    output = graph.invoke(
        {
            "manifest": manifest,
            "verification_results": verification_results or [],
        }
    )
    return SynthesisReport.model_validate(output["report"])


def _validate_selection(
    evidence: list[EvidenceItem],
    selection: SynthesisSelection,
) -> None:
    ids = selection.selected_evidence_ids
    if len(ids) > MAX_SELECTED_EVIDENCE:
        raise SynthesisGuardrailError(
            f"Selector chose {len(ids)} evidence items; maximum is {MAX_SELECTED_EVIDENCE}."
        )
    if len(ids) != len(set(ids)):
        raise SynthesisGuardrailError("Selector returned duplicate evidence IDs.")

    known = {item.id for item in evidence}
    unknown = sorted(set(ids) - known)
    if unknown:
        raise SynthesisGuardrailError(
            "Selector referenced evidence IDs that ChangeGuard did not produce: "
            + ", ".join(unknown)
        )


def _render_report(
    manifest: ChangeManifest,
    verification_results: list[VerificationResult],
    evidence: list[EvidenceItem],
    selection: SynthesisSelection,
) -> SynthesisReport:
    selected = {item.id: item for item in evidence}
    rendered = [selected[item_id] for item_id in selection.selected_evidence_ids]
    caveats = [
        "Only supplied ChangeGuard evidence is eligible for synthesis; this graph does not inspect new repository content or execute project code."
    ]

    if selection.selector != "deterministic":
        caveats.append(
            "Model participation is limited to evidence-ID selection; deterministic guardrails validate every selected ID before rendering."
        )
    if manifest.suppressed_impact_candidates:
        caveats.append(
            "Suppressed candidates reduce active findings only for parsed explicit call evidence; dynamic or unsupported callers may still exist."
        )
    if manifest.verification_plans and not verification_results:
        caveats.append(
            "Verification plans remain NOT_RUN until a user explicitly executes them in a local workspace."
        )
    if any(result.status == VerificationStatus.FAILED for result in verification_results):
        caveats.append(
            "FAILED means a selected verification command returned non-zero; it is not automatic proof of production breakage or causal attribution."
        )
    if any(result.status == VerificationStatus.PASSED for result in verification_results):
        caveats.append(
            "PASSED means the selected command exited zero; it does not prove the change is universally safe."
        )

    return SynthesisReport(
        repo=manifest.repo,
        base=manifest.base,
        head=manifest.head,
        headline=_headline(manifest, verification_results),
        evidence=rendered,
        omitted_evidence_count=max(0, len(evidence) - len(rendered)),
        caveats=caveats,
        selector=selection.selector,
        model=selection.model,
        input_tokens=selection.input_tokens,
        output_tokens=selection.output_tokens,
    )


def _headline(
    manifest: ChangeManifest,
    verification_results: list[VerificationResult],
) -> str:
    if any(result.status == VerificationStatus.FAILED for result in verification_results):
        return "At least one targeted verification command returned a non-zero exit status."
    if any(result.status == VerificationStatus.ERROR for result in verification_results):
        return "At least one targeted verification could not be completed."
    if any(
        candidate.match_level == ImpactMatchLevel.ENDPOINT
        for candidate in manifest.impact_candidates
    ):
        return "Compatibility-sensitive cross-service impact evidence reached endpoint scope."
    if manifest.impact_candidates:
        return "Potential cross-service impact remains at service scope."
    if manifest.suppressed_impact_candidates:
        return "No active impact candidate remained after explicit consumer-call refinement."
    return "No active cross-service impact candidate is present in the supplied manifest."


def _semantic_statement(path: str, change) -> str:
    if change.before is not None and change.after is not None:
        return (
            f"{change.kind.value} in {path}: "
            f"{change.before.http_method} {change.before.path} -> "
            f"{change.after.http_method} {change.after.path}."
        )
    endpoint = change.before or change.after
    if endpoint is None:
        return f"{change.kind.value} in {path}."
    side = "before" if change.before is not None else "after"
    return (
        f"{change.kind.value} in {path}: {side} contract is "
        f"{endpoint.http_method} {endpoint.path}."
    )


def _verification_result_item(index: int, result: VerificationResult) -> EvidenceItem:
    consumer = result.plan.consumer_service
    if result.status == VerificationStatus.FAILED:
        statement = (
            f"Verification command for {consumer} exited {result.exit_code}; this is process "
            "evidence and does not by itself prove causal breakage."
        )
    elif result.status == VerificationStatus.PASSED:
        statement = (
            f"Verification command for {consumer} exited 0; this confirms only that the "
            "selected command completed successfully, not that the change is safe."
        )
    elif result.status == VerificationStatus.ERROR:
        statement = (
            f"Verification for {consumer} could not be completed: "
            f"{result.error or 'execution error'}."
        )
    else:
        statement = f"Verification for {consumer} has not been run."

    return EvidenceItem(
        id=f"verification-result:{index}",
        tier=EvidenceTier.VERIFICATION,
        category=EvidenceCategory.VERIFICATION_RESULT,
        statement=statement,
        source_paths=[result.plan.changed_file],
    )


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
