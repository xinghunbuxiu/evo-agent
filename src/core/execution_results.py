"""Normalize trusted runner output into a bounded, auditable execution record.

This module does not launch processes, authenticate a runner, or sign evidence.
Only a trusted sandbox adapter may call it with the adapter's observed process result.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .execution_profiles import ExecutionProfileSpec


EXECUTION_RESULT_SCHEMA = "mission.execution-result.v1"


def _required_label(value: Any, field: str) -> str:
    label = str(value or "").strip()
    if not label or len(label) > 128:
        raise ValueError(f"{field} must be a non-empty string of at most 128 characters")
    return label


def build_execution_result(
    spec: ExecutionProfileSpec,
    *,
    runner_id: str,
    runner_version: str,
    exit_code: int | None,
    stdout: bytes,
    stderr: bytes,
    timed_out: bool = False,
) -> dict[str, Any]:
    """Build a digest-only record from output captured by a trusted runner adapter."""
    runner_id = _required_label(runner_id, "runner_id")
    runner_version = _required_label(runner_version, "runner_version")
    if not isinstance(timed_out, bool):
        raise ValueError("timed_out must be a boolean")
    if exit_code is not None and (
        isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code < 0
    ):
        raise ValueError("exit_code must be a non-negative integer or null")
    if timed_out and exit_code is not None:
        raise ValueError("timed-out executions must not claim a final exit_code")
    if not timed_out and exit_code is None:
        raise ValueError("completed executions require an exit_code")
    if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
        raise ValueError("stdout and stderr must be captured as bytes")
    output_size = len(stdout) + len(stderr)
    if output_size > spec.max_output_bytes:
        raise ValueError("captured process output exceeds the configured output limit")

    return {
        "schema_version": EXECUTION_RESULT_SCHEMA,
        "runner": {"id": runner_id, "version": runner_version},
        "profile_id": spec.profile_id,
        "target": spec.target,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "execution_succeeded": not timed_out and exit_code == 0,
        "stdout": {"bytes": len(stdout), "sha256": hashlib.sha256(stdout).hexdigest()},
        "stderr": {"bytes": len(stderr), "sha256": hashlib.sha256(stderr).hexdigest()},
    }


__all__ = ["EXECUTION_RESULT_SCHEMA", "build_execution_result"]
