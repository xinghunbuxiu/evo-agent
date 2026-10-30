"""Deterministic, read-only verification of Mission workspace artifacts.

Only declarative checks are accepted. This module never executes worker-provided
commands or code, and every artifact path is confined to the workspace.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


VERIFIER_ID = "evo.workspace-artifact-verifier"
VERIFIER_VERSION = "1.0.0"
SCHEMA_VERSION = "mission.verification.v1"
SUPPORTED_CHECK_TYPES = {"file_exists", "file_contains", "json_value_equals"}


def normalize_verification_contract(value: Any) -> dict[str, Any]:
    """Validate and return the small, deterministic Mission verification DSL."""
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("verification contract schema_version is unsupported")
    checks = value.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("verification contract requires at least one check")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(checks):
        if not isinstance(raw, dict):
            raise ValueError(f"verification check {index} must be an object")
        check_id = str(raw.get("check_id") or "").strip()
        check_type = str(raw.get("type") or "").strip()
        relative_path = str(raw.get("path") or "").strip()
        if not check_id or check_id in seen_ids:
            raise ValueError(f"verification check {index} has a missing or duplicate check_id")
        if check_type not in SUPPORTED_CHECK_TYPES:
            raise ValueError(f"verification check {check_id!r} uses an unsupported type")
        if not relative_path or Path(relative_path).is_absolute():
            raise ValueError(f"verification check {check_id!r} requires a relative path")
        if any(part in {"", ".", ".."} for part in Path(relative_path).parts):
            raise ValueError(f"verification check {check_id!r} has an unsafe path")
        item: dict[str, Any] = {
            "check_id": check_id,
            "type": check_type,
            "path": relative_path,
        }
        if check_type == "file_contains":
            expected = raw.get("expected")
            if not isinstance(expected, str) or not expected:
                raise ValueError(f"verification check {check_id!r} requires non-empty expected text")
            item["expected"] = expected
        elif check_type == "json_value_equals":
            key_path = raw.get("key_path")
            if not isinstance(key_path, list) or not key_path or any(
                not isinstance(part, (str, int)) or isinstance(part, bool) for part in key_path
            ):
                raise ValueError(f"verification check {check_id!r} requires a non-empty key_path")
            if "expected" not in raw:
                raise ValueError(f"verification check {check_id!r} requires expected value")
            item["key_path"] = list(key_path)
            item["expected"] = raw["expected"]
        seen_ids.add(check_id)
        normalized.append(item)
    return {"schema_version": SCHEMA_VERSION, "checks": normalized}


def _workspace_file(workspace: Path, relative_path: str) -> Path:
    root = Path(workspace).resolve()
    candidate = (root / relative_path).resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("artifact path escapes workspace") from exc
    if not candidate.is_file():
        raise ValueError("artifact is not a regular file")
    return candidate


def _read_json_path(value: Any, key_path: list[str | int]) -> Any:
    current = value
    for part in key_path:
        if isinstance(part, int):
            if not isinstance(current, list) or part < 0 or part >= len(current):
                raise KeyError("JSON array index not found")
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                raise KeyError("JSON object key not found")
            current = current[part]
    return current


def verify_workspace_artifacts(
    *, workspace, tenant_id: str, mission_run: dict, action: dict, task
) -> dict[str, Any] | None:
    """Independently inspect declared files and return check-level evidence.

    The verifier reads only files inside the configured workspace. It does not trust
    task.result, worker-reported booleans, arbitrary paths, or executable commands.
    """
    if not isinstance(action, dict):
        return None
    try:
        contract = normalize_verification_contract(action.get("verification_contract"))
    except (TypeError, ValueError):
        return None

    results: list[dict[str, Any]] = []
    for check in contract["checks"]:
        passed = False
        try:
            artifact = _workspace_file(Path(workspace), check["path"])
            if check["type"] == "file_exists":
                passed = True
            elif check["type"] == "file_contains":
                passed = check["expected"] in artifact.read_text(encoding="utf-8")
            elif check["type"] == "json_value_equals":
                payload = json.loads(artifact.read_text(encoding="utf-8"))
                actual = _read_json_path(payload, check["key_path"])
                passed = actual == check["expected"]
        except (OSError, UnicodeError, ValueError, KeyError, IndexError, json.JSONDecodeError):
            passed = False
        results.append({"check_id": check["check_id"], "passed": bool(passed)})

    return {
        "verifier_id": VERIFIER_ID,
        "verifier_version": VERIFIER_VERSION,
        "checks": results,
    }
