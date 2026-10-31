"""Allowlisted execution-profile contracts for trusted sandbox adapters.

This module resolves declarative requests into fixed argv specifications. It does
not execute processes and is not itself a sandbox: callers must run the returned
specification inside an OS/container isolation boundary before trusting its output.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 300
MAX_OUTPUT_BYTES = 256 * 1024
_PROFILE_FIELDS = {"profile_id", "target", "timeout_seconds"}
_MODULE_RE = re.compile(r"^[A-Za-z_]\\w*(?:\\.[A-Za-z_]\\w*)*$")


@dataclass(frozen=True)
class ExecutionProfileSpec:
    profile_id: str
    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: int
    max_output_bytes: int
    network_access: bool = False


def _workspace_target(workspace: Path, raw_target: Any) -> Path:
    target = str(raw_target or "").strip()
    if (
        not target
        or Path(target).is_absolute()
        or PureWindowsPath(target).is_absolute()
        or PureWindowsPath(target).drive
        or "\\\\" in target
        or "\\x00" in target
        or any(part in {"", ".", ".."} for part in Path(target).parts)
    ):
        raise ValueError("execution target must be a portable workspace-relative path")
    root = Path(workspace).resolve(strict=True)
    resolved = (root / target).resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("execution target escapes workspace") from exc
    if not resolved.is_file():
        raise ValueError("execution target must be a regular file")
    return resolved


def resolve_execution_profile(workspace: Path, request: Any) -> ExecutionProfileSpec:
    """Resolve a strict profile request; worker-supplied commands/args are rejected."""
    if not isinstance(request, dict):
        raise ValueError("execution profile request must be an object")
    unknown = set(request) - _PROFILE_FIELDS
    missing = {"profile_id", "target"} - set(request)
    if unknown:
        raise ValueError(f"unsupported execution request fields: {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"missing execution request fields: {', '.join(sorted(missing))}")

    profile_id = str(request.get("profile_id") or "").strip()
    timeout = request.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if isinstance(timeout, bool) or not isinstance(timeout, int):
        raise ValueError("timeout_seconds must be an integer")
    if timeout < 1 or timeout > MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")

    if profile_id == "python.unittest":
        target = str(request.get("target") or "").strip()
        if not _MODULE_RE.fullmatch(target):
            raise ValueError("python.unittest target must be a dotted Python module name")
        argv = (sys.executable, "-m", "unittest", target)
    elif profile_id == "python.pytest":
        target_path = _workspace_target(Path(workspace), request.get("target"))
        argv = (sys.executable, "-m", "pytest", str(target_path))
    else:
        raise ValueError("unsupported execution profile")

    return ExecutionProfileSpec(
        profile_id=profile_id,
        argv=argv,
        cwd=Path(workspace).resolve(strict=True),
        timeout_seconds=timeout,
        max_output_bytes=MAX_OUTPUT_BYTES,
        network_access=False,
    )


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_TIMEOUT_SECONDS",
    "MAX_OUTPUT_BYTES",
    "ExecutionProfileSpec",
    "resolve_execution_profile",
]
