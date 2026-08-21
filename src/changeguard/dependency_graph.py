from __future__ import annotations

import re

from changeguard.github_client import GitHubClient
from changeguard.models import (
    ConsumerHttpCall,
    DependencyEdge,
    DependencyKind,
    ServiceDependencyGraph,
    ServiceNode,
)


MODULE_PREFIX = "spring-petclinic-"
CONFIG_PATH = re.compile(
    r"(?:^|/)src/main/resources/application[^/]*\.(?:yml|yaml|properties)$",
    re.IGNORECASE,
)
CLIENT_SOURCE_PATH = re.compile(
    r"(?:^|/)src/main/java/.+(?:Client|Gateway|Connector)\.java$",
    re.IGNORECASE,
)
LB_URI = re.compile(r"\blb://([A-Za-z0-9_.-]+)")
HTTP_HOST = re.compile(r"\bhttps?://([A-Za-z0-9_.-]+)(?::\d+)?")
EXPLICIT_HTTP_CALL = re.compile(
    r"\.(get|post|put|patch|delete)\s*\(\s*\)\s*"
    r"\.uri\s*\(\s*\"https?://([A-Za-z0-9_.-]+)(?::\d+)?([^\"?#]*)"
    r"(?:\?[^\"#]*)?\"",
    re.IGNORECASE | re.DOTALL,
)


class ServiceDependencyGraphBuilder:
    """Build deterministic cross-service dependency and call-site evidence.

    V2 starts with high-confidence service dependency evidence:
    - Spring Cloud Gateway `lb://service` routes
    - explicit service URLs in application configuration
    - explicit service URLs in Java classes named Client/Gateway/Connector

    V2.2 additionally extracts literal HTTP call sites such as
    `.get().uri("http://customers-service/owners/{ownerId}", ownerId)`.
    Dynamic URI construction is intentionally left unresolved rather than guessed.
    """

    def __init__(self, client: GitHubClient | None = None) -> None:
        self.client = client or GitHubClient()

    def build(self, repo_full_name: str, ref: str) -> ServiceDependencyGraph:
        paths = self.client.list_repository_paths(repo_full_name, ref)
        nodes = self._discover_nodes(paths)
        known_services = {node.name for node in nodes}
        edges: list[DependencyEdge] = []
        consumer_calls: list[ConsumerHttpCall] = []

        for path in paths:
            is_config = bool(CONFIG_PATH.search(path))
            is_client_source = bool(CLIENT_SOURCE_PATH.search(path))
            if not (is_config or is_client_source):
                continue

            source = self._service_for_path(nodes, path)
            if source is None:
                continue

            content = self.client.get_file_text(repo_full_name, path, ref)
            if content is None:
                continue

            edges.extend(
                self._extract_edges(
                    source=source,
                    path=path,
                    content=content,
                    known_services=known_services,
                )
            )
            if is_client_source:
                consumer_calls.extend(
                    self._extract_consumer_calls(
                        source=source,
                        path=path,
                        content=content,
                        known_services=known_services,
                    )
                )

        return ServiceDependencyGraph(
            nodes=nodes,
            edges=self._dedupe_edges(edges),
            consumer_calls=self._dedupe_calls(consumer_calls),
        )

    def _discover_nodes(self, paths: list[str]) -> list[ServiceNode]:
        """Discover Spring service modules at any repository depth.

        The initial Petclinic implementation assumed every service lived directly at
        repository root. Seeded benchmark workspaces and real monorepos can nest
        Maven modules, so the module directory containing a matching `pom.xml` is now
        preserved as the service's full repository-relative module path.
        """
        modules: dict[str, str] = {}
        for path in paths:
            normalized = path.replace("\\", "/")
            parts = normalized.split("/")
            if len(parts) < 2 or parts[-1] != "pom.xml":
                continue

            module_name = parts[-2]
            if not module_name.startswith(MODULE_PREFIX):
                continue

            module_path = "/".join(parts[:-1])
            modules[module_path] = module_name.removeprefix(MODULE_PREFIX)

        return [
            ServiceNode(name=name, module_path=module_path)
            for module_path, name in sorted(modules.items())
        ]

    def _extract_edges(
        self,
        source: str,
        path: str,
        content: str,
        known_services: set[str],
    ) -> list[DependencyEdge]:
        edges: list[DependencyEdge] = []

        for match in LB_URI.finditer(content):
            target = match.group(1)
            if target not in known_services or target == source:
                continue
            edges.append(
                DependencyEdge(
                    source=source,
                    target=target,
                    kind=DependencyKind.GATEWAY_ROUTE,
                    evidence_path=path,
                    evidence=match.group(0),
                )
            )

        for match in HTTP_HOST.finditer(content):
            target = match.group(1)
            if target not in known_services or target == source:
                continue

            kind = (
                DependencyKind.CONFIG_IMPORT
                if target == "config-server" and "configserver:" in content
                else DependencyKind.SERVICE_URL
            )
            edges.append(
                DependencyEdge(
                    source=source,
                    target=target,
                    kind=kind,
                    evidence_path=path,
                    evidence=match.group(0),
                )
            )

        return edges

    def _extract_consumer_calls(
        self,
        source: str,
        path: str,
        content: str,
        known_services: set[str],
    ) -> list[ConsumerHttpCall]:
        calls: list[ConsumerHttpCall] = []
        for match in EXPLICIT_HTTP_CALL.finditer(content):
            http_method = match.group(1).upper()
            target = match.group(2)
            if target not in known_services or target == source:
                continue

            raw_path = match.group(3) or "/"
            normalized_path = self._normalize_call_path(raw_path)
            calls.append(
                ConsumerHttpCall(
                    consumer_service=source,
                    target_service=target,
                    http_method=http_method,
                    path=normalized_path,
                    evidence_path=path,
                    evidence=match.group(0).strip(),
                )
            )
        return calls

    @staticmethod
    def _normalize_call_path(path: str) -> str:
        if not path:
            return "/"
        normalized = "/" + path.lstrip("/")
        if len(normalized) > 1:
            normalized = normalized.rstrip("/")
        return normalized

    @staticmethod
    def _service_for_path(nodes: list[ServiceNode], path: str) -> str | None:
        normalized = path.replace("\\", "/")
        matching = [
            node
            for node in nodes
            if normalized.startswith(node.module_path.rstrip("/") + "/")
        ]
        if not matching:
            return None
        matching.sort(key=lambda node: len(node.module_path), reverse=True)
        return matching[0].name

    @staticmethod
    def _dedupe_edges(edges: list[DependencyEdge]) -> list[DependencyEdge]:
        unique: dict[tuple[str, str, str, str, str], DependencyEdge] = {}
        for edge in edges:
            key = (
                edge.source,
                edge.target,
                edge.kind.value,
                edge.evidence_path,
                edge.evidence,
            )
            unique[key] = edge
        return sorted(
            unique.values(),
            key=lambda edge: (
                edge.source,
                edge.target,
                edge.kind.value,
                edge.evidence_path,
            ),
        )

    @staticmethod
    def _dedupe_calls(calls: list[ConsumerHttpCall]) -> list[ConsumerHttpCall]:
        unique: dict[tuple[str, str, str, str, str], ConsumerHttpCall] = {}
        for call in calls:
            key = (
                call.consumer_service,
                call.target_service,
                call.http_method,
                call.path,
                call.evidence_path,
            )
            unique[key] = call
        return sorted(
            unique.values(),
            key=lambda call: (
                call.consumer_service,
                call.target_service,
                call.http_method,
                call.path,
                call.evidence_path,
            ),
        )
