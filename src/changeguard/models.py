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


class FileChange(BaseModel):
    status: ChangeStatus
    path: str
    old_path: str | None = None
    language: str = "unknown"
    surfaces: list[EngineeringSurface] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    semantic_changes: list[EndpointSemanticChange] = Field(default_factory=list)


class ChangeManifest(BaseModel):
    repo: str
    base: str
    head: str
    files: list[FileChange] = Field(default_factory=list)

    @property
    def changed_file_count(self) -> int:
        return len(self.files)
