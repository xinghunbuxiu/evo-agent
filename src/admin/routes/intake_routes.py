"""商业接单 HTTP 路由（配置驱动）。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import Request

from admin.intake_policy_runtime import summarize_intake_policies
from admin.intake_runtime import (
    analyze_intake,
    assign_intake,
    build_intake_funnel,
    cancel_intake,
    create_intake,
    list_available_capabilities,
    list_intakes,
    normalize_intake_center,
    settle_intake,
)


def register_intake_routes(
    app,
    *,
    workspace: Path,
    load_autonomy_runtime: Callable,
    save_autonomy_runtime: Callable,
    resolve_tenant_id: Callable,
    enrich_autonomy_runtime: Callable,
    append_relationship_message: Callable,
    success_response: Callable,
    error_response: Callable,
    task_queue=None,
    task_priority_normal=None,
) -> None:
    @app.get("/api/autonomy/intake/policies")
    async def get_intake_policies():
        return success_response({
            **summarize_intake_policies(workspace),
            "capabilities": list_available_capabilities(workspace),
        }, "接单路由策略摘要")

    @app.get("/api/autonomy/intake")
    async def list_intake_orders(request: Request):
        tenant_id = resolve_tenant_id(request.query_params.get("tenant_id"))
        status = str(request.query_params.get("status") or "").strip() or None
        member_id = str(request.query_params.get("member_id") or "").strip() or None
        runtime = load_autonomy_runtime(workspace, tenant_id)
        center = normalize_intake_center(runtime.get("intake_center"))
        items = list_intakes(runtime, status=status, member_id=member_id)
        return success_response({
            "items": items,
            "funnel": build_intake_funnel(center),
            "intake_center": center,
        }, "接单列表")

    @app.post("/api/autonomy/intake")
    async def create_intake_order(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        title = str(payload.get("title") or "").strip()
        if not title:
            return error_response("title 必填", 400)
        runtime = load_autonomy_runtime(workspace, tenant_id)
        deliverables = payload.get("expected_deliverables")
        capabilities = payload.get("needed_capabilities")
        try:
            created = create_intake(
                workspace=workspace,
                runtime=runtime,
                title=title,
                description=str(payload.get("description") or "").strip(),
                expected_deliverables=[
                    str(x).strip() for x in (deliverables if isinstance(deliverables, list) else []) if str(x).strip()
                ],
                needed_capabilities=[
                    str(x).strip() for x in (capabilities if isinstance(capabilities, list) else []) if str(x).strip()
                ],
                source=str(payload.get("source") or "outsourcing").strip() or "outsourcing",
                budget=payload.get("budget"),
                quoted_amount=payload.get("quoted_amount"),
                currency=str(payload.get("currency") or "CNY").strip() or "CNY",
                client_label=str(payload.get("client_label") or "").strip() or None,
                deadline_at=str(payload.get("deadline_at") or "").strip() or None,
                policy_id=str(payload.get("policy_id") or "").strip() or None,
                project_id=str(payload.get("project_id") or "").strip() or None,
                auto_analyze=payload.get("auto_analyze", True) is not False,
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        save_autonomy_runtime(workspace, runtime, tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, tenant_id))
        return success_response({"intake": created, "autonomy": enriched}, "接单已创建并完成智脑初析")

    @app.post("/api/autonomy/intake/{intake_id}/analyze")
    async def analyze_intake_order(intake_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        runtime = load_autonomy_runtime(workspace, tenant_id)
        try:
            analyzed = analyze_intake(workspace=workspace, runtime=runtime, intake_id=str(intake_id or "").strip())
        except ValueError as exc:
            return error_response(str(exc), 400)
        save_autonomy_runtime(workspace, runtime, tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, tenant_id))
        return success_response({"intake": analyzed, "autonomy": enriched}, "智脑路由分析完成")

    @app.post("/api/autonomy/intake/{intake_id}/assign")
    async def assign_intake_order(intake_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        member_id = str(payload.get("member_id") or "").strip()
        if not member_id:
            runtime = load_autonomy_runtime(workspace, tenant_id)
            center = normalize_intake_center(runtime.get("intake_center"))
            items = center.get("items") if isinstance(center.get("items"), list) else []
            current = next(
                (
                    item for item in items
                    if isinstance(item, dict) and str(item.get("intake_id") or "").strip() == str(intake_id or "").strip()
                ),
                None,
            )
            routing = current.get("routing") if isinstance(current, dict) and isinstance(current.get("routing"), dict) else {}
            member_id = str(routing.get("recommended_member_id") or "").strip()
        if not member_id:
            return error_response("member_id 必填（或先完成智脑分析以获得推荐）", 400)
        runtime = load_autonomy_runtime(workspace, tenant_id)
        try:
            result = assign_intake(
                workspace=workspace,
                runtime=runtime,
                intake_id=str(intake_id or "").strip(),
                member_id=member_id,
                assigned_by=str(payload.get("assigned_by") or "talent_development_officer").strip(),
                override_reason=str(payload.get("override_reason") or "").strip() or None,
                task_queue=task_queue,
                task_priority_normal=task_priority_normal,
                append_relationship_message=append_relationship_message,
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        save_autonomy_runtime(workspace, runtime, tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, tenant_id))
        return success_response({**result, "autonomy": enriched}, "接单已分派并创建正式任务")

    @app.post("/api/autonomy/intake/{intake_id}/settle")
    async def settle_intake_order(intake_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        runtime = load_autonomy_runtime(workspace, tenant_id)
        try:
            result = settle_intake(
                workspace=workspace,
                runtime=runtime,
                intake_id=str(intake_id or "").strip(),
                settled_amount=payload.get("settled_amount"),
                cost=payload.get("cost"),
                note=str(payload.get("note") or "").strip() or None,
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        save_autonomy_runtime(workspace, runtime, tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, tenant_id))
        return success_response({**result, "autonomy": enriched}, "接单已结算并记入财务")

    @app.post("/api/autonomy/intake/{intake_id}/cancel")
    async def cancel_intake_order(intake_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        runtime = load_autonomy_runtime(workspace, tenant_id)
        try:
            cancelled = cancel_intake(
                runtime=runtime,
                intake_id=str(intake_id or "").strip(),
                reason=str(payload.get("reason") or "").strip() or None,
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        save_autonomy_runtime(workspace, runtime, tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, tenant_id))
        return success_response({"intake": cancelled, "autonomy": enriched}, "接单已取消")
