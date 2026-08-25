"""
财务 M1 API：项目经营摘要与手工成本录入。
"""

from __future__ import annotations

from typing import Callable

from fastapi import Request

from admin.finance_runtime import (
    empty_finance_summary,
    get_finance_overview,
    get_finance_summary,
    list_finance_projects,
    purge_preset_finance_data,
    record_finance_decision,
    upsert_finance_period,
)
from admin.commercial_runtime import get_commercial_readiness


def register_finance_routes(
    app,
    *,
    workspace,
    success_response: Callable[[dict | None, str], dict],
    error_response: Callable[[str, int], object],
) -> None:
    @app.get("/api/finance/overview")
    async def finance_overview(request: Request):
        period = str(request.query_params.get("period") or "").strip() or None
        overview = get_finance_overview(workspace, period=period)
        return success_response(overview, "ok")

    @app.get("/api/finance/summary")
    async def finance_summary(request: Request):
        project_id = str(request.query_params.get("project_id") or "").strip()
        period = str(request.query_params.get("period") or "").strip() or None
        if not project_id:
            overview = get_finance_overview(workspace, period=period)
            return success_response(overview.get("primary") or empty_finance_summary(), "ok")
        summary = get_finance_summary(workspace, project_id=project_id, period=period)
        return success_response(summary, "ok")

    @app.get("/api/finance/projects")
    async def finance_projects():
        items = list_finance_projects(workspace)
        return success_response({"items": items, "total": len(items)}, "ok")

    @app.post("/api/finance/purge-preset")
    async def finance_purge_preset():
        removed = purge_preset_finance_data(workspace)
        return success_response({"removed": removed, "total": len(removed)}, "preset finance data purged")

    @app.put("/api/finance/cost")
    async def finance_update_cost(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return error_response("invalid body", 400)
        project_id = str(body.get("project_id") or "").strip()
        if not project_id:
            return error_response("project_id is required", 400)
        period = str(body.get("period") or "").strip() or None
        cost = body.get("cost")
        try:
            cost_value = float(cost)
        except (TypeError, ValueError):
            return error_response("cost must be a number", 400)
        channel = str(body.get("channel") or "toutiao").strip() or "toutiao"
        summary = upsert_finance_period(
            workspace,
            project_id=project_id,
            period=period,
            channel=channel,
            patch={
                "cost": cost_value,
                "source": "manual_cost_entry",
            },
        )
        return success_response(summary, "cost updated")

    @app.post("/api/finance/decision")
    async def finance_record_decision(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return error_response("invalid body", 400)
        project_id = str(body.get("project_id") or "").strip()
        action = str(body.get("action") or "").strip()
        note = str(body.get("note") or "").strip()
        period = str(body.get("period") or "").strip() or None
        if not project_id:
            return error_response("project_id is required", 400)
        if not action:
            return error_response("action is required", 400)
        try:
            entry = record_finance_decision(
                workspace,
                project_id=project_id,
                action=action,
                note=note,
                period=period,
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        return success_response(entry, "finance decision recorded")

    @app.get("/api/commercial/readiness")
    async def commercial_readiness(request: Request):
        tenant_id = str(request.query_params.get("tenant_id") or "default").strip() or "default"
        payload = get_commercial_readiness(workspace, tenant_id=tenant_id)
        return success_response(payload, "ok")

    @app.get("/api/commercial/weekly-briefing")
    async def commercial_weekly_briefing(request: Request):
        from admin.commercial_runtime import build_weekly_briefing

        tenant_id = str(request.query_params.get("tenant_id") or "default").strip() or "default"
        payload = build_weekly_briefing(workspace, tenant_id=tenant_id)
        return success_response(payload, "ok")
