"""Fail-closed boundary for isolated execution profile adapters.

This module deliberately ships no local subprocess fallback. Deployments must
inject a trusted adapter backed by an independently enforced OS/container
sandbox. The interface and result envelope do not themselves provide isolation
or authenticate the adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .execution_profiles import ExecutionProfileSpec, resolve_execution_profile
from .execution_results import build_execution_result


class SandboxRunnerUnavailable(RuntimeError):
    """Raised when an execution request has no configured isolated runner."""


@dataclass(frozen=True)
class RunnerProcessOutput:
    """Raw process observations returned by a trusted runner adapter."""

    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False


class SandboxRunnerAdapter(Protocol):
    """Deployment-provided adapter that must enforce isolation outside this app."""

    runner_id: str
    runner_version: str

    def execute(self, spec: ExecutionProfileSpec) -> RunnerProcessOutput:
        """Execute the fixed spec in an independently enforced sandbox."""


def execute_with_sandbox(
    workspace: Path,
    request: object,
    *,
    runner: SandboxRunnerAdapter | None = None,
) -> dict:
    """Resolve and execute a profile only through an explicitly injected runner.

    No adapter means no execution. In particular, this function never falls
    back to subprocess, TaskQueue handlers, shell commands, or in-process code.
    The returned envelope is normalized, not authenticated or signed.
    """
    spec = resolve_execution_profile(workspace, request)
    if runner is None:
        raise SandboxRunnerUnavailable(
            "no isolated sandbox runner is configured; refusing in-process execution"
        )

    execute = getattr(runner, "execute", None)
    runner_id = getattr(runner, "runner_id", None)
    runner_version = getattr(runner, "runner_version", None)
    if not callable(execute) or not runner_id or not runner_version:
        raise SandboxRunnerUnavailable("configured sandbox runner adapter is incomplete")

    output = execute(spec)
    if not isinstance(output, RunnerProcessOutput):
        raise TypeError("sandbox runner must return RunnerProcessOutput")

    return build_execution_result(
        spec,
        runner_id=runner_id,
        runner_version=runner_version,
        exit_code=output.exit_code,
        stdout=output.stdout,
        stderr=output.stderr,
        timed_out=output.timed_out,
    )


__all__ = [
    "RunnerProcessOutput",
    "SandboxRunnerAdapter",
    "SandboxRunnerUnavailable",
    "execute_with_sandbox",
]
