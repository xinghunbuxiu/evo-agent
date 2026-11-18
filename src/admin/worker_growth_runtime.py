"""Talent Center worker-growth loop.

Turns a terminal Mission outcome into a concrete training recommendation for
the assigned employee/Worker. It does not execute the training itself; the
Talent Center owns assignment, while Mission owns decomposition/execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def build_worker_growth_recommendation(
    *,
    employee: dict[str, Any],
    mission_run: dict[str, Any],
    node: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """Create a deterministic Talent Center recommendation from one outcome."""
    employee_id = _text(employee.get("member_id"), 120)
    worker_id = _text(employee.get("worker_id") or employee.get("primary_worker_id"), 120)
    mission_run_id = _text(mission_run.get("mission_run_id"), 120)
    node_id = _text(node.get("id"), 120)
    status = _text(outcome.get("status"), 40).lower()
    if not employee_id or not mission_run_id or not node_id:
        raise ValueError("worker growth lineage is incomplete")
    if status not in {"success", "completed", "failed", "cancelled"}:
        raise ValueError("worker growth requires a terminal outcome")

    failure_reasons = outcome.get("failure_reasons")
    if not isinstance(failure_reasons, list):
        failure_reasons = []
    failure_reasons = [_text(item, 300) for item in failure_reasons if _text(item, 300)]

    verified = outcome.get("independent_verification")
    verified_status = _text(verified.get("status") if isinstance(verified, dict) else "", 40).lower()
    success = status in {"success", "completed"} and verified_status in {"passed", "verified"}

    role = _text(
        employee.get("primary_role")
        or (employee.get("persona") or {}).get("role_label"),
        120,
    ) or "worker"

    if success:
        objective = f"复盘节点 {node_id} 的成功路径，提炼可迁移的稳定操作模式"
        reason = "任务完成且有独立验证证据；进入能力巩固，而不是重新学习基础知识。"
        training_mode = "consolidation"
        priority = "normal"
        deliverables = [
            "成功路径摘要",
            "可迁移规则",
            "一个下一任务的复用验证点",
        ]
    else:
        objective = f"针对节点 {node_id} 的失败原因做定向补强并重新验证"
        reason = "Worker 任务未形成独立验证通过结果，需要育成师安排针对性训练。"
        training_mode = "remediation"
        priority = "high"
        deliverables = [
            "失败根因说明",
            "最小修复/训练方案",
            "可重复的验证步骤",
            "一次真实任务复测结果",
        ]

    if failure_reasons:
        objective += "；重点：" + "；".join(failure_reasons[:3])

    now = datetime.now(timezone.utc).isoformat()
    recommendation_id = f"growth:{employee_id}:{mission_run_id}:{node_id}"
    return {
        "recommendation_id": recommendation_id,
        "member_id": employee_id,
        "worker_id": worker_id or None,
        "source_mission_run_id": mission_run_id,
        "source_node_id": node_id,
        "title": ("能力巩固训练" if training_mode == "consolidation" else "失败补强训练"),
        "objective": objective,
        "reason": reason,
        "training_mode": training_mode,
        "priority": priority,
        "role": role,
        "deliverables": deliverables,
        "failure_reasons": failure_reasons,
        "status": "suggested",
        "created_at": now,
        "metadata": {
            "source": "talent_center_worker_growth",
            "source_outcome_status": status,
            "independent_verification_status": verified_status or "unavailable",
            "automatic_retry": False,
        },
    }


def apply_worker_growth_recommendation(
    *,
    runtime: dict[str, Any],
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    """Write the recommendation into Talent Center state without dispatching it."""
    if not isinstance(runtime, dict) or not isinstance(recommendation, dict):
        raise ValueError("growth recommendation context is invalid")
    member_id = _text(recommendation.get("member_id"), 120)
    if not member_id:
        raise ValueError("growth recommendation member_id is required")

    members_payload = runtime.get("child_members")
    if isinstance(members_payload, dict):
        members = members_payload.get("items")
        if not isinstance(members, list):
            raise ValueError("Talent Center child_members.items are missing")
        members_container = members_payload
    elif isinstance(members_payload, list):
        members = members_payload
        members_container = None
    else:
        raise ValueError("Talent Center child_members are missing")

    target = next(
        (
            item for item in members
            if isinstance(item, dict)
            and _text(item.get("member_id"), 120) == member_id
        ),
        None,
    )
    if target is None:
        raise ValueError("growth recommendation employee does not exist")

    training_plan = target.get("training_plan") if isinstance(target.get("training_plan"), dict) else {}
    recommendations = runtime.get("task_center", {}).get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = []

    # Idempotent by source mission/node: a repeated terminal callback does not
    # create another training assignment.
    rec_id = _text(recommendation.get("recommendation_id"), 240)
    existing = next(
        (
            item for item in recommendations
            if isinstance(item, dict)
            and _text(item.get("recommendation_id"), 240) == rec_id
        ),
        None,
    )
    if existing is None:
        recommendations.append(dict(recommendation))

    target["training_plan"] = {
        **training_plan,
        "stage": (
            "remediation_planned"
            if recommendation.get("training_mode") == "remediation"
            else "active_training"
        ),
        "owner_member_id": "talent_development_officer",
        "latest_growth_recommendation_id": rec_id,
        "latest_growth_objective": recommendation.get("objective"),
        "latest_growth_reason": recommendation.get("reason"),
        "latest_growth_at": recommendation.get("created_at"),
        "next_action": "育成师审核推荐并安排训练任务；未审核前不得自动重放原任务。",
    }

    runtime["task_center"] = {
        **(runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}),
        "recommendations": recommendations[-80:],
    }
    if members_container is not None:
        members_container["items"] = members
        runtime["child_members"] = members_container
    else:
        runtime["child_members"] = members
    return runtime


def growth_recommendation_requires_training(recommendation: dict[str, Any]) -> bool:
    return _text(recommendation.get("training_mode"), 40) == "remediation"


__all__ = [
    "apply_worker_growth_recommendation",
    "build_worker_growth_recommendation",
    "growth_recommendation_requires_training",
]
