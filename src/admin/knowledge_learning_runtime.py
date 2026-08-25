"""
岗位成员补知识学习任务：验证触发与 training_plan 回写。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from admin.runtime_state import load_learning_tasks, save_learning_tasks
from admin.formal_task_evolution_runtime import (
    evaluate_independence_readiness,
    maybe_notify_independence_readiness,
    maybe_recommend_formal_task_after_knowledge,
)


def _trim(text: object | None, limit: int = 180) -> str:
    raw = str(text or "").strip()
    return raw[:limit]


def summarize_knowledge_learning_task(learning_task: dict) -> str:
    if not isinstance(learning_task, dict):
        return ""
    approaches = learning_task.get("candidate_approaches") if isinstance(learning_task.get("candidate_approaches"), list) else []
    if approaches and isinstance(approaches[0], dict):
        summary = _trim(approaches[0].get("summary") or approaches[0].get("title"), 160)
        if summary:
            return summary
    return _trim(learning_task.get("goal") or learning_task.get("title"), 160)


def knowledge_learning_next_action(status: str) -> str:
    normalized = str(status or "").strip()
    mapping = {
        "needs_learning": "系统正在补知识，等待调研结果后再推进正式任务",
        "researching": "补知识调研进行中，请等待系统整理可执行方案",
        "candidate_found": "补知识已有候选方案，可回到正式任务做最小验证",
        "ready_for_validation": "补知识待验证，可启动验证或分配新一轮正式任务",
        "validating": "补知识验证进行中，等待结果回写",
        "validated_improved": "补知识验证通过，可继续推进下一轮正式任务",
        "validated_unchanged": "补知识验证完成，建议带着结论回到正式任务",
        "resolved": "补知识已完成，继续岗位稳定性训练",
    }
    return mapping.get(normalized, "等待补知识任务推进")


def knowledge_learning_stage_for_status(current_stage: str, status: str) -> str:
    stage = str(current_stage or "").strip()
    normalized = str(status or "").strip()
    if normalized in {"validated_improved", "validated_unchanged", "resolved"}:
        if stage in {"", "knowledge_supplementing"}:
            return "active_training"
    if normalized in {"needs_learning", "researching", "candidate_found", "ready_for_validation", "validating"}:
        if stage in {"", "profile_initialized", "awaiting_assignment"}:
            return "knowledge_supplementing"
    return stage or "knowledge_supplementing"


def find_member_knowledge_learning_task(
    tasks: dict,
    *,
    member_id: str,
    linked_task_id: str | None = None,
) -> tuple[str | None, dict | None]:
    if not isinstance(tasks, dict):
        return None, None
    normalized_member_id = str(member_id or "").strip()
    linked = str(linked_task_id or "").strip()
    if linked and isinstance(tasks.get(linked), dict):
        return linked, tasks.get(linked)
    for task_id, payload in tasks.items():
        if not isinstance(payload, dict):
            continue
        if str(payload.get("member_id") or "").strip() != normalized_member_id:
            continue
        if str(payload.get("source") or "").strip() != "memory_hub_auto":
            continue
        return str(task_id), payload
    return None, None


def sync_member_knowledge_learning_writeback(
    *,
    workspace: Path,
    runtime: dict,
    tenant_id: str,
    normalize_child_members_runtime: Callable,
) -> dict:
    learning_state = load_learning_tasks(workspace)
    tasks = learning_state.get("tasks") if isinstance(learning_state.get("tasks"), dict) else {}
    members = normalize_child_members_runtime(
        runtime.get("child_members"),
        legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
    )
    items = members.get("items") if isinstance(members.get("items"), list) else []
    for member in items:
        if not isinstance(member, dict):
            continue
        member_id = str(member.get("member_id") or "").strip()
        if not member_id:
            continue
        training_plan = member.get("training_plan") if isinstance(member.get("training_plan"), dict) else {}
        linked_task_id = str(training_plan.get("knowledge_learning_task_id") or "").strip() or None
        task_id, learning_task = find_member_knowledge_learning_task(
            tasks,
            member_id=member_id,
            linked_task_id=linked_task_id,
        )
        if not isinstance(learning_task, dict) or not task_id:
            continue
        status = str(learning_task.get("status") or "").strip()
        previous_status = str(training_plan.get("knowledge_learning_status") or "").strip()
        summary = summarize_knowledge_learning_task(learning_task)
        task_center = runtime.get("task_center", {}) if isinstance(runtime.get("task_center"), dict) else {}
        independence = evaluate_independence_readiness(member=member, task_center=task_center)
        # Write learning outcome into experience_journal when candidates exist
        if status in {
            "candidate_found",
            "ready_for_validation",
            "validated_improved",
            "validated_unchanged",
            "resolved",
        } and summary:
            from admin.model_provider_runtime import append_learning_experience_card

            learning_task_with_id = {**learning_task, "task_id": task_id}
            append_learning_experience_card(
                member,
                learning_task=learning_task_with_id,
                summary=summary,
            )
        member["training_plan"] = {
            **training_plan,
            "knowledge_learning_task_id": task_id,
            "knowledge_learning_status": status,
            "knowledge_learning_summary": summary or training_plan.get("knowledge_learning_summary"),
            "knowledge_learning_updated_at": learning_task.get("updated_at") or datetime.now().isoformat(),
            "knowledge_learning_validated_at": (
                learning_task.get("auto_validation", {}).get("finalized_at")
                if isinstance(learning_task.get("auto_validation"), dict)
                and learning_task.get("auto_validation", {}).get("finalized_at")
                else training_plan.get("knowledge_learning_validated_at")
            ),
            "stage": knowledge_learning_stage_for_status(str(training_plan.get("stage") or ""), status),
            "next_action": knowledge_learning_next_action(status),
            "independence_readiness": independence,
        }
        maybe_recommend_formal_task_after_knowledge(
            workspace=workspace,
            runtime=runtime,
            member=member,
            learning_task=learning_task,
            learning_task_id=task_id,
            previous_status=previous_status,
        )
        maybe_notify_independence_readiness(runtime=runtime, member=member)
    runtime["child_members"] = members
    return runtime


def trigger_member_knowledge_learning_validation(
    *,
    workspace: Path,
    tenant_id: str,
    task_id: str,
    refresh_runtime_learning_tasks: Callable[..., dict],
    tenant_manager,
    task_queue,
) -> dict | None:
    learning_state = load_learning_tasks(workspace)
    tasks = learning_state.get("tasks") if isinstance(learning_state.get("tasks"), dict) else {}
    payload = tasks.get(task_id) if isinstance(tasks.get(task_id), dict) else None
    if not isinstance(payload, dict):
        raise ValueError("学习任务不存在")
    if str(payload.get("source") or "").strip() != "memory_hub_auto":
        return None

    now_iso = datetime.now().isoformat()
    goal = _trim(payload.get("goal") or payload.get("title"), 180)
    queries = payload.get("queries") if isinstance(payload.get("queries"), list) else []
    payload["status"] = "researching"
    payload["updated_at"] = now_iso
    payload["next_validation_action"] = "正在整理补知识候选方案，完成后回到正式任务验证"
    tasks[task_id] = payload
    save_learning_tasks(workspace, {"tasks": tasks})

    refresh_runtime_learning_tasks(
        workspace=workspace,
        tenant_manager=tenant_manager,
        task_queue=task_queue,
        tenant_id=tenant_id,
    )

    learning_state = load_learning_tasks(workspace)
    tasks = learning_state.get("tasks") if isinstance(learning_state.get("tasks"), dict) else {}
    payload = tasks.get(task_id) if isinstance(tasks.get(task_id), dict) else payload
    if not isinstance(payload, dict):
        raise ValueError("学习任务不存在")

    current_status = str(payload.get("status") or "").strip()
    if current_status in {"", "needs_learning", "researching"}:
        mode = "knowledge_learning_lightweight"
        candidate = {
            "source": "memory_hub_auto",
            "title": _trim(payload.get("title"), 120) or "补知识候选方案",
            "summary": goal or _trim(queries[0] if queries else "", 180) or "围绕当前岗位缺口整理出的可执行补知识方案",
            "confidence": 0.58,
            "evidence": [str(item) for item in queries[:3] if str(item).strip()],
            "next_steps": ["带着补知识结论回到正式任务", "执行一轮最小可验证动作", "提交结果与变化说明"],
            "metadata": {"from": "memory_hub_auto_validate"},
        }
        # Prefer configured OpenAI-compatible model (DeepSeek / gateway / …)
        try:
            from admin.model_provider_runtime import run_configured_ai_assist

            role_hint = str(payload.get("role_label") or payload.get("work_type_id") or "岗位员工")
            ai_result = run_configured_ai_assist(
                tenant_manager=tenant_manager,
                tenant_id=tenant_id,
                goal=goal,
                queries=[str(q) for q in queries if str(q).strip()],
                role_hint=role_hint,
            )
            if isinstance(ai_result.get("candidate"), dict) and ai_result.get("status") == "completed":
                candidate = ai_result["candidate"]
                mode = "knowledge_learning_model_provider"
        except Exception as exc:  # noqa: BLE001 — keep lightweight fallback
            candidate["metadata"] = {
                **(candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}),
                "model_provider_error": str(exc)[:180],
            }

        payload["status"] = "candidate_found"
        payload["updated_at"] = datetime.now().isoformat()
        payload["next_validation_action"] = "补知识草案已整理，请回到正式任务做最小验证"
        payload["candidate_approaches"] = [candidate]
        payload["auto_validation"] = {
            "status": "candidate_ready",
            "source": mode,
            "triggered_at": now_iso,
            "finalized_at": payload["updated_at"],
        }
        tasks[task_id] = payload
        save_learning_tasks(workspace, {"tasks": tasks})
        return {
            "mode": mode,
            "task_id": task_id,
            "status": payload.get("status"),
            "message": "补知识任务已整理候选方案，并回写员工训练计划",
        }

    return {
        "mode": "knowledge_learning_lightweight",
        "task_id": task_id,
        "status": payload.get("status"),
        "message": "补知识任务已整理候选方案，并回写员工训练计划",
    }
