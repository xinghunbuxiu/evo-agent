"""
自治学习运行时：草稿学习任务生成与计划入库。
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Callable


def draft_learning_task_id(
    tenant_id: str,
    mission_kind: str,
    node_id: str,
    context: dict | None = None,
) -> str:
    context = context if isinstance(context, dict) else {}
    seed = "::".join([
        str(tenant_id or "default"),
        str(mission_kind or "mission"),
        str(node_id or "node"),
        str(context.get("source_path") or context.get("bundle_path") or context.get("source_dir") or context.get("work_type_id") or ""),
    ])
    return f"draft:{tenant_id}:{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:12]}"


def normalize_mission_learning_task_payload(
    *,
    tenant_id: str,
    mission_kind: str,
    goal: str,
    context: dict,
    payload: dict,
    trim_candidate_text: Callable[[str | None, int], str],
) -> dict:
    source_context = payload.get("source_context", {}) if isinstance(payload.get("source_context"), dict) else {}
    merged_context = {
        "source_path": context.get("source_path") or context.get("bundle_path") or context.get("path") or source_context.get("source_path"),
        "bundle_path": context.get("bundle_path") or context.get("source_path") or source_context.get("source_path"),
        "source_dir": context.get("source_dir") or source_context.get("source_dir"),
        "work_type_id": context.get("work_type_id") or source_context.get("work_type_id"),
        "channel": context.get("channel"),
        "account_id": context.get("account_id"),
    }
    learning_task_id = str(payload.get("task_id") or "").strip() or draft_learning_task_id(
        tenant_id=tenant_id,
        mission_kind=mission_kind,
        node_id=str(payload.get("node_id") or "node"),
        context=merged_context,
    )
    status = str(payload.get("status") or "needs_learning")
    if status not in {"needs_learning", "needs_input", "ready", "researching", "candidate_found", "ready_for_validation"}:
        status = "needs_learning"
    gap_type = str(payload.get("gap_type") or "capability_gap")
    title = str(payload.get("title") or payload.get("node_id") or "Draft Learning Task")
    learning_objectives = payload.get("learning_objectives", []) if isinstance(payload.get("learning_objectives"), list) else []
    validation_checks = payload.get("validation_checks", []) if isinstance(payload.get("validation_checks"), list) else []
    blockers = payload.get("blockers", []) if isinstance(payload.get("blockers"), list) else []
    next_actions = payload.get("next_actions", []) if isinstance(payload.get("next_actions"), list) else []
    recommended_skill_ids = payload.get("recommended_skill_ids", []) if isinstance(payload.get("recommended_skill_ids"), list) else []

    issue_category = {
        "needs_input": "input_gap",
        "capability_gap": "capability_gap",
        "knowledge_gap": "strategy_gap",
        "experience_gap": "strategy_gap",
        "ready": "observation_needed",
        "reuse_existing": "observation_needed",
    }.get(gap_type, gap_type)

    if gap_type == "input_gap":
        queries = [f"补齐缺失输入: {item}" for item in blockers[:3]]
    else:
        queries = [str(item) for item in learning_objectives[:3] if str(item).strip()]
    if not queries:
        queries = [f"围绕节点 {payload.get('node_id') or '--'} 建立最小学习实验"]

    candidate_approaches = [
        {
            "source": "mission_plan",
            "title": title,
            "summary": trim_candidate_text("；".join(str(item) for item in learning_objectives[:2]) or "等待自治学习器根据 mission 缺口继续展开", 180),
            "confidence": 0.42 if status == "needs_learning" else 0.35,
            "evidence": [
                f"mission_kind={mission_kind}",
                f"gap_type={gap_type}",
                f"priority={payload.get('priority') or 'medium'}",
            ],
            "next_steps": next_actions[:3] if next_actions else ["先收敛成一个最小实验，再进入验证"],
            "metadata": {
                "from": "mission_plan",
                "node_id": payload.get("node_id"),
                "recommended_skill_ids": recommended_skill_ids[:5],
            },
        }
    ]

    return {
        "task_id": learning_task_id,
        "tenant_id": tenant_id,
        "goal": goal,
        "mission_kind": mission_kind,
        "mission_node_id": payload.get("node_id"),
        "title": title,
        "source": "mission_plan",
        "bundle_path": merged_context.get("bundle_path"),
        "source_dir": merged_context.get("source_dir"),
        "work_type_id": merged_context.get("work_type_id"),
        "channel": merged_context.get("channel"),
        "account_id": merged_context.get("account_id"),
        "issue_category": issue_category,
        "gap_type": gap_type,
        "priority": payload.get("priority") or "medium",
        "capability_type": payload.get("capability_type"),
        "queries": queries,
        "preferred_sources": ["local_memory", "platform_shared", "historical_archive", "ai_assist"],
        "validation_gate": "Mission 草案需要先补输入或做最小实验，再进入真实样本验证。",
        "status": status,
        "blockers": blockers,
        "learning_objectives": learning_objectives,
        "validation_checks": validation_checks,
        "next_actions": next_actions,
        "recommended_skill_ids": recommended_skill_ids,
        "source_runs": [
            {"source": "mission_plan", "status": "drafted", "candidate_count": len(candidate_approaches)},
            {"source": "local_memory", "status": "pending", "candidate_count": 0},
            {"source": "platform_shared", "status": "pending", "candidate_count": 0},
        ],
        "candidate_approaches": candidate_approaches,
        "next_validation_action": (
            "先补齐阻塞输入后重新规划"
            if status == "needs_input"
            else "将当前节点转成最小实验并做一次真实执行验证"
        ),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }


def upsert_plan_learning_tasks(
    *,
    workspace,
    tenant_id: str,
    mission_kind: str,
    goal: str,
    context: dict,
    plan: dict,
    load_learning_tasks: Callable,
    save_learning_tasks: Callable,
    normalize_mission_learning_task_payload_fn: Callable[..., dict],
) -> list[str]:
    learning_state = load_learning_tasks(workspace)
    tasks = learning_state.get("tasks", {}) if isinstance(learning_state, dict) else {}
    tasks = tasks if isinstance(tasks, dict) else {}
    stored_ids: list[str] = []
    for item in (plan.get("learning_tasks", []) if isinstance(plan.get("learning_tasks"), list) else []):
        if not isinstance(item, dict):
            continue
        normalized = normalize_mission_learning_task_payload_fn(
            tenant_id=tenant_id,
            mission_kind=mission_kind,
            goal=goal,
            context=context,
            payload=item,
        )
        existing = tasks.get(normalized["task_id"])
        if isinstance(existing, dict):
            normalized["created_at"] = existing.get("created_at") or normalized.get("created_at")
            if str(existing.get("status") or "") in {"validating", "validated_improved", "validated_unchanged", "resolved", "candidate_found", "ready_for_validation"}:
                normalized["status"] = str(existing.get("status"))
                normalized["source_runs"] = existing.get("source_runs", normalized.get("source_runs", []))
                normalized["candidate_approaches"] = existing.get("candidate_approaches", normalized.get("candidate_approaches", []))
                normalized["next_validation_action"] = existing.get("next_validation_action") or normalized.get("next_validation_action")
        tasks[normalized["task_id"]] = normalized
        stored_ids.append(normalized["task_id"])
    if stored_ids:
        save_learning_tasks(workspace, {"tasks": tasks})
    return stored_ids
