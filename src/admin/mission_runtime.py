"""
Mission 运行态持久化、续跑与启动组装。
"""

from admin.worker_route_runtime import worker_supports_mission_follow_up
import copy
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable


def mission_runs_file(workspace: Path) -> Path:
    path = workspace / ".admin" / "mission_runs.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def exclusive_mission_claim_lock(workspace: Path):
    """Serialize startup recovery and operator release across processes."""
    lock_path = workspace / ".admin" / ".mission-worker-claims.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_mission_runs_atomic(workspace: Path, payload: dict) -> None:
    path = mission_runs_file(workspace)
    normalized_items = payload.get("items", []) if isinstance(payload, dict) else []
    normalized_items = _retain_mission_runs(normalized_items) if isinstance(normalized_items, list) else []
    content = json.dumps({
        "updated_at": datetime.now().isoformat(),
        "items": normalized_items,
    }, indent=2, ensure_ascii=False)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_mission_runs_strict(workspace: Path) -> dict:
    """Read persisted Mission evidence without converting corruption into an empty history."""
    path = mission_runs_file(workspace)
    if not path.is_file():
        return {"updated_at": None, "items": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Mission runs store must contain a JSON object")
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("Mission runs store must contain an items array")
    if any(not isinstance(item, dict) for item in items):
        raise ValueError("Mission runs store contains a non-object run")
    return {
        "updated_at": data.get("updated_at"),
        "items": items,
    }


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


def _mission_run_has_active_worker_claim(mission_run: dict) -> bool:
    """Keep runs that are the only durable evidence for a live worker reservation."""
    actions = mission_run.get("actions", []) if isinstance(mission_run.get("actions"), list) else []
    return any(
        isinstance(action, dict)
        and isinstance(action.get("worker_claim"), dict)
        and action["worker_claim"].get("state") == "claimed"
        for action in actions
    )


def _retain_mission_runs(items: list, limit: int = 50) -> list[dict]:
    """Bound history without evicting runs that still own worker claims."""
    valid = [item for item in items if isinstance(item, dict)]
    retained_indexes = set(range(min(max(0, limit), len(valid))))
    retained_indexes.update(
        index for index, item in enumerate(valid)
        if _mission_run_has_active_worker_claim(item)
    )
    result = []
    seen_ids = set()
    for index, item in enumerate(valid):
        if index not in retained_indexes:
            continue
        run_id = str(item.get("mission_run_id") or "").strip()
        if run_id:
            if run_id in seen_ids:
                continue
            seen_ids.add(run_id)
        result.append(item)
    return result


def save_mission_runs(workspace: Path, payload: dict) -> None:
    _write_mission_runs_atomic(workspace, payload)


def reconcile_worker_claims_on_startup(*, workspace: Path, task_queue, organization_registry) -> dict:
    with exclusive_mission_claim_lock(workspace):
        return _reconcile_worker_claims_on_startup_locked(
            workspace=workspace,
            task_queue=task_queue,
            organization_registry=organization_registry,
        )


def _reconcile_worker_claims_on_startup_locked(*, workspace: Path, task_queue, organization_registry) -> dict:
    """Recover only durable worker claims; never refresh plans or dispatch new work."""
    state = load_mission_runs(workspace)
    items = state.get("items", []) if isinstance(state, dict) else []
    groups: dict[str, dict] = {}
    checked = 0
    held = 0
    released = 0
    changed = False
    for run in items:
        if not isinstance(run, dict):
            continue
        actions = run.get("actions", []) if isinstance(run.get("actions"), list) else []
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                continue
            claim = action.get("worker_claim")
            if not isinstance(claim, dict) or claim.get("state") != "claimed":
                continue
            claim_id = str(claim.get("claim_id") or "").strip()
            worker_id = str(claim.get("worker_id") or "").strip()
            task_id = str(action.get("task_id") or "").strip()
            if not claim_id or not worker_id or not task_id:
                claim["recovery_status"] = "needs_review"
                claim["recovery_reason"] = "claim_or_task_identity_missing"
                claim["recovery_checked_at"] = datetime.now().astimezone().isoformat()
                held += 1
                changed = True
                if claim_id:
                    group = groups.setdefault(claim_id, {
                        "worker_id": worker_id,
                        "task_ids": set(),
                        "actions": [],
                    })
                    group["identity_conflict"] = True
                    group["actions"].append(action)
                continue
            group = groups.setdefault(claim_id, {
                "worker_id": worker_id,
                "task_ids": set(),
                "actions": [],
            })
            if group["worker_id"] != worker_id:
                group["identity_conflict"] = True
            group["task_ids"].add(task_id)
            group["actions"].append(action)

    for claim_id, group in groups.items():
        checked += 1
        reason = None
        if group.get("identity_conflict"):
            reason = "worker_identity_conflict"
        else:
            for task_id in sorted(group["task_ids"]):
                try:
                    task = task_queue.get_task(task_id)
                except Exception:
                    reason = "queue_lookup_failed"
                    break
                if task is None:
                    reason = "queue_task_missing"
                    break
                status = str(getattr(getattr(task, "status", None), "value", "") or "")
                if status not in {"success", "completed", "failed", "cancelled"}:
                    reason = "queue_task_not_terminal"
                    break
        if reason:
            for action in group["actions"]:
                claim = action["worker_claim"]
                claim["recovery_status"] = "needs_review"
                claim["recovery_reason"] = reason
                claim["recovery_checked_at"] = datetime.now().astimezone().isoformat()
            held += 1
            changed = True
            continue
        try:
            organization_registry.release_worker_task(
                worker_id=group["worker_id"],
                task_id=claim_id,
            )
        except Exception as exc:
            for action in group["actions"]:
                claim = action["worker_claim"]
                claim["recovery_status"] = "needs_review"
                claim["recovery_reason"] = "worker_release_failed"
                claim["release_error_type"] = type(exc).__name__
                claim["recovery_checked_at"] = datetime.now().astimezone().isoformat()
            held += 1
            changed = True
            continue
        released_at = datetime.now().astimezone().isoformat()
        for action in group["actions"]:
            claim = action["worker_claim"]
            claim["state"] = "released"
            claim["released_at"] = released_at
            claim["recovery_status"] = "recovered"
            claim["recovery_reason"] = None
            claim["recovery_checked_at"] = released_at
        released += 1
        changed = True

    if changed:
        save_mission_runs(workspace, {"items": items})
    return {
        "mission_runs": len([item for item in items if isinstance(item, dict)]),
        "claims_checked": checked,
        "claims_released": released,
        "claims_held_for_review": held,
    }


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
                if isinstance(error, dict):
                    detail = str(error.get("error") or error.get("message") or "").strip()
                else:
                    detail = str(error or "").strip()
                if detail:
                    current["auto_continue_error_detail"] = detail[:500]
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
    save_mission_runs(workspace, {"items": refreshed_items})
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
        if not isinstance(context, dict):
            context = {}
        prepared_route = prepared.get("runtime_route", {})
        if isinstance(prepared_route, dict):
            route_worker_id = str(prepared_route.get("primary_worker_id") or "").strip()
            if route_worker_id:
                context.setdefault("runtime_primary_worker_id", route_worker_id)
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
        save_mission_runs(workspace, {"items": items})
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


def _append_worker_claim_recovery_audit(workspace: Path, event: dict) -> None:
    path = workspace / ".admin" / "worker_claim_recovery_audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def release_worker_claim_for_review(
    *,
    workspace: Path,
    mission_run_id: str,
    tenant_id: str,
    claim_id: str,
    actor: dict,
    reason: str,
    task_queue,
    organization_registry,
) -> dict:
    """Release a reviewed claim using a durable intent-before-side-effect sequence."""
    from datetime import timezone

    now = lambda: datetime.now(timezone.utc).isoformat()
    with exclusive_mission_claim_lock(workspace):
        state = load_mission_runs_strict(workspace)
        items = state["items"]
        selected_run = next((
            item for item in items
            if str(item.get("mission_run_id") or "") == str(mission_run_id or "")
        ), None)
        if not isinstance(selected_run, dict):
            raise KeyError("mission_run_not_found")
        if str(selected_run.get("tenant_id") or "default") != str(tenant_id):
            raise PermissionError("mission_run_tenant_mismatch")

        matches = []
        for run in items:
            for action in run.get("actions", []) if isinstance(run.get("actions"), list) else []:
                claim = action.get("worker_claim") if isinstance(action, dict) else None
                if isinstance(claim, dict) and str(claim.get("claim_id") or "") == str(claim_id):
                    matches.append((run, action, claim))
        if not matches:
            raise KeyError("worker_claim_not_found")

        worker_ids = {str(claim.get("worker_id") or "").strip() for _, _, claim in matches}
        tenant_ids = {str(run.get("tenant_id") or "default") for run, _, _ in matches}
        if len(worker_ids) != 1 or not next(iter(worker_ids)):
            raise ValueError("worker_claim_identity_conflict")
        if tenant_ids != {str(tenant_id)}:
            raise PermissionError("worker_claim_tenant_mismatch")
        if not any(run is selected_run for run, _, _ in matches):
            raise ValueError("worker_claim_not_attached_to_selected_run")
        if any(claim.get("state") != "claimed" or claim.get("recovery_status") != "needs_review"
               for _, _, claim in matches):
            raise ValueError("worker_claim_not_pending_review")

        worker_id = next(iter(worker_ids))
        task_ids = sorted({str(action.get("task_id") or "").strip() for _, action, _ in matches})
        if not task_ids or any(not task_id for task_id in task_ids):
            raise ValueError("worker_claim_task_identity_missing")
        for task_id in task_ids:
            task = task_queue.get_task(task_id)
            if task is None:
                raise ValueError("worker_claim_task_missing")
            status_value = getattr(getattr(task, "status", None), "value", None)
            status = str(status_value or getattr(task, "status", "") or "")
            if status not in {"success", "completed", "failed", "cancelled"}:
                raise ValueError("worker_claim_task_not_terminal")

        worker = organization_registry.get_worker(worker_id)
        if not isinstance(worker, dict):
            raise ValueError("worker_registry_entry_missing")
        active = worker.get("active_task_ids")
        released = worker.get("released_task_ids")
        if not isinstance(active, list) or not isinstance(released, list):
            raise ValueError("worker_registry_claim_state_invalid")
        if claim_id in active and claim_id in released:
            raise ValueError("worker_registry_claim_state_conflict")
        already_released = claim_id in released and claim_id not in active
        if not already_released and claim_id not in active:
            raise ValueError("worker_registry_claim_mismatch")

        actor_provider = str(actor.get("auth_provider") or "")
        actor_id = str(actor.get("id") or "")
        event_base = {
            "timestamp": now(),
            "tenant_id": tenant_id,
            "mission_run_id": mission_run_id,
            "claim_id": claim_id,
            "worker_id": worker_id,
            "task_ids": task_ids,
            "reason": reason,
            "actor_provider": actor_provider,
            "actor_id": actor_id,
            "before": {"mission_claim_state": "claimed", "worker_active_task_ids": list(active)},
        }
        _append_worker_claim_recovery_audit(
            workspace,
            {**event_base, "event": "release_requested", "after": None},
        )

        requested_at = now()
        for _, _, claim in matches:
            claim["release_operation"] = {
                "status": "requested",
                "reason": reason,
                "requested_at": requested_at,
                "actor_provider": actor_provider,
                "actor_id": actor_id,
            }
        save_mission_runs(workspace, {"items": items})

        if not already_released:
            organization_registry.release_worker_task(worker_id=worker_id, task_id=claim_id)

        released_at = now()
        for _, _, claim in matches:
            claim["state"] = "released"
            claim["released_at"] = released_at
            claim["recovery_status"] = "manually_released"
            claim["recovery_reason"] = "tenant_admin_manual_release"
            claim["recovery_checked_at"] = released_at
            claim["release_operation"]["status"] = "applied"
            claim["release_operation"]["applied_at"] = released_at
        save_mission_runs(workspace, {"items": items})

        final_worker = organization_registry.get_worker(worker_id)
        _append_worker_claim_recovery_audit(
            workspace,
            {
                **event_base,
                "timestamp": released_at,
                "event": "release_applied",
                "after": {
                    "mission_claim_state": "released",
                    "worker_status": final_worker.get("status") if isinstance(final_worker, dict) else None,
                    "worker_active_task_ids": final_worker.get("active_task_ids") if isinstance(final_worker, dict) else None,
                },
            },
        )
        return {
            "mission_run_id": mission_run_id,
            "claim_id": claim_id,
            "worker_id": worker_id,
            "task_ids": task_ids,
            "state": "released",
            "already_released_in_registry": already_released,
        }
