"""
Mission 动作编排运行时。
"""

from __future__ import annotations

from typing import Any, Callable


def _append_base_action(
    *,
    actions: list[dict],
    node_id: str,
    title: str | None,
    action_type: str,
    status: str,
    detail: str,
    matched_skill_ids: list[str],
    matched_skills: list[dict],
    work_type: dict,
    work_type_summary: dict,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "node_id": node_id,
        "title": title,
        "action_type": action_type,
        "status": status,
        "detail": detail,
        "matched_verified_skill_ids": matched_skill_ids,
        "matched_verified_skills": matched_skills[:3],
        "work_type_id": work_type.get("work_type_id"),
        "work_type_title": work_type.get("title"),
        "delivery_targets": work_type_summary.get("deliverables", []),
    }
    if isinstance(extra, dict):
        payload.update(extra)
    actions.append(payload)


def create_mission_action_runtime_bindings(
    *,
    normalize_string_list: Callable[[object], list[str]],
    task_priority_cls,
    mission_action_handlers: dict[str, Callable] | None = None,
    context_resolvers: dict[str, Callable[[dict], dict]] | None = None,
):
    def build_mission_actions(
        *,
        task_queue,
        tenant_id: str,
        mission_run_id: str,
        plan: dict,
        context: dict,
        work_type: dict,
        work_type_summary: dict,
    ) -> dict[str, Any]:
        resolved_context = dict(context)
        runtime_route = plan.get("runtime_route", {}) if isinstance(plan.get("runtime_route"), dict) else {}
        execution_preference = str(
            runtime_route.get("execution_preference")
            or resolved_context.get("runtime_execution_preference")
            or ""
        ).strip() or "worker"
        primary_package_id = str(
            runtime_route.get("primary_package_id")
            or resolved_context.get("runtime_primary_package_id")
            or ""
        ).strip() or None
        primary_capability_id = str(
            runtime_route.get("primary_capability_id")
            or resolved_context.get("runtime_primary_capability_id")
            or ""
        ).strip() or None
        primary_worker_id = str(
            runtime_route.get("primary_worker_id")
            or resolved_context.get("runtime_primary_worker_id")
            or ""
        ).strip()
        context_resolver = context_resolvers.get(primary_worker_id) if isinstance(context_resolvers, dict) else None
        if callable(context_resolver):
            resolved_context = context_resolver(context)
        worker_handler = mission_action_handlers.get(primary_worker_id) if isinstance(mission_action_handlers, dict) else None

        plan_learning_tasks = plan.get("learning_tasks", []) if isinstance(plan.get("learning_tasks"), list) else []
        plan_learning_task_map: dict[str, str] = {}
        for item in plan_learning_tasks:
            if not isinstance(item, dict):
                continue
            node_key = str(item.get("node_id") or "").strip()
            task_key = str(item.get("task_id") or "").strip()
            if node_key and task_key:
                plan_learning_task_map[node_key] = task_key

        actions: list[dict] = []
        submitted_task_ids: list[str] = []
        counts = {
            "submitted": 0,
            "needs_learning": 0,
            "needs_input": 0,
            "planned_only": 0,
        }

        for node in plan.get("nodes", []):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "node")
            task_type = str(node.get("task_type") or "plan")
            node_status = str(node.get("status") or "planned")
            capability_type = str(node.get("capability_type") or "")
            matched_skill_ids = normalize_string_list(node.get("recommended_skill_ids"))
            matched_skills = node.get("recommended_skills", [])
            if not isinstance(matched_skills, list):
                matched_skills = []

            if callable(worker_handler):
                handled = worker_handler(
                    task_queue=task_queue,
                    tenant_id=tenant_id,
                    mission_run_id=mission_run_id,
                    plan=plan,
                    node=node,
                    resolved_context=resolved_context,
                    work_type=work_type,
                    work_type_summary=work_type_summary,
                    counts=counts,
                    actions=actions,
                    submitted_task_ids=submitted_task_ids,
                    matched_skill_ids=matched_skill_ids,
                    matched_skills=matched_skills,
                    append_action=_append_base_action,
                    task_priority_cls=task_priority_cls,
                )
                if handled:
                    continue

            if node_status == "needs_learning" or task_type in {"learn", "promote", "validate", "plan", "collect", "execute"}:
                counts["needs_learning"] += 1
                _append_base_action(
                    actions=actions,
                    node_id=node_id,
                    title=node.get("title"),
                    action_type="learning_ticket",
                    status="needs_learning",
                    detail="当前先生成学习/研究动作，等待后续自治学习器接手",
                    matched_skill_ids=matched_skill_ids,
                    matched_skills=matched_skills,
                    work_type=work_type,
                    work_type_summary=work_type_summary,
                    extra={
                        "capability_type": capability_type,
                        "execution_preference": execution_preference,
                        "primary_package_id": primary_package_id,
                        "primary_capability_id": primary_capability_id,
                        "primary_worker_id": primary_worker_id or None,
                        "linked_learning_task_id": plan_learning_task_map.get(node_id),
                        "next_actions": node.get("next_actions", []),
                    },
                )
                continue

            counts["planned_only"] += 1
            _append_base_action(
                actions=actions,
                node_id=node_id,
                title=node.get("title"),
                action_type="planned_only",
                status="planned",
                detail="当前仅保留在 mission plan 中，尚未进入自动执行",
                matched_skill_ids=matched_skill_ids,
                matched_skills=matched_skills,
                work_type=work_type,
                work_type_summary=work_type_summary,
                extra={
                    "execution_preference": execution_preference,
                    "primary_package_id": primary_package_id,
                    "primary_capability_id": primary_capability_id,
                    "primary_worker_id": primary_worker_id or None,
                },
            )

        # Preserve planner evidence on the concrete action record so execution
        # and dispatch logs can be traced back to the planning decision.
        decision_trace_by_node = {
            str(node.get("id") or "node"): node.get("decision_trace", [])
            for node in plan.get("nodes", [])
            if isinstance(node, dict)
        }
        for action in actions:
            if not isinstance(action, dict):
                continue
            trace = decision_trace_by_node.get(str(action.get("node_id") or ""), [])
            if isinstance(trace, list) and trace and not action.get("decision_trace"):
                action["decision_trace"] = trace

        mission_skill_ids: list[str] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            for skill_id in normalize_string_list(action.get("matched_verified_skill_ids")):
                if skill_id not in mission_skill_ids:
                    mission_skill_ids.append(skill_id)

        overall_status = "submitted" if counts["submitted"] else "planning_only"
        if counts["needs_input"] and not counts["submitted"]:
            overall_status = "blocked"
        elif counts["needs_learning"] and not counts["submitted"]:
            overall_status = "needs_learning"

        return {
            "resolved_context": resolved_context,
            "actions": actions,
            "submitted_task_ids": submitted_task_ids,
            "counts": counts,
            "matched_verified_skill_ids": mission_skill_ids,
            "status": overall_status,
            "execution_preference": execution_preference,
            "primary_package_id": primary_package_id,
            "primary_capability_id": primary_capability_id,
            "primary_worker_id": primary_worker_id or None,
        }

    return {
        "build_mission_actions": build_mission_actions,
    }


__all__ = [
    "create_mission_action_runtime_bindings",
]
