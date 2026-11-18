"""Fail-closed verification binding for Talent Center Learning Tasks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from core.verification import verify_verification_evidence


def validate_learning_task_attestation(
    workspace: Path,
    tenant_id: str,
    task: dict,
    attestation: Any,
) -> dict:
    """Validate a signed independent verifier result against one submitted task."""
    if not isinstance(task, dict):
        raise ValueError("learning task is required")
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    if metadata.get("source") != "talent_center_worker_growth_adoption":
        raise ValueError("task is not an adopted Worker Growth Learning Task")
    if str(task.get("status") or "").strip() != "submitted":
        raise ValueError("Learning Task must be submitted before verification")
    if not isinstance(attestation, dict):
        raise ValueError("signed independent verification attestation is required")
    if not verify_verification_evidence(Path(workspace), str(tenant_id), attestation):
        raise ValueError("independent verification signature is invalid")

    expected = {
        "source": "learning_task_independent_verifier",
        "tenant_id": str(tenant_id),
        "learning_task_id": str(task.get("task_id") or "").strip(),
        "member_id": str(task.get("member_id") or "").strip(),
        "worker_id": str(metadata.get("executing_worker_id") or "").strip(),
        "execution_event_id": str(metadata.get("execution_event_id") or "").strip(),
    }
    for key, value in expected.items():
        if not value or attestation.get(key) != value:
            raise ValueError(f"independent verification {key} binding mismatch")
    if not str(attestation.get("verifier_id") or "").strip():
        raise ValueError("independent verifier identity is required")
    if not str(attestation.get("verifier_version") or "").strip():
        raise ValueError("independent verifier version is required")
    status = str(attestation.get("status") or "").strip()
    if status not in {"passed", "failed"}:
        raise ValueError("independent verification status must be passed or failed")
    checks = attestation.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("independent verification must include checks")
    normalized_checks = []
    for check in checks:
        if not isinstance(check, dict) or not str(check.get("check_id") or "").strip():
            raise ValueError("independent verification check is malformed")
        if not isinstance(check.get("passed"), bool):
            raise ValueError("independent verification check requires a boolean result")
        normalized_checks.append(check)
    checks_passed = all(item["passed"] for item in normalized_checks)
    if (status == "passed") != checks_passed:
        raise ValueError("independent verification verdict does not match its checks")
    digest = hashlib.sha256(json.dumps(
        attestation, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return {
        "status": status,
        "attestation": attestation,
        "sha256": digest,
        "verifier_id": str(attestation["verifier_id"]).strip(),
        "verified_at": str(attestation.get("verified_at") or "").strip() or None,
    }


def attach_learning_task_attestation(
    workspace: Path,
    tenant_id: str,
    task: dict,
    attestation: Any,
) -> dict:
    """Attach only a signed verifier attestation bound to the submitted task."""
    validated = validate_learning_task_attestation(workspace, tenant_id, task, attestation)
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    task["metadata"] = {
        **metadata,
        "independent_verification": validated,
    }
    return validated


def require_passed_learning_task_attestation(
    workspace: Path,
    tenant_id: str,
    task: dict,
) -> dict:
    metadata = task.get("metadata") if isinstance(task, dict) and isinstance(task.get("metadata"), dict) else {}
    stored = metadata.get("independent_verification")
    if not isinstance(stored, dict) or not isinstance(stored.get("attestation"), dict):
        raise ValueError("independent verification evidence is missing")
    validated = validate_learning_task_attestation(
        workspace, tenant_id, task, stored["attestation"],
    )
    if stored.get("sha256") != validated["sha256"] or stored.get("status") != validated["status"]:
        raise ValueError("stored independent verification evidence integrity mismatch")
    if validated["status"] != "passed":
        raise ValueError("independent verification did not pass")
    return validated
