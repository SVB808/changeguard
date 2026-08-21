from __future__ import annotations

import os
import re
from collections import defaultdict
from collections.abc import Callable

from changeguard.github_client import GitHubClient
from changeguard.models import (
    ConsumerHttpCall,
    DependencyEdge,
    DependencyKind,
    ServiceDependencyGraph,
    ServiceNode,
)


CONFIG_PATH = re.compile(
    r"(?:^|/)src/main/resources/application[^/]*\.(?:yml|yaml|properties)$",
    re.IGNORECASE,
)
CLIENT_SOURCE_PATH = re.compile(
    r"(?:^|/)src/main/java/.+(?:Client|Gateway|Connector|Feign)\.java$",
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
REST_TEMPLATE_SIMPLE_CALL = re.compile(
    r"\.(getForObject|getForEntity|postForObject|postForEntity|put|delete)\s*\(\s*"
    r"\"https?://([A-Za-z0-9_.-]+)(?::\d+)?([^\"?#]*)"
    r"(?:\?[^\"#]*)?\"",
    re.IGNORECASE | re.DOTALL,
)
REST_TEMPLATE_EXCHANGE = re.compile(
    r"\.exchange\s*\(\s*"
    r"\"https?://([A-Za-z0-9_.-]+)(?::\d+)?([^\"?#]*)"
    r"(?:\?[^\"#]*)?\"\s*,\s*HttpMethod\.(GET|POST|PUT|PATCH|DELETE)\b",
    re.IGNORECASE | re.DOTALL,
)
FEIGN_CLIENT = re.compile(r"@FeignClient\s*\((?P<args>[^)]*)\)", re.IGNORECASE | re.DOTALL)
REQUEST_MAPPING = re.compile(
    r"@RequestMapping\s*(?:\((?P<args>[^)]*)\))?",
    re.IGNORECASE | re.DOTALL,
)
FEIGN_METHOD_DECL = re.compile(
    r"@(?P<mapping>GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping|RequestMapping)"
    r"\s*(?:\((?P<args>[^)]*)\))?\s*"
    r"(?:public\s+)?[A-Za-z0-9_$.<>?,\[\]\s]+\s+[A-Za-z_$][A-Za-z0-9_$]*\s*"
    r"\([^;{}]*\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
DOTTED_APPLICATION_NAME = re.compile(
    r"^\s*spring\.application\.name\s*[:=]\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
SERVICE_ROLE_SUFFIX = re.compile(r"(?:service|server|gateway)$", re.IGNORECASE)
LITERAL_SERVICE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
ENV_DEFAULT = re.compile(r"^\$\{[^}:]+:([^}]+)\}$")
STRING_LITERAL = re.compile(r'\"([^\"]+)\"')
MAPPING_PATH_NAMED = re.compile(
    r"\b(?:value|path)\s*=\s*\"([^\"]+)\"",
    re.IGNORECASE,
)
FEIGN_TARGET_NAMED = re.compile(
    r"\b(?:name|value)\s*=\s*\"([^\"]+)\"",
    re.IGNORECASE,
)
REQUEST_METHOD = re.compile(
    r"\bRequestMethod\.(GET|POST|PUT|PATCH|DELETE)\b",
    re.IGNORECASE,
)


class ServiceDependencyGraphBuilder:
    """Build deterministic cross-service dependency and call-site evidence.

    Service discovery is repository-agnostic for Maven monorepos. Maven module
    directories come from repository `pom.xml` paths. A literal
    `spring.application.name` in `application*.yml|yaml|properties` is preferred as
    service identity. When no literal name exists, the module basename is used, with
    a conservative sibling-prefix fallback for conventional `*-service`, `*-server`,
    and `*-gateway` module groups.

    High-confidence dependency evidence currently includes:
    - Spring Cloud Gateway `lb://service` routes
    - explicit service URLs in application configuration and client-like Java sources
    - literal OpenFeign `@FeignClient` target declarations

    Consumer HTTP method + route evidence is extracted from literal WebClient,
    RestTemplate, and OpenFeign declarations when possible. Dynamic URI construction
    is intentionally left unresolved rather than guessed.
    """

    def __init__(self, client: GitHubClient | None = None) -> None:
        self.client = client or GitHubClient()

    def build(self, repo_full_name: str, ref: str) -> ServiceDependencyGraph:
        paths = [
            path.replace("\\", "/")
            for path in self.client.list_repository_paths(repo_full_name, ref)
        ]
        content_cache: dict[str, str | None] = {}

        def read_text(path: str) -> str | None:
            if path not in content_cache:
                content_cache[path] = self.client.get_file_text(repo_full_name, path, ref)
            return content_cache[path]

        nodes = self._discover_nodes(paths, read_text)
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

            content = read_text(path)
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

    def _discover_nodes(
        self,
        paths: list[str],
        read_text: Callable[[str], str | None],
    ) -> list[ServiceNode]:
        """Discover Maven-backed service modules without repository-specific naming."""
        all_modules = sorted(
            {
                path[: -len("/pom.xml")]
                for path in paths
                if path.endswith("/pom.xml")
            }
        )
        modules = [
            module
            for module in all_modules
            if self._is_module_candidate(module, all_modules, paths)
        ]
        fallback_names = self._fallback_module_names(modules)
        nodes: list[ServiceNode] = []

        for module in modules:
            application_name = self._application_name_for_module(
                module,
                modules,
                paths,
                read_text,
            )
            nodes.append(
                ServiceNode(
                    name=application_name or fallback_names[module],
                    module_path=module,
                )
            )

        return sorted(nodes, key=lambda node: (node.module_path, node.name))

    @staticmethod
    def _is_module_candidate(
        module: str,
        all_modules: list[str],
        paths: list[str],
    ) -> bool:
        """Exclude pure aggregator modules while retaining leaf or source modules."""
        module_prefix = module.rstrip("/") + "/"
        has_child_module = any(
            other != module and other.startswith(module_prefix)
            for other in all_modules
        )
        has_main_source = any(
            path.startswith(module_prefix + "src/main/")
            for path in paths
        )
        return has_main_source or not has_child_module

    def _application_name_for_module(
        self,
        module: str,
        modules: list[str],
        paths: list[str],
        read_text: Callable[[str], str | None],
    ) -> str | None:
        candidates = [
            path
            for path in paths
            if CONFIG_PATH.search(path)
            and self._module_for_path(modules, path) == module
        ]
        for path in sorted(candidates):
            content = read_text(path)
            if content is None:
                continue
            application_name = self._extract_application_name(content)
            if application_name is not None:
                return application_name
        return None

    @classmethod
    def _extract_application_name(cls, content: str) -> str | None:
        dotted = DOTTED_APPLICATION_NAME.search(content)
        if dotted:
            return cls._literal_service_name(dotted.group(1))

        lines = content.splitlines()
        spring_index = cls._yaml_key_index(lines, "spring")
        if spring_index is None:
            return None
        spring_indent = cls._indent(lines[spring_index])

        application_index = cls._yaml_key_index(
            lines,
            "application",
            start=spring_index + 1,
            parent_indent=spring_indent,
        )
        if application_index is None:
            return None
        application_indent = cls._indent(lines[application_index])

        name_index = cls._yaml_key_index(
            lines,
            "name",
            start=application_index + 1,
            parent_indent=application_indent,
            require_value=True,
        )
        if name_index is None:
            return None

        _, raw_value = lines[name_index].split(":", 1)
        return cls._literal_service_name(raw_value)

    @classmethod
    def _yaml_key_index(
        cls,
        lines: list[str],
        key: str,
        start: int = 0,
        parent_indent: int | None = None,
        require_value: bool = False,
    ) -> int | None:
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.*?)\s*$", re.IGNORECASE)
        for index in range(start, len(lines)):
            line = lines[index]
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = cls._indent(line)
            if parent_indent is not None and indent <= parent_indent:
                return None
            match = pattern.match(line)
            if not match:
                continue
            value = match.group(1).split("#", 1)[0].strip()
            if require_value and not value:
                continue
            return index
        return None

    @staticmethod
    def _indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    @staticmethod
    def _literal_service_name(raw_value: str) -> str | None:
        value = raw_value.split("#", 1)[0].strip().strip("\"'")
        env_default = ENV_DEFAULT.fullmatch(value)
        if env_default:
            value = env_default.group(1).strip().strip("\"'")
        if not value or not LITERAL_SERVICE_NAME.fullmatch(value):
            return None
        return value

    @staticmethod
    def _fallback_module_names(modules: list[str]) -> dict[str, str]:
        """Use module basenames, stripping only safe conventional sibling prefixes."""
        groups: dict[str, list[str]] = defaultdict(list)
        for module in modules:
            parent, _, _ = module.rpartition("/")
            groups[parent].append(module)

        names: dict[str, str] = {}
        for siblings in groups.values():
            basenames = [module.rsplit("/", 1)[-1] for module in siblings]
            prefix = os.path.commonprefix(basenames)
            prefix = prefix[: prefix.rfind("-") + 1] if "-" in prefix else ""
            stripped = [name[len(prefix) :] if prefix else name for name in basenames]
            can_strip = (
                len(siblings) >= 2
                and bool(prefix)
                and all(name and SERVICE_ROLE_SUFFIX.search(name) for name in stripped)
            )

            for module, basename, stripped_name in zip(
                siblings,
                basenames,
                stripped,
                strict=True,
            ):
                names[module] = stripped_name if can_strip else basename

        return names

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

        feign_target = self._extract_feign_target(content)
        if feign_target in known_services and feign_target != source:
            match = FEIGN_CLIENT.search(content)
            assert match is not None
            edges.append(
                DependencyEdge(
                    source=source,
                    target=feign_target,
                    kind=DependencyKind.DECLARATIVE_CLIENT,
                    evidence_path=path,
                    evidence=match.group(0).strip(),
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
        calls.extend(
            self._extract_webclient_calls(source, path, content, known_services)
        )
        calls.extend(
            self._extract_resttemplate_calls(source, path, content, known_services)
        )
        calls.extend(self._extract_feign_calls(source, path, content, known_services))
        return calls

    def _extract_webclient_calls(
        self,
        source: str,
        path: str,
        content: str,
        known_services: set[str],
    ) -> list[ConsumerHttpCall]:
        calls: list[ConsumerHttpCall] = []
        for match in EXPLICIT_HTTP_CALL.finditer(content):
            call = self._absolute_url_call(
                source=source,
                path=path,
                target=match.group(2),
                http_method=match.group(1).upper(),
                raw_path=match.group(3) or "/",
                evidence=match.group(0).strip(),
                known_services=known_services,
            )
            if call is not None:
                calls.append(call)
        return calls

    def _extract_resttemplate_calls(
        self,
        source: str,
        path: str,
        content: str,
        known_services: set[str],
    ) -> list[ConsumerHttpCall]:
        method_map = {
            "getforobject": "GET",
            "getforentity": "GET",
            "postforobject": "POST",
            "postforentity": "POST",
            "put": "PUT",
            "delete": "DELETE",
        }
        calls: list[ConsumerHttpCall] = []

        for match in REST_TEMPLATE_SIMPLE_CALL.finditer(content):
            call = self._absolute_url_call(
                source=source,
                path=path,
                target=match.group(2),
                http_method=method_map[match.group(1).lower()],
                raw_path=match.group(3) or "/",
                evidence=match.group(0).strip(),
                known_services=known_services,
            )
            if call is not None:
                calls.append(call)

        for match in REST_TEMPLATE_EXCHANGE.finditer(content):
            call = self._absolute_url_call(
                source=source,
                path=path,
                target=match.group(1),
                http_method=match.group(3).upper(),
                raw_path=match.group(2) or "/",
                evidence=match.group(0).strip(),
                known_services=known_services,
            )
            if call is not None:
                calls.append(call)

        return calls

    def _absolute_url_call(
        self,
        source: str,
        path: str,
        target: str,
        http_method: str,
        raw_path: str,
        evidence: str,
        known_services: set[str],
    ) -> ConsumerHttpCall | None:
        if target not in known_services or target == source:
            return None
        return ConsumerHttpCall(
            consumer_service=source,
            target_service=target,
            http_method=http_method,
            path=self._normalize_call_path(raw_path),
            evidence_path=path,
            evidence=evidence,
        )

    def _extract_feign_calls(
        self,
        source: str,
        path: str,
        content: str,
        known_services: set[str],
    ) -> list[ConsumerHttpCall]:
        target = self._extract_feign_target(content)
        if target not in known_services or target == source:
            return []

        base_path = self._extract_feign_base_path(content)
        calls: list[ConsumerHttpCall] = []
        for match in FEIGN_METHOD_DECL.finditer(content):
            mapping = match.group("mapping").lower()
            args = match.group("args") or ""
            method = self._mapping_http_method(mapping, args)
            if method is None:
                continue
            method_path = self._mapping_path(args) or "/"
            calls.append(
                ConsumerHttpCall(
                    consumer_service=source,
                    target_service=target,
                    http_method=method,
                    path=self._join_paths(base_path, method_path),
                    evidence_path=path,
                    evidence=match.group(0).strip(),
                )
            )
        return calls

    @classmethod
    def _extract_feign_target(cls, content: str) -> str | None:
        match = FEIGN_CLIENT.search(content)
        if match is None:
            return None
        args = match.group("args") or ""
        named = FEIGN_TARGET_NAMED.search(args)
        if named:
            return cls._literal_service_name(named.group(1))
        first_literal = STRING_LITERAL.search(args)
        if first_literal:
            return cls._literal_service_name(first_literal.group(1))
        return None

    @classmethod
    def _extract_feign_base_path(cls, content: str) -> str:
        interface = re.search(r"\binterface\s+[A-Za-z_$][A-Za-z0-9_$]*", content)
        if interface is None:
            return "/"
        prefix = content[: interface.start()]
        mappings = list(REQUEST_MAPPING.finditer(prefix))
        if not mappings:
            return "/"
        args = mappings[-1].group("args") or ""
        return cls._mapping_path(args) or "/"

    @staticmethod
    def _mapping_http_method(mapping: str, args: str) -> str | None:
        direct = {
            "getmapping": "GET",
            "postmapping": "POST",
            "putmapping": "PUT",
            "patchmapping": "PATCH",
            "deletemapping": "DELETE",
        }
        if mapping in direct:
            return direct[mapping]
        request_method = REQUEST_METHOD.search(args)
        if request_method:
            return request_method.group(1).upper()
        return "ANY"

    @staticmethod
    def _mapping_path(args: str) -> str | None:
        named = MAPPING_PATH_NAMED.search(args)
        if named:
            return named.group(1)
        first_literal = STRING_LITERAL.search(args)
        if first_literal:
            return first_literal.group(1)
        return None

    @classmethod
    def _join_paths(cls, base: str, child: str) -> str:
        base_norm = cls._normalize_call_path(base)
        child_norm = cls._normalize_call_path(child)
        if base_norm == "/":
            return child_norm
        if child_norm == "/":
            return base_norm
        return cls._normalize_call_path(base_norm + "/" + child_norm.lstrip("/"))

    @staticmethod
    def _normalize_call_path(path: str) -> str:
        if not path:
            return "/"
        normalized = "/" + path.lstrip("/")
        if len(normalized) > 1:
            normalized = normalized.rstrip("/")
        return normalized

    @staticmethod
    def _module_for_path(modules: list[str], path: str) -> str | None:
        normalized = path.replace("\\", "/")
        matching = [
            module
            for module in modules
            if normalized.startswith(module.rstrip("/") + "/")
        ]
        if not matching:
            return None
        return max(matching, key=len)

    @classmethod
    def _service_for_path(cls, nodes: list[ServiceNode], path: str) -> str | None:
        modules = [node.module_path for node in nodes]
        module = cls._module_for_path(modules, path)
        if module is None:
            return None
        return next(node.name for node in nodes if node.module_path == module)

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
