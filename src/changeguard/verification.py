from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

from changeguard.models import (
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
) -> list[VerificationPlan]:
    """Create reviewable Maven test plans for endpoint-backed impact candidates.

    Service-level candidates are intentionally excluded. At that evidence level we do
    not yet know which concrete consumer endpoint use should be verified.
    """
    plans: list[VerificationPlan] = []

    for candidate in candidates:
        if candidate.match_level != ImpactMatchLevel.ENDPOINT:
            continue

        module = graph.module_for_service(candidate.consumer_service)
        if module is None:
            continue

        endpoint = candidate.before or candidate.after
        plans.append(
            VerificationPlan(
                provider_service=candidate.provider_service,
                consumer_service=candidate.consumer_service,
                consumer_module=module,
                changed_file=candidate.changed_file,
                trigger_kind=candidate.trigger_kind,
                endpoint=endpoint,
                command=["mvn", "-pl", module, "-am", "test"],
                reason=(
                    "Run the consumer module's existing Maven tests because an explicit "
                    "consumer HTTP call matched the compatibility-sensitive provider endpoint."
                ),
            )
        )

    return sorted(
        plans,
        key=lambda plan: (
            plan.consumer_service,
            plan.provider_service,
            plan.changed_file,
            plan.trigger_kind.value,
            plan.endpoint.path if plan.endpoint is not None else "",
        ),
    )


def execute_verification_plan(
    plan: VerificationPlan,
    repo_path: Path | str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> VerificationResult:
    """Execute a previously reviewed plan in an explicit local repository workspace."""
    workspace = Path(repo_path).expanduser().resolve()

    validation_error = _validate_workspace(workspace, plan.consumer_module)
    if validation_error is not None:
        return VerificationResult(
            plan=plan,
            status=VerificationStatus.ERROR,
            error=validation_error,
        )

    started = time.perf_counter()
    try:
        completed = runner(
            plan.command,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        return VerificationResult(
            plan=plan,
            status=VerificationStatus.ERROR,
            duration_seconds=time.perf_counter() - started,
            error=(
                f"Could not execute '{plan.command[0]}'. Install Maven or make the "
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
        trigger_kind="ENDPOINT_REMOVED",
        command=["mvn", "-pl", consumer_module, "-am", "test"],
        reason="Explicit local Maven module verification requested by the user.",
    )


def _validate_workspace(workspace: Path, consumer_module: str) -> str | None:
    if not workspace.exists() or not workspace.is_dir():
        return f"Verification workspace does not exist or is not a directory: {workspace}"

    if not (workspace / "pom.xml").is_file():
        return f"Verification workspace does not contain a root pom.xml: {workspace}"

    module_path = workspace / consumer_module
    if not module_path.is_dir():
        return f"Consumer module does not exist in workspace: {consumer_module}"

    if not (module_path / "pom.xml").is_file():
        return f"Consumer module does not contain pom.xml: {consumer_module}"

    return None


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
