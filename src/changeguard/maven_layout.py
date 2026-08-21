from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import xml.etree.ElementTree as ET

from changeguard.github_client import GitHubClient


@dataclass(frozen=True)
class MavenModuleLayout:
    """Repository-relative Maven execution coordinates for one module."""

    module_path: str
    build_root: str
    build_pom: str
    module_selector: str | None
    evidence_paths: tuple[str, ...]


class MavenBuildLayoutBuilder:
    """Discover Maven reactor roots from explicit `<modules>` declarations.

    The builder intentionally uses only repository evidence at the requested ref. It does
    not infer an aggregator merely because a parent directory happens to contain a POM.
    When a module has no enclosing reactor declaration, it is treated as a standalone
    Maven build and its own POM becomes the build POM.
    """

    def __init__(self, client: GitHubClient | None = None) -> None:
        self.client = client or GitHubClient()

    def build(self, repo_full_name: str, ref: str) -> dict[str, MavenModuleLayout]:
        paths = [
            path.replace("\\", "/")
            for path in self.client.list_repository_paths(repo_full_name, ref)
        ]
        pom_paths = sorted(path for path in paths if self._is_pom(path))
        module_by_pom = {pom: self._module_for_pom(pom) for pom in pom_paths}
        pom_by_module = {module: pom for pom, module in module_by_pom.items()}
        known_modules = set(pom_by_module)

        parent_declarations: dict[str, list[tuple[str, str]]] = {}
        for pom_path in pom_paths:
            content = self.client.get_file_text(repo_full_name, pom_path, ref)
            if content is None:
                continue
            aggregator_module = module_by_pom[pom_path]
            for declaration in self._declared_modules(content):
                child_module = self._resolve_declared_module(
                    aggregator_module,
                    declaration,
                )
                if child_module is None or child_module not in known_modules:
                    continue
                parent_declarations.setdefault(child_module, []).append(
                    (aggregator_module, pom_path)
                )

        layouts: dict[str, MavenModuleLayout] = {}
        for module_path in sorted(known_modules):
            layout = self._layout_for_module(
                module_path,
                pom_by_module,
                parent_declarations,
            )
            if layout is not None:
                layouts[module_path] = layout
        return layouts

    @staticmethod
    def _is_pom(path: str) -> bool:
        return path == "pom.xml" or path.endswith("/pom.xml")

    @staticmethod
    def _module_for_pom(pom_path: str) -> str:
        if pom_path == "pom.xml":
            return ""
        return pom_path[: -len("/pom.xml")]

    @staticmethod
    def _pom_for_module(module_path: str) -> str:
        return "pom.xml" if module_path == "" else f"{module_path}/pom.xml"

    @classmethod
    def _declared_modules(cls, content: str) -> list[str]:
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return []

        declarations: list[str] = []
        for child in list(root):
            if cls._local_name(child.tag) != "modules":
                continue
            for module in list(child):
                if cls._local_name(module.tag) != "module" or module.text is None:
                    continue
                value = module.text.strip().replace("\\", "/")
                if value:
                    declarations.append(value)
        return declarations

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @staticmethod
    def _resolve_declared_module(
        aggregator_module: str,
        declaration: str,
    ) -> str | None:
        declaration_path = PurePosixPath(declaration)
        if declaration_path.is_absolute():
            return None

        parts = [] if aggregator_module == "" else aggregator_module.split("/")
        for part in declaration_path.parts:
            if part in ("", "."):
                continue
            if part == "..":
                if not parts:
                    return None
                parts.pop()
                continue
            parts.append(part)
        return "/".join(parts)

    def _layout_for_module(
        self,
        module_path: str,
        pom_by_module: dict[str, str],
        parent_declarations: dict[str, list[tuple[str, str]]],
    ) -> MavenModuleLayout | None:
        current = module_path
        visited = {current}
        evidence: list[str] = []

        while True:
            parents = parent_declarations.get(current, [])
            unique_parents = sorted(set(parents))
            if not unique_parents:
                break
            if len(unique_parents) != 1:
                # Multiple reactor parents are ambiguous; do not guess which build root
                # should own verification execution.
                return None

            parent_module, parent_pom = unique_parents[0]
            if parent_module in visited:
                return None
            visited.add(parent_module)
            evidence.append(parent_pom)
            current = parent_module

        build_root = current
        build_pom = pom_by_module.get(build_root, self._pom_for_module(build_root))

        if build_root == module_path:
            selector = None
            evidence_paths = (build_pom,)
        else:
            selector = self._relative_module(build_root, module_path)
            if selector is None:
                return None
            evidence_paths = tuple(dict.fromkeys(evidence))

        return MavenModuleLayout(
            module_path=module_path,
            build_root=build_root,
            build_pom=build_pom,
            module_selector=selector,
            evidence_paths=evidence_paths,
        )

    @staticmethod
    def _relative_module(build_root: str, module_path: str) -> str | None:
        if build_root == "":
            return module_path or "."
        prefix = build_root.rstrip("/") + "/"
        if not module_path.startswith(prefix):
            return None
        relative = module_path[len(prefix) :]
        return relative or "."
