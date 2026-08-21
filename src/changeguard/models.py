from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class ChangeStatus(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    UNKNOWN = "unknown"


class EngineeringSurface(str, Enum):
    API_CONTRACT = "api_contract"
    DATABASE = "database"
    SECURITY = "security"
    MESSAGING = "messaging"
    CONFIG = "config"
    DEPENDENCY = "dependency"
    JAVA_CODE = "java_code"
    DEPLOYMENT = "deployment"
    OBSERVABILITY = "observability"


class EndpointChangeKind(str, Enum):
    ENDPOINT_ADDED = "ENDPOINT_ADDED"
    ENDPOINT_REMOVED = "ENDPOINT_REMOVED"
    ENDPOINT_PATH_CHANGED = "ENDPOINT_PATH_CHANGED"
    ENDPOINT_METHOD_CHANGED = "ENDPOINT_METHOD_CHANGED"
    REQUEST_SIGNATURE_CHANGED = "REQUEST_SIGNATURE_CHANGED"
    RESPONSE_TYPE_CHANGED = "RESPONSE_TYPE_CHANGED"


class SecurityPolicyChangeKind(str, Enum):
    SECURITY_POLICY_ADDED = "SECURITY_POLICY_ADDED"
    SECURITY_POLICY_REMOVED = "SECURITY_POLICY_REMOVED"
    SECURITY_POLICY_CHANGED = "SECURITY_POLICY_CHANGED"


class DependencyKind(str, Enum):
    GATEWAY_ROUTE = "gateway_route"
    SERVICE_URL = "service_url"
    CONFIG_IMPORT = "config_import"


class ImpactKind(str, Enum):
    POTENTIAL_CONSUMER_IMPACT = "POTENTIAL_CONSUMER_IMPACT"


class ImpactMatchLevel(str, Enum):
    SERVICE = "service"
    ENDPOINT = "endpoint"


class VerificationKind(str, Enum):
    MAVEN_MODULE_TESTS = "maven_module_tests"


class VerificationStatus(str, Enum):
    NOT_RUN = "NOT_RUN"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"


class SpringEndpoint(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    controller: str
    method_name: str = Field(alias="methodName")
    http_method: str = Field(alias="httpMethod")
    path: str
    return_type: str = Field(alias="returnType")
    parameter_types: list[str] = Field(default_factory=list, alias="parameterTypes")


class EndpointSemanticChange(BaseModel):
    kind: EndpointChangeKind
    before: SpringEndpoint | None = None
    after: SpringEndpoint | None = None


class SecurityAuthorizationRule(BaseModel):
    selector: str
    patterns: list[str] = Field(default_factory=list)
    action: str


class SpringSecurityPolicy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    component: str
    method_name: str = Field(alias="methodName")
    authorization_rules: list[SecurityAuthorizationRule] = Field(
        default_factory=list,
        alias="authorizationRules",
    )
    disabled_features: list[str] = Field(default_factory=list, alias="disabledFeatures")


class SecuritySemanticChange(BaseModel):
    kind: SecurityPolicyChangeKind
    before: SpringSecurityPolicy | None = None
    after: SpringSecurityPolicy | None = None


class ServiceNode(BaseModel):
    name: str
    module_path: str


class DependencyEdge(BaseModel):
    source: str
    target: str
    kind: DependencyKind
    evidence_path: str
    evidence: str


class ConsumerHttpCall(BaseModel):
    consumer_service: str
    target_service: str
    http_method: str
    path: str
    evidence_path: str
    evidence: str


class ServiceDependencyGraph(BaseModel):
    nodes: list[ServiceNode] = Field(default_factory=list)
    edges: list[DependencyEdge] = Field(default_factory=list)
    consumer_calls: list[ConsumerHttpCall] = Field(default_factory=list)

    def service_for_path(self, path: str) -> str | None:
        normalized = path.replace("\\", "/")
        matching = [
            node
            for node in self.nodes
            if normalized == node.module_path
            or normalized.startswith(node.module_path.rstrip("/") + "/")
        ]
        if not matching:
            return None
        matching.sort(key=lambda node: len(node.module_path), reverse=True)
        return matching[0].name

    def module_for_service(self, service: str) -> str | None:
        for node in self.nodes:
            if node.name == service:
                return node.module_path
        return None

    def direct_dependents(self, service: str) -> list[str]:
        return sorted({edge.source for edge in self.edges if edge.target == service})

    def edges_between(self, source: str, target: str) -> list[DependencyEdge]:
        return [
            edge
            for edge in self.edges
            if edge.source == source and edge.target == target
        ]

    def calls_between(self, consumer: str, target: str) -> list[ConsumerHttpCall]:
        return [
            call
            for call in self.consumer_calls
            if call.consumer_service == consumer and call.target_service == target
        ]


class ImpactCandidate(BaseModel):
    kind: ImpactKind = ImpactKind.POTENTIAL_CONSUMER_IMPACT
    provider_service: str
    consumer_service: str
    changed_file: str
    trigger_kind: EndpointChangeKind
    before: SpringEndpoint | None = None
    after: SpringEndpoint | None = None
    match_level: ImpactMatchLevel = ImpactMatchLevel.SERVICE
    reason: str
    dependency_evidence: list[DependencyEdge] = Field(default_factory=list)
    consumer_call_evidence: list[ConsumerHttpCall] = Field(default_factory=list)
    suppression_reason: str | None = None


class VerificationPlan(BaseModel):
    kind: VerificationKind = VerificationKind.MAVEN_MODULE_TESTS
    provider_service: str
    consumer_service: str
    consumer_module: str
    changed_file: str
    trigger_kind: EndpointChangeKind
    endpoint: SpringEndpoint | None = None
    command: list[str]
    reason: str
    status: VerificationStatus = VerificationStatus.NOT_RUN


class VerificationResult(BaseModel):
    plan: VerificationPlan
    status: VerificationStatus
    exit_code: int | None = None
    duration_seconds: float | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str | None = None


class FileChange(BaseModel):
    status: ChangeStatus
    path: str
    old_path: str | None = None
    language: str = "unknown"
    surfaces: list[EngineeringSurface] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    semantic_changes: list[EndpointSemanticChange] = Field(default_factory=list)
    security_changes: list[SecuritySemanticChange] = Field(default_factory=list)
    service: str | None = None
    direct_dependents: list[str] = Field(default_factory=list)


class ChangeManifest(BaseModel):
    repo: str
    base: str
    head: str
    files: list[FileChange] = Field(default_factory=list)
    dependency_graph: ServiceDependencyGraph | None = None
    impact_analysis_enabled: bool = False
    impact_candidates: list[ImpactCandidate] = Field(default_factory=list)
    suppressed_impact_candidates: list[ImpactCandidate] = Field(default_factory=list)
    verification_planning_enabled: bool = False
    verification_plans: list[VerificationPlan] = Field(default_factory=list)

    @property
    def changed_file_count(self) -> int:
        return len(self.files)

    @property
    def impact_candidate_count(self) -> int:
        return len(self.impact_candidates)

    @property
    def suppressed_impact_candidate_count(self) -> int:
        return len(self.suppressed_impact_candidates)

    @property
    def verification_plan_count(self) -> int:
        return len(self.verification_plans)
