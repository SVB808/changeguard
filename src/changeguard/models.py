from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


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


class FileChange(BaseModel):
    status: ChangeStatus
    path: str
    old_path: str | None = None
    language: str = "unknown"
    surfaces: list[EngineeringSurface] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class ChangeManifest(BaseModel):
    repo: str
    base: str
    head: str
    files: list[FileChange] = Field(default_factory=list)

    @property
    def changed_file_count(self) -> int:
        return len(self.files)
