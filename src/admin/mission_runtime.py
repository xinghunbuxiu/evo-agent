"""
Mission 运行态持久化、续跑与启动组装。
"""

from admin.worker_route_runtime import worker_supports_mission_follow_up
import json
from datetime import datetime
from pathlib import Path
from typing import Callable


def mission_runs_file(workspace: Path) -> Path:
    path = workspace / ".admin" / "mission_runs.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_mission_runs(workspace: Path) -> dict:
    path = mission_runs_file(workspace)
    if not path.is_file():
        return {"updated_at": None, "items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    items = data.get("items", []) if isinstance(data, dict) else []
    return {
        "updated_at": data.get("updated_at") if isinstance(data, dict) else None,
        "items": items if isinstance(items, list) else [],
    }


def save_mission_runs(workspace: Path, payload: dict) -> None:
    normalized_items = payload.get("items", []) if isinstance(payload, dict) else []
    mission_runs_file(workspace).write_text(
        json.dumps({
            "updated_at": datetime.now().isoformat(),
            "items": normalized_items if isinstance(normalized_items, list) else [],
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def find_mission_run(workspace: Path, mission_run_id: str) -> dict | None:
    state = load_mission_runs(workspace)
    items = state.get("items", []) if isinstance(state, dict) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("mission_run_id") or "") == str(mission_run_id or ""):
            return item
    return None


def derive_follow_up_analytics_types(mission_run: dict) -> list[str]:
    actions = mission_run.get("actions", []) if isinstance(mission_run.get("actions"), list) else []
    completed_types: list[str] = []
    for item in actions:
        if not isinstance(item, dict):
            continue
        result = item.get("task_result", {}) if isinstance(item.get("task_result"), dict) else {}
        analytics_type = str(result.get("analytics_type") or "").strip().lower()
        if analytics_type and analytics_type not in completed_types:
            completed_types.append(analytics_type)
    preferred_order = ["fans", "works", "income"]
    remaining = [item for item in preferred_order if item not in completed_types]
    return remaining or preferred_order


def derive_follow_up_goal(mission_run: dict) -> str:
    summary = mission_run.get("summary", {}) if isinstance(mission_run.get("summary"), dict) else {}
    next_cycle_plan = summary.get("next_cycle_plan", {}) if isinstance(summary.get("next_cycle_plan"), dict) else {}
    goal = str(mission_run.get("goal") or "").strip()
    focus_points = [
        str(item).strip()
        for item in (next_cycle_plan.get("focus_points", []) if isinstance(next_cycle_plan.get("focus_points"), list) else [])
        if str(item).strip()
    ]
    next_steps = [
        str(item).strip()
        for item in (next_cycle_plan.get("next_steps", []) if isinstance(next_cycle_plan.get("next_steps"), list) else [])
        if str(item).strip()
    ]
    role_reflection_experiments = [
        str(item).strip()
        for item in (next_cycle_plan.get("role_reflection_experiments", []) if isinstance(next_cycle_plan.get("role_reflection_experiments"), list) else [])
        if str(item).strip()
    ]
    role_reflection_summaries = [
        str(item).strip()
        for item in (next_cycle_plan.get("role_reflection_summaries", []) if isinstance(next_cycle_plan.get("role_reflection_summaries"), list) else [])
        if str(item).strip()
    ]
    if not focus_points and not next_steps:
        return goal
    parts = [goal] if goal else []
    if role_reflection_summaries:
        parts.append("岗位延续：" + "；".join(role_reflection_summaries[:1]))
    if focus_points:
        parts.append("当前关注：" + "；".join(focus_points[:2]))
    if role_reflection_experiments:
        parts.append("岗位实验：" + "；".join(role_reflection_experiments[:2]))
    if next_steps:
        parts.append("下一步：" + "；".join(next_steps[:3]))
    return " | ".join(parts)


def derive_follow_up_context(mission_run: dict) -> dict:
    context = copy.deepcopy(mission_run.get("context", {}) if isinstance(mission_run.get("context"), dict) else {})
    summary = mission_run.get("summary", {}) if isinstance(mission_run.get("summary"), dict) else {}
    next_cycle_plan = summary.get("next_cycle_plan", {}) if isinstance(summary.get("next_cycle_plan"), dict) else {}
    next_steps = [
        str(item).strip()
        for item in (next_cycle_plan.get("next_steps", []) if isinstance(next_cycle_plan.get("next_steps"), list) else [])
        if str(item).strip()
    ]
    focus_points = [
        str(item).strip()
        for item in (next_cycle_plan.get("focus_points", []) if isinstance(next_cycle_plan.get("focus_points"), list) else [])
        if str(item).strip()
    ]
    role_reflection_experiments = [
        str(item).strip()
        for item in (next_cycle_plan.get("role_reflection_experiments", []) if isinstance(next_cycle_plan.get("role_reflection_experiments"), list) else [])
        if str(item).strip()
    ]
    role_reflection_summaries = [
        str(item).strip()
        for item in (next_cycle_plan.get("role_reflection_summaries", []) if isinstance(next_cycle_plan.get("role_reflection_summaries"), list) else [])
        if str(item).strip()
    ]
    preferred_content_mode = str(next_cycle_plan.get("preferred_content_mode") or "").strip()
    feedback_goal_hint = str(next_cycle_plan.get("feedback_goal_hint") or "").strip()
    context["previous_mission_run_id"] = mission_run.get("mission_run_id")
    context["autonomy_session_id"] = (
        mission_run.get("autonomy_session_id")
        or context.get("autonomy_session_id")
        or mission_run.get("mission_run_id")
    )
    context["root_mission_run_id"] = (
        mission_run.get("root_mission_run_id")
        or context.get("root_mission_run_id")
        or mission_run.get("mission_run_id")
    )
    context["autonomy_cycle"] = int(context.get("autonomy_cycle") or 0) + 1
    if next_steps:
        context["deliverable_goal"] = "；".join(next_steps[:3])
    if focus_points:
        context["goal_hint"] = "；".join(focus_points[:2])
    if role_reflection_experiments:
        context["role_reflection_experiment"] = role_reflection_experiments[0]
    if role_reflection_summaries:
        context["role_reflection_summary"] = role_reflection_summaries[0]
    if role_reflection_summaries or role_reflection_experiments:
        context["role_reflection_context"] = {
            "summary": role_reflection_summaries[0] if role_reflection_summaries else "",
            "next_experiment": role_reflection_experiments[0] if role_reflection_experiments else "",
            "all_summaries": role_reflection_summaries[:3],
            "all_experiments": role_reflection_experiments[:3],
        }
    runtime_route = mission_run.get("runtime_route", {}) if isinstance(mission_run.get("runtime_route"), dict) else {}
    primary_worker_id = str(
        runtime_route.get("primary_worker_id")
        or context.get("runtime_primary_worker_id")
        or ""
    ).strip()
    if worker_supports_mission_follow_up(runtime_route, primary_worker_id):
        context["analytics_types"] = derive_follow_up_analytics_types(mission_run)
        context["draft_content"] = ""
        context["auto_publish_draft"] = False
        if preferred_content_mode:
            context["content_mode"] = preferred_content_mode
        if feedback_goal_hint:
            context["feedback_goal_hint"] = feedback_goal_hint
        elif next_steps:
            context["feedback_goal_hint"] = "；".join(next_steps[:2])
    return context


def should_auto_continue_mission(mission_run: dict) -> bool:
    if not isinstance(mission_run, dict):
        return False
    summary = mission_run.get("summary", {}) if isinstance(mission_run.get("summary"), dict) else {}
    next_cycle_plan = summary.get("next_cycle_plan", {}) if isinstance(summary.get("next_cycle_plan"), dict) else {}
    if str(next_cycle_plan.get("status") or "") != "ready":
        return False
    status = str(mission_run.get("status") or "")
    if status not in {"completed", "partially_completed", "improved"}:
        return False
    context = mission_run.get("context", {}) if isinstance(mission_run.get("context"), dict) else {}
    if not bool(context.get("auto_continue")):
        return False
    if mission_run.get("auto_continue_source_mission_run_id"):
        return False
    if mission_run.get("auto_continue_triggered_run_id"):
        return False
    cycle = int(context.get("autonomy_cycle") or 0)
    max_cycles = int(context.get("max_autonomy_cycles") or 3)
    return cycle < max(1, max_cycles)


def build_mission_session_summary(current_run: dict, all_runs: list[dict]) -> dict:
    session_id = str(current_run.get("autonomy_session_id") or "").strip()
    if not session_id:
        return {}
    related = [
        item for item in all_runs
        if isinstance(item, dict) and str(item.get("autonomy_session_id") or "").strip() == session_id
    ]
    related.sort(key=lambda item: str(item.get("created_at") or ""))
    current_run_id = str(current_run.get("mission_run_id") or "")
    current_index = next((
        index + 1
        for index, item in enumerate(related)
        if str(item.get("mission_run_id") or "") == current_run_id
    ), len(related))
    return {
        "autonomy_session_id": session_id,
        "run_index": current_index,
        "run_count": len(related),
        "root_mission_run_id": current_run.get("root_mission_run_id"),
        "latest_mission_run_id": related[-1].get("mission_run_id") if related else current_run_id,
    }


def refresh_mission_runs(
    *,
    workspace: Path,
    task_queue,
    tenant_manager,
    refresh_runtime_learning_tasks: Callable[..., dict],
    refresh_mission_run: Callable[..., dict],
    mission_starter=None,
    sync_autonomy_runtime_from_missions: Callable[..., list[dict] | None] | None = None,
) -> dict:
    refresh_runtime_learning_tasks(
        workspace=workspace,
        tenant_manager=tenant_manager,
        task_queue=task_queue,
    )
    state = load_mission_runs(workspace)
    items = state.get("items", []) if isinstance(state, dict) else []
    refreshed_items = [
        refresh_mission_run(
            workspace=workspace,
            task_queue=task_queue,
            tenant_manager=tenant_manager,
            mission_run=item,
        )
        for item in items
        if isinstance(item, dict)
    ]

    if callable(mission_starter):
        for current in refreshed_items:
            if not should_auto_continue_mission(current):
                continue
            payload = {
                "tenant_id": current.get("tenant_id") or "default",
                "work_type_id": (
                    current.get("work_type", {}).get("work_type_id")
                    if isinstance(current.get("work_type"), dict)
                    else None
                ),
                "mission_kind": current.get("mission_kind"),
                "goal": derive_follow_up_goal(current),
                "context": derive_follow_up_context(current),
            }
            latest, error = mission_starter(payload, refresh_runs=False)
            if error is not None or not isinstance(latest, dict):
                current["auto_continue_status"] = "failed"
                current["auto_continue_error"] = "自动续跑启动失败"
                continue
            current["auto_continue_triggered_at"] = datetime.now().isoformat()
            current["auto_continue_triggered_run_id"] = latest.get("mission_run_id")
            current["auto_continue_status"] = "triggered"
            latest["auto_continue_source_mission_run_id"] = current.get("mission_run_id")
            refreshed_items.insert(0, latest)
            break

    for current in refreshed_items:
        if not isinstance(current, dict):
            continue
        summary = current.get("summary", {}) if isinstance(current.get("summary"), dict) else {}
        summary["session"] = build_mission_session_summary(current, refreshed_items)
        current["summary"] = summary
    if callable(sync_autonomy_runtime_from_missions):
        synced = sync_autonomy_runtime_from_missions(
            workspace=workspace,
            mission_runs=refreshed_items,
        )
        if isinstance(synced, list):
            refreshed_items = [item for item in synced if isinstance(item, dict)]
    save_mission_runs(workspace, {"items": refreshed_items[:50]})
    return load_mission_runs(workspace)


def create_start_mission(
    *,
    workspace: Path,
    task_queue,
    tenant_manager,
    prepare_mission_work_type_bundle: Callable[..., dict],
    mission_planner,
    upsert_plan_learning_tasks: Callable[..., list[str]],
    build_mission_run: Callable[..., dict],
    refresh_mission_runs_fn: Callable[..., dict],
    error_response: Callable[[str, int], object],
    resolve_mission_member_context: Callable[..., dict] | None = None,
):
    def start_mission(data: dict, *, refresh_runs: bool = True):
        goal = str(data.get("goal") or "").strip()
        work_type_id = str(data.get("work_type_id") or "").strip() or None
        tenant_id = str(data.get("tenant_id") or "default").strip() or "default"
        mission_kind = str(data.get("mission_kind") or "").strip() or None
        context = data.get("context", {})
        if not isinstance(context, dict):
            context = {}
        if callable(resolve_mission_member_context):
            resolved_member_context = resolve_mission_member_context(
                tenant_id=tenant_id,
                work_type_id=work_type_id,
                mission_kind=mission_kind,
                context=context,
            )
            if isinstance(resolved_member_context, dict):
                merged_context = dict(context)
                for key, value in resolved_member_context.items():
                    if merged_context.get(key) in {None, "", []} and value not in {None, "", []}:
                        merged_context[key] = value
                context = merged_context
        prepared = prepare_mission_work_type_bundle(
            workspace=workspace,
            work_type_id=work_type_id,
            goal=goal,
            mission_kind=mission_kind,
            context=context,
        )
        goal = str(prepared.get("goal") or "").strip()
        mission_kind = prepared.get("mission_kind")
        context = prepared.get("context", {})
        validation = prepared.get("work_type_validation", {})
        if not goal:
            return None, error_response("goal 不能为空", 400)
        context.setdefault("work_type_validation", validation)

        plan = mission_planner.plan(
            tenant_id=tenant_id,
            goal=goal,
            mission_kind=mission_kind,
            context=context,
        )
        if prepared.get("work_type"):
            plan["work_type"] = prepared["work_type"]
            plan["work_type_summary"] = prepared.get("work_type_summary")
            plan["work_type_validation"] = validation
            plan["runtime_route"] = prepared.get("runtime_route")
        learning_task_ids = upsert_plan_learning_tasks(
            workspace=workspace,
            tenant_id=tenant_id,
            mission_kind=str(mission_kind or ""),
            goal=goal,
            context=context,
            plan=plan,
        )
        plan["learning_task_ids"] = learning_task_ids
        mission_run = build_mission_run(
            workspace=workspace,
            task_queue=task_queue,
            tenant_id=tenant_id,
            plan=plan,
            context=context,
        )
        state = load_mission_runs(workspace)
        items = state.get("items", []) if isinstance(state, dict) else []
        items = [item for item in items if isinstance(item, dict)]
        items.insert(0, mission_run)
        save_mission_runs(workspace, {"items": items[:50]})
        if refresh_runs:
            refreshed = refresh_mission_runs_fn(
                workspace=workspace,
                task_queue=task_queue,
                tenant_manager=tenant_manager,
                mission_starter=start_mission,
            )
            latest_items = refreshed.get("items", []) if isinstance(refreshed, dict) else []
            latest = latest_items[0] if latest_items else mission_run
        else:
            latest = mission_run
        return latest, None

    return start_mission
