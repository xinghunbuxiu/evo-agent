"""
M1 进化闭环探测：不经过 HTTP / create_app，直接操作 autonomy runtime。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from admin.formal_task_evolution_runtime import apply_approved_task_evolution
from admin.runtime_state import (
    create_employee_member_runtime,
    load_autonomy_runtime,
    normalize_child_members_runtime,
    save_autonomy_runtime,
)
from admin.task_center_runtime import upsert_task


def run_evolution_closure_probe(workspace: Path, *, tenant_id: str = "default") -> dict:
    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
    runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
    child_members = normalize_child_members_runtime(
        runtime.get("child_members"),
        legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
    )
    employee = create_employee_member_runtime(
        tenant_id=normalized_tenant_id,
        name="M1 Evolution Probe",
        role_label="M1 Evolution Probe",
        role_key="m1_evolution_probe",
        self_description="m1 evolution probe",
        long_term_goal="m1 evolution probe",
    )
    member_id = str(employee.get("member_id") or "").strip()
    items = child_members.get("items") if isinstance(child_members.get("items"), list) else []
    items.append(employee)
    child_members["items"] = items
    runtime["child_members"] = child_members

    task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
    now_iso = datetime.now().isoformat()
    task_id = f"task:{member_id}:{int(datetime.now().timestamp() * 1000)}"
    task = upsert_task(task_center, {
        "task_id": task_id,
        "member_id": member_id,
        "assigned_by_member_id": "talent_development_officer",
        "title": "M1 进化探测任务",
        "objective": "验证任务确认后系统能否自动生成下一轮建议",
        "deliverables": ["提交结果", "提交复盘"],
        "status": "assigned",
        "assigned_at": now_iso,
        "started_at": None,
        "submitted_at": None,
        "approved_at": None,
        "result_summary": None,
        "reflection": None,
        "review_note": None,
        "metadata": {"source": "m1_evolution_probe"},
    })
    runtime["task_center"] = task_center
    save_autonomy_runtime(workspace, runtime, normalized_tenant_id)

    task["status"] = "submitted"
    task["started_at"] = now_iso
    task["submitted_at"] = now_iso
    task["result_summary"] = "已完成 M1 进化探测交付"
    task["reflection"] = "验证 assign→submit→approve 闭环"
    save_autonomy_runtime(workspace, runtime, normalized_tenant_id)

    task["status"] = "approved"
    task["approved_at"] = datetime.now().isoformat()
    task["review_note"] = "M1 进化探测确认"
    runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
    runtime, evolution_summary = apply_approved_task_evolution(
        workspace=workspace,
        runtime=runtime,
        tenant_id=normalized_tenant_id,
        member_id=member_id,
        task=task,
        include_training_review=False,
    )
    save_autonomy_runtime(workspace, runtime, normalized_tenant_id)

    runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
    recommendations = (
        runtime.get("task_center", {}).get("recommendations", [])
        if isinstance(runtime.get("task_center"), dict)
        else []
    )
    probe_recs = [
        item for item in recommendations
        if isinstance(item, dict)
        and str(item.get("member_id") or "").strip() == member_id
        and str(item.get("status") or "").strip() == "suggested"
    ]
    return {
        "member_id": member_id,
        "task_id": task_id,
        "evolution_summary": evolution_summary,
        "recommendation_count": len(probe_recs),
        "next_task_title": probe_recs[0].get("title") if probe_recs else evolution_summary.get("next_task_title"),
    }
