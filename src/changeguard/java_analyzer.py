from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from changeguard.models import EndpointSemanticChange, SecuritySemanticChange


class JavaAnalyzerError(RuntimeError):
    pass


@dataclass(frozen=True)
class JavaSemanticAnalysis:
    endpoint_changes: list[EndpointSemanticChange]
    security_changes: list[SecuritySemanticChange]


class JavaSpringAnalyzer:
    """Bridge from the Python orchestration layer to the JVM semantic analyzer."""

    def __init__(
        self,
        jar_path: Path | str | None = None,
        java_command: str = "java",
    ) -> None:
        self.jar_path = Path(jar_path) if jar_path else self.default_jar_path()
        self.java_command = java_command

    @staticmethod
    def default_jar_path() -> Path:
        configured = os.getenv("CHANGEGUARD_JAVA_ANALYZER_JAR")
        if configured:
            return Path(configured).expanduser().resolve()

        repo_root = Path(__file__).resolve().parents[2]
        return (
            repo_root
            / "analyzers"
            / "java-spring"
            / "target"
            / "changeguard-java-analyzer.jar"
        )

    def is_available(self) -> bool:
        return self.jar_path.is_file()

    def analyze_sources(
        self,
        before_source: str,
        after_source: str,
    ) -> JavaSemanticAnalysis:
        if not self.is_available():
            raise JavaAnalyzerError(
                "Java semantic analyzer JAR was not found at "
                f"{self.jar_path}. Build it with: "
                "mvn -f analyzers/java-spring/pom.xml package"
            )

        with tempfile.TemporaryDirectory(prefix="changeguard-java-") as temp_dir:
            temp_path = Path(temp_dir)
            before_path = temp_path / "before.java"
            after_path = temp_path / "after.java"
            before_path.write_text(before_source, encoding="utf-8")
            after_path.write_text(after_source, encoding="utf-8")

            command = [
                self.java_command,
                "-jar",
                str(self.jar_path),
                "--before",
                str(before_path),
                "--after",
                str(after_path),
            ]

            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise JavaAnalyzerError(
                    f"Could not execute '{self.java_command}'. "
                    "Install Java 17+ or configure the Java executable on PATH."
                ) from exc

        if completed.returncode != 0:
            stderr = completed.stderr.strip() or "unknown JVM analyzer error"
            raise JavaAnalyzerError(
                f"Java semantic analyzer failed with exit code "
                f"{completed.returncode}: {stderr}"
            )

        return parse_analysis_result(completed.stdout)


def _parse_payload(output: str) -> dict:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise JavaAnalyzerError(
            "Java semantic analyzer returned invalid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise JavaAnalyzerError("Java semantic analyzer response was not a JSON object")
    return payload


def parse_analysis_result(output: str) -> JavaSemanticAnalysis:
    payload = _parse_payload(output)

    endpoint_changes = payload.get("changes")
    if not isinstance(endpoint_changes, list):
        raise JavaAnalyzerError(
            "Java semantic analyzer response did not contain a changes list"
        )

    security_changes = payload.get("securityChanges", [])
    if not isinstance(security_changes, list):
        raise JavaAnalyzerError(
            "Java semantic analyzer response did not contain a valid securityChanges list"
        )

    return JavaSemanticAnalysis(
        endpoint_changes=[
            EndpointSemanticChange.model_validate(change)
            for change in endpoint_changes
        ],
        security_changes=[
            SecuritySemanticChange.model_validate(change)
            for change in security_changes
        ],
    )


def parse_semantic_changes(output: str) -> list[EndpointSemanticChange]:
    """Backward-compatible helper for endpoint-only callers/tests."""
    return parse_analysis_result(output).endpoint_changes


def parse_security_changes(output: str) -> list[SecuritySemanticChange]:
    return parse_analysis_result(output).security_changes
