"""
Mission 规划、执行与续跑接口。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import Request

from admin.mission_runtime import load_mission_runs, load_mission_runs_strict


def register_mission_routes(
    app,
    *,
    workspace: Path,
    task_queue,
    tenant_manager,
    prepare_mission_work_type_bundle: Callable[..., dict],
    mission_planner,
    upsert_plan_learning_tasks: Callable[..., list[str]],
    refresh_mission_runs: Callable[..., dict],
    start_mission: Callable[..., tuple[dict | None, object | None]],
    find_mission_run: Callable[[Path, str], dict | None],
    derive_follow_up_goal: Callable[[dict], str],
    derive_follow_up_context: Callable[[dict], dict],
    success_response: Callable[[dict | None, str], dict],
    error_response: Callable[[str, int], object],
    get_session_user: Callable[[Request], dict | None],
    authorize_tenant: Callable[[dict, str], bool],
) -> None:
    @app.post("/api/missions/plan")
    async def plan_mission(request: Request):
        data = await request.json()
        goal = str(data.get("goal") or "").strip()
        work_type_id = str(data.get("work_type_id") or "").strip() or None
        tenant_id = str(data.get("tenant_id") or "default").strip() or "default"
        mission_kind = str(data.get("mission_kind") or "").strip() or None
        context = data.get("context", {})
        if not isinstance(context, dict):
            context = {}
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
            return error_response("goal 不能为空", 400)
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
        return success_response(plan, "Mission 规划已生成")

    @app.get("/api/missions/runs")
    async def list_mission_runs(tenant_id: str | None = None, limit: int = 20):
        state = refresh_mission_runs(
            workspace=workspace,
            task_queue=task_queue,
            tenant_manager=tenant_manager,
            mission_starter=start_mission,
        )
        items = state.get("items", []) if isinstance(state, dict) else []
        filtered = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if tenant_id and item.get("tenant_id") != tenant_id:
                continue
            filtered.append(item)
            if len(filtered) >= max(1, min(limit, 100)):
                break
        return success_response({
            "updated_at": state.get("updated_at"),
            "items": filtered,
        })

    @app.get("/api/missions/worker-claims/recovery-review")
    async def list_worker_claims_for_recovery_review(request: Request, tenant_id: str | None = None, limit: int = 100):
        user = get_session_user(request)
        if not user:
            return error_response("未登录", 401)
        if not tenant_id or not str(tenant_id).strip():
            return error_response("必须指定 tenant_id", 400)
        if not authorize_tenant(user, tenant_id):
            return error_response("无权访问该租户", 403)

        # Read persisted evidence directly: do not refresh missions or trigger dispatch here.
        # Corrupt/incomplete storage must not masquerade as an empty review queue.
        try:
            state = load_mission_runs_strict(workspace)
        except (OSError, UnicodeError, ValueError) as exc:
            return error_response(f"Mission 复核数据读取失败: {type(exc).__name__}", 500)
        items = state["items"]
        reviews = []
        for mission_run in items:
            if not isinstance(mission_run, dict):
                continue
            if tenant_id and mission_run.get("tenant_id") != tenant_id:
                continue
            actions = mission_run.get("actions", [])
            if not isinstance(actions, list):
                continue
            for action in actions:
                if not isinstance(action, dict):
                    continue
                claim = action.get("worker_claim")
                if not isinstance(claim, dict):
                    continue
                if claim.get("state") != "claimed" or claim.get("recovery_status") != "needs_review":
                    continue
                reviews.append({
                    "mission_run_id": mission_run.get("mission_run_id"),
                    "tenant_id": mission_run.get("tenant_id") or "default",
                    "goal": mission_run.get("goal"),
                    "node_id": action.get("node_id"),
                    "action_title": action.get("title"),
                    "task_id": action.get("task_id"),
                    "worker_claim": {
                        "claim_id": claim.get("claim_id"),
                        "worker_id": claim.get("worker_id"),
                        "state": claim.get("state"),
                        "recovery_status": claim.get("recovery_status"),
                        "recovery_reason": claim.get("recovery_reason"),
                        "recovery_checked_at": claim.get("recovery_checked_at"),
                        "release_error_type": claim.get("release_error_type"),
                    },
                })
                if len(reviews) >= max(1, min(limit, 500)):
                    return success_response({
                        "count": len(reviews),
                        "items": reviews,
                    }, "待人工复核的 Worker Claim")
        return success_response({
            "count": len(reviews),
            "items": reviews,
        }, "待人工复核的 Worker Claim")

    @app.get("/api/missions/{mission_run_id}")
    async def get_mission_run(mission_run_id: str):
        state = refresh_mission_runs(
            workspace=workspace,
            task_queue=task_queue,
            tenant_manager=tenant_manager,
            mission_starter=start_mission,
        )
        items = state.get("items", []) if isinstance(state, dict) else []
        current = next((
            item for item in items
            if isinstance(item, dict) and str(item.get("mission_run_id") or "") == str(mission_run_id or "")
        ), None)
        if not isinstance(current, dict):
            current = find_mission_run(workspace, mission_run_id)
        if not isinstance(current, dict):
            return error_response("未找到对应的 mission run", 404)
        return success_response(current)

    @app.post("/api/missions/execute")
    async def execute_mission(request: Request):
        data = await request.json()
        latest, error = start_mission(data if isinstance(data, dict) else {})
        if error:
            return error
        return success_response(latest, "Mission 已开始推进")

    @app.post("/api/missions/{mission_run_id}/continue")
    async def continue_mission(mission_run_id: str):
        state = refresh_mission_runs(
            workspace=workspace,
            task_queue=task_queue,
            tenant_manager=tenant_manager,
            mission_starter=start_mission,
        )
        items = state.get("items", []) if isinstance(state, dict) else []
        current = next((
            item for item in items
            if isinstance(item, dict) and str(item.get("mission_run_id") or "") == str(mission_run_id or "")
        ), None)
        if not isinstance(current, dict):
            current = find_mission_run(workspace, mission_run_id)
        if not isinstance(current, dict):
            return error_response("未找到对应的 mission run", 404)

        next_cycle_plan = (
            current.get("summary", {}).get("next_cycle_plan", {})
            if isinstance(current.get("summary"), dict)
            else {}
        )
        if str(next_cycle_plan.get("status") or "") != "ready":
            return error_response("当前 mission 尚未生成可继续推进的下一轮计划", 400)

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
        latest, error = start_mission(payload)
        if error:
            return error
        return success_response({
            "source_mission_run_id": mission_run_id,
            "continued_mission_run": latest,
        }, "已基于上一轮结果启动下一轮 Mission")
