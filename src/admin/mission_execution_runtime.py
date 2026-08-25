"""
Mission 执行运行时：任务刷新、学习动作推进、经验沉淀与失败学习闭环。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from core.tenant import TenantManager


def create_mission_execution_bindings(
    *,
    load_learning_tasks: Callable,
    save_learning_tasks: Callable,
    collect_task_verified_skills: Callable,
    skill_ids_from_items: Callable,
    infer_framework_hint_from_delivery: Callable,
    create_mission_delivery_skill_candidate: Callable,
    safe_float: Callable[[object, float], float],
    trim_candidate_text: Callable,
    record_growth_event: Callable,
    build_snapshot_signature: Callable,
    normalize_string_list: Callable,
    build_external_learning_plan: Callable,
    execute_learning_task: Callable,
    make_learning_task_id: Callable,
    extract_task_snapshot: Callable,
    resolve_effective_growth_policy: Callable,
    growth_policy_decision_label: Callable,
    effective_platform_promotion_status: Callable,
    mission_post_action_handlers: dict[str, Callable] | None = None,
    mission_summary_handlers: dict[str, Callable] | None = None,
):
    def extract_node_role_reflection_context(mission_run: dict, node_id: str) -> dict:
        if not isinstance(mission_run, dict):
            return {}
        plan = mission_run.get("plan", {}) if isinstance(mission_run.get("plan"), dict) else {}
        nodes = plan.get("nodes") if isinstance(plan.get("nodes"), list) else []
        for item in nodes:
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "").strip() != str(node_id or "").strip():
                continue
            payload = item.get("role_reflection_context", {})
            return payload if isinstance(payload, dict) else {}
        return {}

    def build_mission_failure_sample(mission_run: dict, action: dict, failed_task) -> dict:
        payload = failed_task.payload or {}
        source_path = (
            payload.get("path")
            or payload.get("source_dir")
            or mission_run.get("context", {}).get("source_path")
            or mission_run.get("context", {}).get("source_dir")
        )
        source_path = str(source_path or "")
        return {
            "bundle_path": source_path,
            "source_dir": source_path,
            "sample_signature": f"mission:{failed_task.id}:{action.get('node_id') or 'node'}",
            "latest_mtime": 0.0,
        }

    def build_mission_failure_diagnosis(mission_run: dict, action: dict, failed_task) -> dict:
        payload = failed_task.payload or {}
        task_type = str(failed_task.type or action.get("task_type") or "")
        role_reflection_context = extract_node_role_reflection_context(mission_run, str(action.get("node_id") or ""))
        role_next_experiment = str(role_reflection_context.get("next_experiment") or "").strip()
        role_summary = str(role_reflection_context.get("summary") or "").strip()
        base_snapshot = {
            "task_id": failed_task.id,
            "task_type": task_type,
            "status": failed_task.status.value,
            "capability_id": (
                (failed_task.result or {}).get("capability_id")
                or payload.get("capability_id")
            ),
            "issue_category": "execution_error",
            "recommended_actions": [
                "复核失败任务的输入路径、signals 与 strategy 决策",
                "从本地经验、平台共享和企业私有仓中搜索相似失败案例",
                *( [f"优先回到岗位最近实验: {role_next_experiment}"] if role_next_experiment else [] ),
            ],
            "evaluation_metrics": {},
        }
        diagnosis = {
            "bundle_path": (
                payload.get("path")
                or payload.get("source_dir")
                or mission_run.get("context", {}).get("source_path")
                or "--"
            ),
            "research_state": "blocked",
            "stable": False,
            "next_action": role_next_experiment or "该 mission 节点执行失败，进入针对性学习与复盘",
            "analyze": {},
            "reconstruct": {},
            "role_reflection_context": role_reflection_context,
        }
        if role_summary:
            diagnosis["role_reflection_summary"] = role_summary
        if task_type == "reconstruct":
            diagnosis["reconstruct"] = base_snapshot
        else:
            diagnosis["analyze"] = base_snapshot
        return diagnosis

    def upsert_mission_failure_learning_task(
        *,
        workspace,
        tenant_manager: TenantManager,
        tenant_id: str,
        mission_run: dict,
        action: dict,
        failed_task,
    ) -> str:
        learning_state = load_learning_tasks(workspace)
        tasks = learning_state.get("tasks", {}) if isinstance(learning_state, dict) else {}
        tasks = tasks if isinstance(tasks, dict) else {}

        existing = next(
            (
                key for key, item in tasks.items()
                if isinstance(item, dict)
                and item.get("source_task_id") == failed_task.id
                and item.get("source") == "mission_failure"
            ),
            None,
        )
        if existing:
            return existing

        sample = build_mission_failure_sample(mission_run, action, failed_task)
        diagnosis = build_mission_failure_diagnosis(mission_run, action, failed_task)
        learning_plan = build_external_learning_plan(
            tenant_manager=tenant_manager,
            tenant_id=tenant_id,
            diagnosis=diagnosis,
        )
        learning_task = execute_learning_task(
            workspace=workspace,
            tenant_manager=tenant_manager,
            tenant_id=tenant_id,
            sample=sample,
            diagnosis=diagnosis,
            learning_plan=learning_plan,
        )
        learning_task["source"] = "mission_failure"
        learning_task["source_task_id"] = failed_task.id
        learning_task["mission_run_id"] = mission_run.get("mission_run_id")
        learning_task["mission_node_id"] = action.get("node_id")
        learning_task["goal"] = mission_run.get("goal")
        learning_task["updated_at"] = datetime.now().isoformat()

        learning_task_id = str(learning_task.get("task_id") or make_learning_task_id(tenant_id, sample))
        tasks[learning_task_id] = learning_task
        save_learning_tasks(workspace, {"tasks": tasks})
        return learning_task_id

    def refresh_mission_learning_action(
        *,
        workspace,
        task_queue,
        tenant_id: str,
        mission_run: dict,
        action: dict,
        successful_task_actions: list[dict],
    ) -> dict:
        if not isinstance(action, dict):
            return action

        linked_learning_task_id = str(action.get("linked_learning_task_id") or "")
        if linked_learning_task_id:
            learning_state = load_learning_tasks(workspace)
            learning_tasks = learning_state.get("tasks", {}) if isinstance(learning_state, dict) else {}
            learning_tasks = learning_tasks if isinstance(learning_tasks, dict) else {}
            linked_learning_task = learning_tasks.get(linked_learning_task_id)
            if isinstance(linked_learning_task, dict):
                current = dict(action)
                learning_status = str(linked_learning_task.get("status") or "needs_learning")
                current["learning_status"] = learning_status
                current["learning_task"] = {
                    "task_id": linked_learning_task_id,
                    "status": learning_status,
                    "next_validation_action": linked_learning_task.get("next_validation_action"),
                    "updated_at": linked_learning_task.get("updated_at"),
                    "issue_category": linked_learning_task.get("issue_category"),
                }
                if learning_status in {"validated_improved", "resolved"}:
                    current["status"] = "improved" if learning_status == "validated_improved" else "completed"
                    current["detail"] = "学习任务已形成可用结果，可继续沉淀为经验或策略"
                elif learning_status in {"ready_for_validation", "candidate_found", "validating"}:
                    current["status"] = "validating"
                    current["detail"] = linked_learning_task.get("next_validation_action") or "学习任务已进入验证阶段"
                elif learning_status == "awaiting_connector":
                    current["status"] = "blocked"
                    current["detail"] = linked_learning_task.get("next_validation_action") or "学习任务已具备候选方案，但还缺验证执行器"
                elif learning_status == "needs_input":
                    current["status"] = "blocked"
                    current["detail"] = linked_learning_task.get("next_validation_action") or "学习任务仍缺输入，暂时阻塞"
                else:
                    current["status"] = "needs_learning"
                    current["detail"] = linked_learning_task.get("next_validation_action") or "学习任务已创建，等待自治学习器继续推进"
                return current

        runtime_route = mission_run.get("runtime_route", {}) if isinstance(mission_run.get("runtime_route"), dict) else {}
        primary_worker_id = str(
            runtime_route.get("primary_worker_id")
            or mission_run.get("context", {}).get("runtime_primary_worker_id")
            or ""
        ).strip()
        post_action_handler = (
            mission_post_action_handlers.get(primary_worker_id)
            if isinstance(mission_post_action_handlers, dict)
            else None
        )
        if callable(post_action_handler):
            return post_action_handler(
                workspace=workspace,
                tenant_id=tenant_id,
                mission_run=mission_run,
                action=action,
                successful_task_actions=successful_task_actions,
                task_queue=task_queue,
                collect_task_verified_skills=collect_task_verified_skills,
                skill_ids_from_items=skill_ids_from_items,
                extract_task_snapshot=extract_task_snapshot,
                resolve_effective_growth_policy=resolve_effective_growth_policy,
                infer_framework_hint_from_delivery=infer_framework_hint_from_delivery,
                safe_float=safe_float,
                create_mission_delivery_skill_candidate=create_mission_delivery_skill_candidate,
                build_snapshot_signature=build_snapshot_signature,
                record_growth_event=record_growth_event,
                growth_policy_decision_label=growth_policy_decision_label,
                effective_platform_promotion_status=effective_platform_promotion_status,
            )
        return action

    def refresh_mission_run(
        *,
        workspace,
        task_queue,
        tenant_manager: TenantManager,
        mission_run: dict,
        build_mission_next_cycle_plan: Callable,
        build_mission_growth_timeline: Callable,
    ) -> dict:
        if not isinstance(mission_run, dict):
            return mission_run

        actions = mission_run.get("actions", [])
        if not isinstance(actions, list):
            actions = []

        learning_state = load_learning_tasks(workspace)
        learning_tasks = learning_state.get("tasks", {}) if isinstance(learning_state, dict) else {}
        learning_tasks = learning_tasks if isinstance(learning_tasks, dict) else {}
        submitted_task_ids = mission_run.get("submitted_task_ids", [])
        submitted_task_ids = submitted_task_ids if isinstance(submitted_task_ids, list) else []
        counts = {
            "submitted": 0,
            "needs_learning": 0,
            "needs_input": 0,
            "planned_only": 0,
            "success": 0,
            "failed": 0,
            "running": 0,
            "learning_validating": 0,
            "learning_improved": 0,
            "learning_regressed": 0,
            "learning_completed": 0,
        }

        goal = str(mission_run.get("goal") or "")
        tenant_id = str(mission_run.get("tenant_id") or "default")
        existing_failure_learning = {
            (
                str(item.get("node_id") or ""),
                str(item.get("task_id") or ""),
            )
            for item in actions
            if isinstance(item, dict) and item.get("action_type") == "failure_learning_ticket"
        }

        refreshed_actions: list[dict] = []
        successful_task_actions: list[dict] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            current = dict(action)
            action_type = str(current.get("action_type") or "")
            node_id = str(current.get("node_id") or "")
            task_id = str(current.get("task_id") or "")
            role_reflection_context = extract_node_role_reflection_context(mission_run, node_id)
            role_next_experiment = str(role_reflection_context.get("next_experiment") or "").strip()
            role_summary = str(role_reflection_context.get("summary") or "").strip()

            if task_id and action_type == "task_submitted":
                task = task_queue.get_task(task_id)
                if not task:
                    current["status"] = "submitted"
                    counts["submitted"] += 1
                    refreshed_actions.append(current)
                    continue

                task_status = str(task.status.value or "")
                if task_status == "completed":
                    current["status"] = "completed"
                    current["detail"] = trim_candidate_text(
                        (task.result or {}).get("summary") or current.get("detail") or f"{current.get('task_type') or 'task'} 已完成"
                    )
                    current["task_result"] = task.result if isinstance(task.result, dict) else {}
                    counts["success"] += 1
                    successful_task_actions.append(current)
                elif task_status == "failed":
                    current["status"] = "failed"
                    current["detail"] = trim_candidate_text(task.error or f"{current.get('task_type') or 'task'} 执行失败")
                    counts["failed"] += 1
                    failure_key = (node_id, task_id)
                    if failure_key not in existing_failure_learning:
                        learning_task_id = upsert_mission_failure_learning_task(
                            workspace=workspace,
                            tenant_manager=tenant_manager,
                            tenant_id=tenant_id,
                            mission_run=mission_run,
                            action=current,
                            failed_task=task,
                        )
                        refreshed_actions.append({
                            "node_id": node_id,
                            "title": current.get("title"),
                            "action_type": "failure_learning_ticket",
                            "status": "needs_learning",
                            "task_id": task_id,
                            "detail": (
                                f"执行失败，优先沿岗位最近实验继续复盘: {role_next_experiment}"
                                if role_next_experiment
                                else "执行失败，已标记为需要进入学习/复盘闭环"
                            ),
                            "linked_learning_task_id": learning_task_id,
                            "next_actions": [
                                *( [role_next_experiment] if role_next_experiment else [] ),
                                "优先分析失败任务的 error、signals 和输入路径",
                                "必要时对该节点生成针对性学习任务或复盘实验",
                                *( [f"参考岗位最近反思: {role_summary}"] if role_summary else [] ),
                            ],
                            "role_reflection_context": role_reflection_context,
                        })
                        existing_failure_learning.add(failure_key)
                elif task_status == "running":
                    current["status"] = "running"
                    counts["running"] += 1
                else:
                    current["status"] = "submitted"
                    counts["submitted"] += 1
                refreshed_actions.append(current)
                continue

            if action_type == "failure_learning_ticket":
                linked_learning_task_id = str(current.get("linked_learning_task_id") or "")
                linked_learning_task = (
                    learning_tasks.get(linked_learning_task_id)
                    if linked_learning_task_id and isinstance(learning_tasks.get(linked_learning_task_id), dict)
                    else None
                )
                if isinstance(linked_learning_task, dict):
                    learning_status = str(linked_learning_task.get("status") or "needs_learning")
                    current["learning_status"] = learning_status
                    current["learning_task"] = {
                        "task_id": linked_learning_task_id,
                        "status": learning_status,
                        "next_validation_action": linked_learning_task.get("next_validation_action"),
                        "auto_validation": linked_learning_task.get("auto_validation"),
                        "validation_result": linked_learning_task.get("validation_result"),
                        "updated_at": linked_learning_task.get("updated_at"),
                    }
                    if learning_status == "validating":
                        current["status"] = "validating"
                        current["detail"] = "失败样本已进入自动验证，正在等待重放/历史实验结果"
                        counts["learning_validating"] += 1
                    elif learning_status == "awaiting_connector":
                        current["status"] = "blocked"
                        current["detail"] = (
                            f"已有学习候选方案，优先回到岗位实验: {role_next_experiment}"
                            if role_next_experiment
                            else "已有学习候选方案，但当前工种还缺验证连接器或执行器"
                        )
                        counts["needs_learning"] += 1
                    elif learning_status == "validated_improved":
                        current["status"] = "improved"
                        current["detail"] = "失败样本已通过自动验证获得正向提升，可继续沉淀为经验/策略候选"
                        counts["learning_improved"] += 1
                        counts["learning_completed"] += 1
                    elif learning_status in {"validated_unchanged", "resolved"}:
                        current["status"] = "completed"
                        current["detail"] = "失败样本已完成验证闭环，当前结果稳定但尚未观察到明显提升"
                        counts["learning_completed"] += 1
                    elif learning_status in {"validated_regressed", "validated_mixed"}:
                        current["status"] = "regressed"
                        current["detail"] = "失败样本验证后仍存在退化或不稳定，需要继续学习和修正"
                        counts["learning_regressed"] += 1
                    else:
                        current["status"] = "needs_learning"
                        current["detail"] = (
                            linked_learning_task.get("next_validation_action")
                            or role_next_experiment
                            or "失败样本已建学习任务，等待进一步验证"
                        )
                        counts["needs_learning"] += 1
                    if role_reflection_context:
                        current["role_reflection_context"] = role_reflection_context
                else:
                    current["status"] = "needs_learning"
                    counts["needs_learning"] += 1

                refreshed_actions.append(current)
                continue

            if action_type == "learning_ticket":
                current = refresh_mission_learning_action(
                    workspace=workspace,
                    task_queue=task_queue,
                    tenant_id=tenant_id,
                    mission_run=mission_run,
                    action=current,
                    successful_task_actions=successful_task_actions,
                )
                refreshed_actions.append(current)
                if current.get("status") == "completed":
                    counts["learning_completed"] += 1
                elif current.get("status") == "improved":
                    counts["learning_improved"] += 1
                    counts["learning_completed"] += 1
                elif current.get("status") == "validating":
                    counts["learning_validating"] += 1
                elif current.get("status") == "regressed":
                    counts["learning_regressed"] += 1
                else:
                    counts["needs_learning"] += 1
                continue

            refreshed_actions.append(current)
            if action_type == "failure_learning_ticket":
                counts["needs_learning"] += 1
            elif action_type == "needs_input":
                counts["needs_input"] += 1
            elif action_type == "planned_only":
                counts["planned_only"] += 1

        mission_run["actions"] = refreshed_actions
        mission_run["counts"] = counts

        overall_status = "planning_only"
        if counts["learning_validating"]:
            overall_status = "validating"
        elif counts["learning_improved"] and (counts["needs_learning"] or counts["failed"] or counts["success"]):
            overall_status = "partially_completed"
        elif counts["learning_improved"]:
            overall_status = "improved"
        elif counts["success"] and counts["needs_learning"]:
            overall_status = "partially_completed"
        elif counts["needs_learning"]:
            overall_status = "needs_learning"
        elif counts["learning_regressed"]:
            overall_status = "regressed"
        elif counts["running"]:
            overall_status = "running"
        elif counts["submitted"]:
            overall_status = "submitted"
        elif counts["success"] and counts["needs_learning"] == 0 and counts["needs_input"] == 0:
            overall_status = "completed"
        elif counts["failed"]:
            overall_status = "needs_learning"
        elif counts["needs_input"]:
            overall_status = "blocked"
        elif counts["success"]:
            overall_status = "partially_completed"
        elif counts["learning_completed"]:
            overall_status = "completed"

        mission_run["status"] = overall_status
        mission_run["updated_at"] = datetime.now().isoformat()
        next_cycle_plan = build_mission_next_cycle_plan(mission_run, refreshed_actions)
        mission_growth_timeline = build_mission_growth_timeline(refreshed_actions)
        mission_run["summary"] = {
            "goal": goal,
            "submitted_task_ids": submitted_task_ids,
            "matched_verified_skill_ids": normalize_string_list(mission_run.get("matched_verified_skill_ids")),
            "work_type_id": (
                str(mission_run.get("work_type", {}).get("work_type_id") or "").strip()
                if isinstance(mission_run.get("work_type"), dict)
                else ""
            ),
            "work_type_title": (
                str(mission_run.get("work_type", {}).get("title") or "").strip()
                if isinstance(mission_run.get("work_type"), dict)
                else ""
            ),
            "work_type_validation": (
                mission_run.get("work_type_validation", {})
                if isinstance(mission_run.get("work_type_validation"), dict)
                else {}
            ),
            "delivery_targets": (
                mission_run.get("work_type_summary", {}).get("deliverables", [])
                if isinstance(mission_run.get("work_type_summary"), dict)
                else []
            ),
            "knowledge_policy": tenant_manager.get_knowledge_policy(tenant_id),
            "work_type_knowledge_policy": (
                mission_run.get("work_type_summary", {}).get("knowledge_policy", {})
                if isinstance(mission_run.get("work_type_summary"), dict)
                else {}
            ),
            "effective_growth_policy": resolve_effective_growth_policy(
                tenant_manager=tenant_manager,
                tenant_id=tenant_id,
                work_type_policy=(
                    mission_run.get("work_type_summary", {}).get("knowledge_policy", {})
                    if isinstance(mission_run.get("work_type_summary"), dict)
                    else {}
                ),
            ),
            "next_cycle_plan": next_cycle_plan,
            "growth_timeline": mission_growth_timeline,
        }
        runtime_route = mission_run.get("runtime_route", {}) if isinstance(mission_run.get("runtime_route"), dict) else {}
        primary_worker_id = str(
            runtime_route.get("primary_worker_id")
            or mission_run.get("context", {}).get("runtime_primary_worker_id")
            or ""
        ).strip()
        summary_handler = (
            mission_summary_handlers.get(primary_worker_id)
            if isinstance(mission_summary_handlers, dict)
            else None
        )
        if callable(summary_handler):
            mission_run["summary"]["worker_summary"] = summary_handler(
                mission_run=mission_run,
                refreshed_actions=refreshed_actions,
            )
            mission_run["summary"]["worker_summary_type"] = primary_worker_id
        return mission_run

    return {
        "build_mission_failure_sample": build_mission_failure_sample,
        "build_mission_failure_diagnosis": build_mission_failure_diagnosis,
        "upsert_mission_failure_learning_task": upsert_mission_failure_learning_task,
        "refresh_mission_learning_action": refresh_mission_learning_action,
        "refresh_mission_run": refresh_mission_run,
    }
