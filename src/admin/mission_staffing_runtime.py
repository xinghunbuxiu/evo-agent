"""Mission staffing contracts owned by the Talent Center.

Mission may describe the personnel it needs, but only a validated Talent Center
assignment can authorize an employee/Worker pairing for a Mission node.
"""
from __future__ import annotations

from typing import Any


def resolve_selected_employee(*, members: list[dict[str, Any]], selected_member_id: str) -> dict[str, Any] | None:
    """Resolve only an explicit, unique, active employee selection."""
    selected_id = str(selected_member_id or "").strip()
    if not selected_id:
        return None
    matches = [
        item for item in members
        if isinstance(item, dict) and str(item.get("member_id") or "").strip() == selected_id
    ]
    if len(matches) != 1:
        return None
    member = matches[0]
    if str(member.get("status") or "active").strip() != "active":
        return None
    if str(member.get("primary_role") or "").strip() == "talent_development":
        return None
    return member


def build_staffing_request(
    *,
    tenant_id: str,
    mission_run_id: str,
    node: dict[str, Any],
    workforce_decision: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic, non-authorizing staffing request for one node."""
    tenant = str(tenant_id or "").strip()
    run_id = str(mission_run_id or "").strip()
    node_id = str(node.get("id") or "").strip() if isinstance(node, dict) else ""
    if not tenant or not run_id or not node_id:
        raise ValueError("tenant, mission run, and node identity are required")
    decision = workforce_decision if isinstance(workforce_decision, dict) else {}
    capabilities = decision.get("required_capabilities")
    capabilities = sorted({
        str(value).strip().casefold()
        for value in capabilities
        if str(value).strip()
    }) if isinstance(capabilities, list) else []
    return {
        "schema_version": "talent.staffing_request.v1",
        "request_id": f"{run_id}:{node_id}",
        "tenant_id": tenant,
        "mission_run_id": run_id,
        "node_id": node_id,
        "role_id": str(decision.get("recommended_role_id") or "").strip() or None,
        "required_capabilities": capabilities,
        "task_type": str(node.get("task_type") or "").strip() or None,
        "risk_level": str(node.get("risk_level") or decision.get("risk_level") or "standard").strip(),
        "status": "pending",
        "decision_owner": "mission",
        "dispatch_authorized": False,
    }


def validate_staffing_assignment(
    *,
    assignment: Any,
    request: dict[str, Any],
    worker: Any,
    expected_handler_id: str,
) -> tuple[bool, str]:
    """Validate a Talent Center approval against the exact request and Worker."""
    if not isinstance(assignment, dict):
        return False, "staffing_assignment_missing"
    if assignment.get("schema_version") != "talent.staffing_assignment.v1":
        return False, "staffing_assignment_schema_invalid"
    if assignment.get("decision_owner") != "talent_center" or assignment.get("status") != "approved":
        return False, "staffing_assignment_not_approved"
    for field in ("tenant_id", "mission_run_id", "node_id", "request_id"):
        if str(assignment.get(field) or "").strip() != str(request.get(field) or "").strip():
            return False, f"staffing_assignment_{field}_mismatch"
    member_id = str(assignment.get("employee_member_id") or "").strip()
    worker_id = str(assignment.get("worker_id") or "").strip()
    if not member_id or not worker_id:
        return False, "staffing_assignment_identity_missing"
    if not isinstance(worker, dict) or str(worker.get("worker_id") or "").strip() != worker_id:
        return False, "staffing_assignment_worker_mismatch"
    if str(worker.get("owner_tenant_id") or "").strip() != str(request.get("tenant_id") or "").strip():
        return False, "staffing_assignment_worker_tenant_mismatch"
    if str(worker.get("owner_member_id") or "").strip() != member_id:
        return False, "staffing_assignment_worker_employee_mismatch"
    if worker.get("status") != "available" or worker.get("active_task_ids"):
        return False, "staffing_assignment_worker_unavailable"
    profile = worker.get("profile") if isinstance(worker.get("profile"), dict) else {}
    if str(profile.get("handler_id") or "").strip() != str(expected_handler_id or "").strip():
        return False, "staffing_assignment_handler_mismatch"
    return True, "staffing_assignment_validated"


__all__ = ["resolve_selected_employee", "build_staffing_request", "validate_staffing_assignment"]
