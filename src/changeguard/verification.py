from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from changeguard.maven_layout import MavenModuleLayout
from changeguard.models import (
    EndpointChangeKind,
    ImpactCandidate,
    ImpactMatchLevel,
    ServiceDependencyGraph,
    VerificationPlan,
    VerificationResult,
    VerificationStatus,
)


OUTPUT_TAIL_CHARS = 6000
DEFAULT_TIMEOUT_SECONDS = 300


def build_verification_plans(
    candidates: list[ImpactCandidate],
    graph: ServiceDependencyGraph,
    module_layout: dict[str, MavenModuleLayout] | None = None,
) -> list[VerificationPlan]:
    """Create reviewable Maven test plans for endpoint-backed impact candidates.

    Service-level candidates are intentionally excluded. At that evidence level we do
    not yet know which concrete consumer endpoint use should be verified.

    When exact Maven reactor evidence is available, plans include `-f <build-pom>` and
    a module selector relative to that reactor root. This makes nested-monorepo plans
    executable from the repository root instead of assuming the repository root itself
    contains the relevant Maven aggregator.
    """
    plans: list[VerificationPlan] = []
    layout_by_module = module_layout or {}

    for candidate in candidates:
        if candidate.match_level != ImpactMatchLevel.ENDPOINT:
            continue

        module = candidate.consumer_module or graph.module_for_service(
            candidate.consumer_service
        )
        if module is None:
            continue

        layout = layout_by_module.get(module)
        command = _maven_command(module, layout)
        endpoint = candidate.before or candidate.after
        reason = (
            "Run the consumer module's existing Maven tests because an explicit "
            "consumer HTTP call matched the compatibility-sensitive provider endpoint."
        )
        if layout is not None:
            evidence = ", ".join(layout.evidence_paths)
            reason += (
                f" Maven build root is derived from explicit reactor evidence: {evidence}."
            )

        plans.append(
            VerificationPlan(
                provider_service=candidate.provider_service,
                consumer_service=candidate.consumer_service,
                consumer_module=module,
                changed_file=candidate.changed_file,
                trigger_kind=candidate.trigger_kind,
                endpoint=endpoint,
                command=command,
                reason=reason,
            )
        )

    return sorted(
        plans,
        key=lambda plan: (
            plan.consumer_module,
            plan.consumer_service,
            plan.provider_service,
            plan.changed_file,
            plan.trigger_kind.value,
            plan.endpoint.path if plan.endpoint is not None else "",
        ),
    )


def _maven_command(
    module: str,
    layout: MavenModuleLayout | None,
) -> list[str]:
    if layout is None:
        return ["mvn", "-pl", module, "-am", "test"]

    command = ["mvn", "-f", layout.build_pom]
    if layout.module_selector is not None:
        command.extend(["-pl", layout.module_selector, "-am"])
    command.append("test")
    return command


def execute_verification_plan(
    plan: VerificationPlan,
    repo_path: Path | str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> VerificationResult:
    """Execute a previously reviewed plan in an explicit local repository workspace."""
    workspace = Path(repo_path).expanduser().resolve()

    validation_error = _validate_workspace(workspace, plan)
    if validation_error is not None:
        return VerificationResult(
            plan=plan,
            status=VerificationStatus.ERROR,
            error=validation_error,
        )

    process_command = plan.command
    if runner is subprocess.run:
        resolved_command = _resolve_process_command(plan.command)
        if resolved_command is None:
            return VerificationResult(
                plan=plan,
                status=VerificationStatus.ERROR,
                error=(
                    f"Could not resolve '{plan.command[0]}' to an executable launcher. "
                    "Install Maven or make mvn/mvn.cmd available on PATH."
                ),
            )
        process_command = resolved_command

    started = time.perf_counter()
    try:
        completed = runner(
            process_command,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return VerificationResult(
            plan=plan,
            status=VerificationStatus.ERROR,
            duration_seconds=time.perf_counter() - started,
            error=(
                f"Could not execute '{process_command[0]}'. Install Maven or make the "
                "configured executable available on PATH."
            ),
        )
    except subprocess.TimeoutExpired as exc:
        return VerificationResult(
            plan=plan,
            status=VerificationStatus.ERROR,
            duration_seconds=time.perf_counter() - started,
            stdout_tail=_tail(_coerce_output(exc.stdout)),
            stderr_tail=_tail(_coerce_output(exc.stderr)),
            error=f"Verification command exceeded the {timeout_seconds}s timeout.",
        )
    except OSError as exc:
        return VerificationResult(
            plan=plan,
            status=VerificationStatus.ERROR,
            duration_seconds=time.perf_counter() - started,
            error=f"Could not execute verification command: {exc}",
        )

    duration = time.perf_counter() - started
    status = (
        VerificationStatus.PASSED
        if completed.returncode == 0
        else VerificationStatus.FAILED
    )
    return VerificationResult(
        plan=plan,
        status=status,
        exit_code=completed.returncode,
        duration_seconds=duration,
        stdout_tail=_tail(completed.stdout or ""),
        stderr_tail=_tail(completed.stderr or ""),
    )


def create_maven_module_plan(
    consumer_service: str,
    consumer_module: str,
) -> VerificationPlan:
    """Create an explicit local-only module verification plan for CLI execution."""
    return VerificationPlan(
        provider_service="manual",
        consumer_service=consumer_service,
        consumer_module=consumer_module,
        changed_file="manual",
        trigger_kind=EndpointChangeKind.ENDPOINT_REMOVED,
        command=["mvn", "-pl", consumer_module, "-am", "test"],
        reason="Explicit local Maven module verification requested by the user.",
    )


def _resolve_process_command(
    command: list[str],
    *,
    platform_name: str | None = None,
    resolver: Callable[[str], str | None] = shutil.which,
) -> list[str] | None:
    """Resolve a portable command name to the concrete process launcher.

    PowerShell can resolve `mvn` to Maven's `mvn.cmd`, while Python's direct process
    creation may not resolve the same batch launcher from the extensionless name.
    Keep plans portable as `mvn ...`, then resolve the concrete launcher only when
    execution is explicitly requested.
    """
    if not command:
        return None

    executable = command[0]
    candidates = [executable]
    current_platform = platform_name or os.name
    if current_platform == "nt" and Path(executable).suffix == "":
        candidates.extend([f"{executable}.cmd", f"{executable}.bat", f"{executable}.exe"])

    for candidate in candidates:
        resolved = resolver(candidate)
        if resolved is not None:
            return [resolved, *command[1:]]

    return None


def _validate_workspace(workspace: Path, plan: VerificationPlan) -> str | None:
    if not workspace.exists() or not workspace.is_dir():
        return f"Verification workspace does not exist or is not a directory: {workspace}"

    build_pom = _build_pom_from_command(plan.command)
    if build_pom is None:
        root_pom = workspace / "pom.xml"
        if not root_pom.is_file():
            return f"Verification workspace does not contain a root pom.xml: {workspace}"
    else:
        build_pom_path = (workspace / build_pom).resolve()
        try:
            build_pom_path.relative_to(workspace)
        except ValueError:
            return f"Maven build POM must remain inside the verification workspace: {build_pom}"
        if not build_pom_path.is_file():
            return f"Maven build POM does not exist in workspace: {build_pom}"

    module_path = (workspace / plan.consumer_module).resolve()
    try:
        module_path.relative_to(workspace)
    except ValueError:
        return (
            "Consumer module must remain inside the verification workspace: "
            f"{plan.consumer_module}"
        )

    if not module_path.is_dir():
        return f"Consumer module does not exist in workspace: {plan.consumer_module}"

    if not (module_path / "pom.xml").is_file():
        return f"Consumer module does not contain pom.xml: {plan.consumer_module}"

    return None


def _build_pom_from_command(command: list[str]) -> str | None:
    try:
        index = command.index("-f")
    except ValueError:
        return None
    if index + 1 >= len(command):
        return None
    return command[index + 1]


def _tail(value: str) -> str:
    if len(value) <= OUTPUT_TAIL_CHARS:
        return value
    return value[-OUTPUT_TAIL_CHARS:]


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
