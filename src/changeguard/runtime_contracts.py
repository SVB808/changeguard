from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from changeguard.models import ServiceDependencyGraph


class RuntimeConsumerClassification(str, Enum):
    KNOWN_ACTIVE = "known_active"
    STATIC_ONLY = "static_only"
    RUNTIME_ONLY = "runtime_only"


class RemovalGateStatus(str, Enum):
    BLOCKED_ACTIVE_RUNTIME = "BLOCKED_ACTIVE_RUNTIME"
    BLOCKED_STATIC_REFERENCE = "BLOCKED_STATIC_REFERENCE"
    INSUFFICIENT_OBSERVATION = "INSUFFICIENT_OBSERVATION"
    REMOVAL_CANDIDATE = "REMOVAL_CANDIDATE"


class RuntimeObservation(BaseModel):
    observed_at: datetime
    consumer_service: str
    provider_service: str
    http_method: str
    path: str
    request_count: int = Field(default=1, ge=1)
    consumer_version: str | None = None
    provider_version: str | None = None
    status_code: int | None = None
    source: str = "otel"
    event_id: str | None = None

    @field_validator("observed_at")
    @classmethod
    def _normalize_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @field_validator("http_method")
    @classmethod
    def _normalize_method(cls, value: str) -> str:
        return value.upper().strip()

    @field_validator("path")
    @classmethod
    def _normalize_path(cls, value: str) -> str:
        return normalize_route(value)

    @field_validator("consumer_service", "provider_service")
    @classmethod
    def _nonempty_service(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("service name cannot be empty")
        return normalized

    def stable_event_id(self) -> str:
        if self.event_id:
            return self.event_id
        payload = {
            "observed_at": self.observed_at.isoformat(),
            "consumer_service": self.consumer_service,
            "provider_service": self.provider_service,
            "http_method": self.http_method,
            "path": self.path,
            "request_count": self.request_count,
            "consumer_version": self.consumer_version,
            "provider_version": self.provider_version,
            "status_code": self.status_code,
            "source": self.source,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class RuntimeConsumerSummary(BaseModel):
    consumer_service: str
    classification: RuntimeConsumerClassification
    static_reference: bool
    static_evidence_paths: list[str] = Field(default_factory=list)
    runtime_request_count: int = 0
    runtime_last_seen: datetime | None = None
    runtime_versions: list[str] = Field(default_factory=list)


class ContractRemovalReport(BaseModel):
    provider_service: str
    http_method: str
    path: str
    status: RemovalGateStatus
    quiet_window_days: int
    as_of: datetime
    telemetry_coverage_start: datetime | None = None
    telemetry_coverage_end: datetime | None = None
    telemetry_coverage_sufficient: bool = False
    runtime_request_count: int = 0
    runtime_last_seen: datetime | None = None
    static_reference_count: int = 0
    consumers: list[RuntimeConsumerSummary] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


def normalize_route(path: str) -> str:
    route = path.split("?", 1)[0].strip()
    if "://" in route:
        route = urlparse(route).path
    route = "/" + route.lstrip("/")
    if len(route) > 1:
        route = route.rstrip("/")
    return route


def route_matches(observed_path: str, contract_path: str) -> bool:
    observed = normalize_route(observed_path)
    contract = normalize_route(contract_path)

    pattern_parts: list[str] = []
    index = 0
    while index < len(contract):
        char = contract[index]
        if char == "{":
            closing = contract.find("}", index + 1)
            if closing != -1:
                pattern_parts.append(r"[^/]+")
                index = closing + 1
                continue
        if contract.startswith("**", index):
            pattern_parts.append(r".*")
            index += 2
            continue
        if char == "*":
            pattern_parts.append(r"[^/]*")
            index += 1
            continue
        pattern_parts.append(re.escape(char))
        index += 1

    return re.fullmatch("".join(pattern_parts), observed) is not None


def static_consumers_for_contract(
    graphs: list[ServiceDependencyGraph],
    provider_service: str,
    http_method: str,
    path: str,
) -> dict[str, list[str]]:
    method = http_method.upper()
    consumers: dict[str, set[str]] = {}
    for graph in graphs:
        for call in graph.consumer_calls:
            if call.target_service != provider_service:
                continue
            if call.http_method.upper() != method:
                continue
            if not route_matches(call.path, path):
                continue
            consumers.setdefault(call.consumer_service, set()).add(call.evidence_path)
    return {
        consumer: sorted(paths)
        for consumer, paths in sorted(consumers.items())
    }


def parse_runtime_payload(payload: Any, source: str = "otel") -> list[RuntimeObservation]:
    if isinstance(payload, list):
        return [
            RuntimeObservation.model_validate({**item, "source": item.get("source", source)})
            for item in payload
        ]

    if not isinstance(payload, dict):
        raise ValueError("runtime payload must be a JSON object or array")

    if "observations" in payload:
        observations = payload["observations"]
        if not isinstance(observations, list):
            raise ValueError("'observations' must be a JSON array")
        return [
            RuntimeObservation.model_validate({**item, "source": item.get("source", source)})
            for item in observations
        ]

    if "resourceSpans" in payload:
        return _parse_otlp_json(payload, source=source)

    return [RuntimeObservation.model_validate({**payload, "source": payload.get("source", source)})]


def _parse_otlp_json(payload: dict[str, Any], source: str) -> list[RuntimeObservation]:
    observations: list[RuntimeObservation] = []

    for resource_span in payload.get("resourceSpans", []):
        resource = resource_span.get("resource", {})
        resource_attrs = _attribute_map(resource.get("attributes", []))
        consumer = _string_value(resource_attrs.get("service.name"))
        consumer_version = _string_value(resource_attrs.get("service.version"))
        if not consumer:
            continue

        for scope_span in resource_span.get("scopeSpans", []):
            for span in scope_span.get("spans", []):
                attrs = _attribute_map(span.get("attributes", []))
                provider = _first_string(
                    attrs,
                    [
                        "changeguard.target_service",
                        "peer.service",
                        "server.address",
                        "net.peer.name",
                    ],
                )
                method = _first_string(attrs, ["http.request.method", "http.method"])
                path = _first_string(attrs, ["http.route", "url.path", "http.target"])
                if path is None:
                    url = _first_string(attrs, ["url.full", "http.url"])
                    if url:
                        path = urlparse(url).path

                observed_at = _span_datetime(span.get("startTimeUnixNano"))
                if not provider or not method or not path or observed_at is None:
                    continue

                provider = _normalize_provider_name(provider)
                status_code = _int_value(
                    attrs.get("http.response.status_code", attrs.get("http.status_code"))
                )
                event_id = _string_value(span.get("spanId"))
                observations.append(
                    RuntimeObservation(
                        observed_at=observed_at,
                        consumer_service=consumer,
                        provider_service=provider,
                        http_method=method,
                        path=path,
                        consumer_version=consumer_version,
                        status_code=status_code,
                        source=source,
                        event_id=event_id,
                    )
                )

    return observations


def _attribute_map(attributes: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for attribute in attributes:
        key = attribute.get("key")
        value = attribute.get("value")
        if isinstance(key, str):
            result[key] = value
    return result


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return str(value)

    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in value:
            return str(value[key])
    return None


def _int_value(value: Any) -> int | None:
    raw = _string_value(value)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _first_string(attributes: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = _string_value(attributes.get(key))
        if value:
            return value
    return None


def _span_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        nanoseconds = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(nanoseconds / 1_000_000_000, tz=timezone.utc)


def _normalize_provider_name(value: str) -> str:
    host = value.strip()
    if ":" in host and not host.startswith("["):
        host = host.split(":", 1)[0]
    return host
