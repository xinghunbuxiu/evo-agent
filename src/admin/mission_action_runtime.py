"""
Mission 动作编排运行时。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from core.mission_brain import index_mission_brain_decisions


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

        brain_contract = plan.get("orchestration", {}) if isinstance(plan.get("orchestration"), dict) else {}
        brain_decisions = index_mission_brain_decisions(brain_contract)
        raw_coordination_plan = brain_contract.get("coordination_plan")
        coordination_plan = raw_coordination_plan if isinstance(raw_coordination_plan, dict) else {}
        raw_coordination_actions = coordination_plan.get("actions")
        coordination_actions = raw_coordination_actions if isinstance(raw_coordination_actions, list) else []
        coordination_ids = [
            str(item.get("node_id") or "").strip()
            for item in coordination_actions
            if isinstance(item, dict)
        ]
        coordination_plan_valid = (
            isinstance(raw_coordination_plan, dict)
            and coordination_plan.get("schema_version") == "mission.coordination.v1"
            and coordination_plan.get("decision_owner") == "mission"
            and coordination_plan.get("dispatch_authorized") is False
            and isinstance(raw_coordination_actions, list)
            and len(coordination_ids) == len(coordination_actions)
            and all(coordination_ids)
            and len(coordination_ids) == len(set(coordination_ids))
        )
        coordination_by_node = {
            str(item.get("node_id")): item
            for item in coordination_actions
            if isinstance(item, dict) and str(item.get("node_id") or "").strip()
        }

        authorization_by_node: dict[str, dict[str, Any]] = {}

        def append_action(**kwargs) -> None:
            node_key = str(kwargs.get("node_id") or "").strip()
            extra = dict(kwargs.get("extra") or {})
            decision = brain_decisions.get(node_key)
            coordination = coordination_by_node.get(node_key)
            extra["orchestration_owner"] = "mission"
            extra["dispatch_mode"] = str(brain_contract.get("dispatch_mode") or "centralized")
            if coordination:
                extra["mission_coordination_action"] = coordination.get("action")
                extra["mission_coordination_reason_code"] = coordination.get("reason_code")
                extra["mission_coordination_dispatch_authorized"] = bool(
                    coordination.get("dispatch_authorized", False)
                )
            authorization = authorization_by_node.get(node_key)
            if authorization:
                extra["mission_runtime_authorization"] = authorization
            if decision:
                extra["mission_brain_decision"] = decision.get("decision")
                extra["decision_trace"] = decision.get("decision_trace", [])
                extra["validation_checks"] = decision.get("validation_checks", [])
                extra["verified_skill_ids"] = decision.get("verified_skill_ids", [])
                workforce_decision = decision.get("workforce_decision")
                if isinstance(workforce_decision, dict):
                    # A workforce recommendation is evidence, never dispatch authorization.
                    extra["workforce_decision"] = workforce_decision
                    extra["workforce_dispatch_authorized"] = False
            kwargs["extra"] = extra
            _append_base_action(**kwargs)

        def authorize_node_dispatch(
            node: dict,
            coordination: dict | None,
            decision: dict | None,
        ) -> dict[str, Any]:
            node_id = str(node["id"]).strip()
            blockers = node["blockers"]
            status = node["status"].strip()
            action_name = str((coordination or {}).get("action") or "")
            reason_code = "authorized"
            authorized = True

            if (
                not coordination_plan_valid
            ):
                authorized, reason_code = False, "coordination_contract_invalid"
            elif coordination is None:
                authorized, reason_code = False, "coordination_action_missing"
            elif coordination.get("dispatch_authorized") is not False:
                authorized, reason_code = False, "coordination_action_must_not_authorize_dispatch"
            elif action_name not in {
                "prepare_for_authorized_dispatch",
                "await_dispatch_authorization",
                "reuse_verified_knowledge_then_validate",
            }:
                authorized, reason_code = False, "coordination_action_not_dispatchable"
            elif action_name == "reuse_verified_knowledge_then_validate" and status != "reuse_existing":
                authorized, reason_code = False, "verified_reuse_status_mismatch"
            elif action_name != "reuse_verified_knowledge_then_validate" and status != "ready":
                authorized, reason_code = False, "node_not_ready"
            elif blockers:
                authorized, reason_code = False, "node_blockers_present"
            elif action_name == "reuse_verified_knowledge_then_validate" and not (
                node["recommended_skill_ids"] and node["validation_checks"]
            ):
                authorized, reason_code = False, "verified_skill_or_validation_evidence_missing"
            else:
                runtime_target = primary_worker_id or primary_package_id or primary_capability_id
                if not runtime_target:
                    authorized, reason_code = False, "runtime_target_missing"
                else:
                    workforce = decision.get("workforce_decision") if isinstance(decision, dict) else None
                    if not isinstance(workforce, dict):
                        authorized, reason_code = False, "workforce_decision_missing"
                    elif (
                        workforce.get("dispatch_state") != "recommendation_only"
                        or workforce.get("dispatch_authorized") is not False
                    ):
                        authorized, reason_code = False, "workforce_contract_invalid"
                    else:
                        workforce_result = str(workforce.get("decision") or "")
                        recommended_worker = str(workforce.get("recommended_worker_id") or "").strip()
                        if workforce_result != "assign_existing_worker_recommended":
                            authorized, reason_code = False, "workforce_recommendation_not_assignable"
                        elif not primary_worker_id or recommended_worker != primary_worker_id:
                            authorized, reason_code = False, "runtime_worker_does_not_match_recommendation"

            workforce = decision.get("workforce_decision") if isinstance(decision, dict) else None
            return {
                "schema_version": "mission.dispatch.authorization.v1",
                "mission_run_id": mission_run_id,
                "node_id": node_id,
                "decision_owner": "mission_runtime",
                "authorized": authorized,
                "policy_rule_id": "mission.dispatch.ready_route_gate.v1",
                "reason_code": reason_code,
                "evidence": {
                    "node_status": status,
                    "blocker_codes": [str(item) for item in blockers],
                    "coordination_action": action_name or None,
                    "runtime_target": primary_worker_id or primary_package_id or primary_capability_id,
                    "recommended_worker_id": (
                        workforce.get("recommended_worker_id") if isinstance(workforce, dict) else None
                    ),
                },
                "authorized_at": datetime.now(timezone.utc).isoformat() if authorized else None,
            }

        actions: list[dict] = []
        submitted_task_ids: list[str] = []
        counts = {
            "submitted": 0,
            "needs_learning": 0,
            "needs_input": 0,
            "planned_only": 0,
        }

        nodes = plan.get("nodes")
        if not isinstance(nodes, list):
            raise ValueError("Mission plan requires a nodes list")
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                raise ValueError(f"Mission plan node at index {index} must be an object")
            for field_name in ("id", "status", "task_type", "decision_trace", "blockers", "recommended_skill_ids", "validation_checks"):
                if field_name not in node:
                    raise ValueError(f"Mission plan node at index {index} requires field {field_name!r}")
            node_id = str(node["id"] or "").strip()
            if not node_id:
                raise ValueError(f"Mission plan node at index {index} requires a non-empty id")
            if not isinstance(node["status"], str) or not node["status"].strip():
                raise ValueError(f"Mission plan node {node_id!r} requires a non-empty status")
            if not isinstance(node["task_type"], str) or not node["task_type"].strip():
                raise ValueError(f"Mission plan node {node_id!r} requires a non-empty task_type")
            if not isinstance(node["decision_trace"], list):
                raise ValueError(f"Mission plan node {node_id!r} requires list field 'decision_trace'")
            if not isinstance(node["blockers"], list):
                raise ValueError(f"Mission plan node {node_id!r} requires list field 'blockers'")
            if not isinstance(node["recommended_skill_ids"], list):
                raise ValueError(f"Mission plan node {node_id!r} requires list field 'recommended_skill_ids'")
            if not isinstance(node["validation_checks"], list):
                raise ValueError(f"Mission plan node {node_id!r} requires list field 'validation_checks'")
            task_type = node["task_type"].strip()
            node_status = node["status"].strip()
            capability_type = str(node.get("capability_type") or "")
            matched_skill_ids = normalize_string_list(node["recommended_skill_ids"])
            matched_skills = node.get("recommended_skills", [])
            if not isinstance(matched_skills, list):
                matched_skills = []

            coordination = coordination_by_node.get(node_id)
            decision = brain_decisions.get(node_id)
            authorization = authorize_node_dispatch(node, coordination, decision)
            authorization_by_node[node_id] = authorization

            if not authorization["authorized"]:
                reason_code = authorization["reason_code"]
                coordination_name = str((coordination or {}).get("action") or "")
                if coordination_name == "request_missing_input":
                    counts["needs_input"] += 1
                    action_type, action_status = "needs_input", "blocked"
                    detail = "Mission 主脑判定缺少必需输入，运行时拒绝派发"
                elif coordination_name == "resolve_capability_or_learning_gap":
                    counts["needs_learning"] += 1
                    action_type, action_status = "learning_ticket", "needs_learning"
                    detail = "Mission 主脑判定存在能力缺口，运行时拒绝派发"
                elif coordination_name == "reuse_verified_knowledge_then_validate":
                    counts["planned_only"] += 1
                    action_type, action_status = "knowledge_reuse_pending", "planned"
                    detail = "应先复用已验证知识并完成当前任务验证，暂不派发新执行"
                else:
                    action_type, action_status = "dispatch_denied", "blocked"
                    detail = f"Mission 运行时拒绝派发：{reason_code}"
                append_action(
                    actions=actions,
                    node_id=node_id,
                    title=node.get("title"),
                    action_type=action_type,
                    status=action_status,
                    detail=detail,
                    matched_skill_ids=matched_skill_ids,
                    matched_skills=matched_skills,
                    work_type=work_type,
                    work_type_summary=work_type_summary,
                    extra={
                        "task_type": task_type,
                        "capability_type": capability_type,
                        "mission_runtime_authorization": authorization,
                        "next_actions": node.get("next_actions", []),
                    },
                )
                continue

            dispatch_node = dict(node)
            dispatch_node["mission_runtime_authorization"] = authorization
            if callable(worker_handler):
                handled = worker_handler(
                    task_queue=task_queue,
                    tenant_id=tenant_id,
                    mission_run_id=mission_run_id,
                    plan=plan,
                    node=dispatch_node,
                    resolved_context=resolved_context,
                    work_type=work_type,
                    work_type_summary=work_type_summary,
                    counts=counts,
                    actions=actions,
                    submitted_task_ids=submitted_task_ids,
                    matched_skill_ids=matched_skill_ids,
                    matched_skills=matched_skills,
                    append_action=append_action,
                    task_priority_cls=task_priority_cls,
                )
                if handled:
                    continue

            if node_status == "needs_learning" or task_type in {"learn", "promote", "validate", "plan", "collect", "execute"}:
                counts["needs_learning"] += 1
                append_action(
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
            append_action(
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
            str(node.get("id") or "node"): node["decision_trace"]
            for node in plan["nodes"]
        }
        for action in actions:
            action["decision_trace"] = decision_trace_by_node[str(action["node_id"])]

        mission_skill_ids: list[str] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            for skill_id in normalize_string_list(action.get("matched_verified_skill_ids")):
                if skill_id not in mission_skill_ids:
                    mission_skill_ids.append(skill_id)

        overall_status = "submitted" if counts["submitted"] else "planning_only"
        has_dispatch_denial = any(
            isinstance(action, dict)
            and action.get("action_type") == "dispatch_denied"
            and action.get("status") == "blocked"
            for action in actions
        )
        if (counts["needs_input"] or has_dispatch_denial) and not counts["submitted"]:
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
