from __future__ import annotations

import re

from changeguard.github_client import GitHubClient
from changeguard.models import (
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


class ServiceDependencyGraphBuilder:
    """Build a small deterministic cross-service graph from repository evidence.

    V2 intentionally starts with high-confidence evidence sources instead of trying
    to understand every possible Java HTTP client pattern:
    - Spring Cloud Gateway `lb://service` routes
    - explicit service URLs in application configuration
    - explicit service URLs in Java classes named Client/Gateway/Connector
    """

    def __init__(self, client: GitHubClient | None = None) -> None:
        self.client = client or GitHubClient()

    def build(self, repo_full_name: str, ref: str) -> ServiceDependencyGraph:
        paths = self.client.list_repository_paths(repo_full_name, ref)
        nodes = self._discover_nodes(paths)
        known_services = {node.name for node in nodes}
        edges: list[DependencyEdge] = []

        for path in paths:
            if not (CONFIG_PATH.search(path) or CLIENT_SOURCE_PATH.search(path)):
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

        return ServiceDependencyGraph(
            nodes=nodes,
            edges=self._dedupe_edges(edges),
        )

    def _discover_nodes(self, paths: list[str]) -> list[ServiceNode]:
        modules: set[str] = set()
        for path in paths:
            parts = path.replace("\\", "/").split("/")
            if len(parts) == 2 and parts[1] == "pom.xml" and parts[0].startswith(MODULE_PREFIX):
                modules.add(parts[0])

        return [
            ServiceNode(
                name=module.removeprefix(MODULE_PREFIX),
                module_path=module,
            )
            for module in sorted(modules)
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

    @staticmethod
    def _service_for_path(nodes: list[ServiceNode], path: str) -> str | None:
        normalized = path.replace("\\", "/")
        for node in nodes:
            if normalized.startswith(node.module_path.rstrip("/") + "/"):
                return node.name
        return None

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
