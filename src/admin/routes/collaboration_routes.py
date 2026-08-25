"""跨工种协作 HTTP 路由（配置驱动）。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import Request

from admin.collaboration_policy_runtime import summarize_collaboration_policies
from admin.collaboration_runtime import (
    assign_collaboration_request,
    create_collaboration_request,
    list_collaboration_requests,
    mark_collaboration_integrated,
    normalize_collaboration_center,
)


def register_collaboration_routes(
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
) -> None:
    @app.get("/api/autonomy/collaborations/policies")
    async def get_collaboration_policies():
        return success_response(summarize_collaboration_policies(workspace), "协作策略摘要")

    @app.get("/api/autonomy/collaborations")
    async def list_collaborations(request: Request):
        tenant_id = resolve_tenant_id(request.query_params.get("tenant_id"))
        role = str(request.query_params.get("role") or "orchestrator").strip()
        member_id = str(request.query_params.get("member_id") or "").strip() or None
        runtime = load_autonomy_runtime(workspace, tenant_id)
        items = list_collaboration_requests(runtime, role=role, member_id=member_id)
        return success_response({
            "items": items,
            "collaboration_center": normalize_collaboration_center(runtime.get("collaboration_center")),
        }, "协作请求列表")

    @app.post("/api/autonomy/collaborations")
    async def create_collaboration(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        requester_member_id = str(payload.get("requester_member_id") or payload.get("member_id") or "").strip()
        needed_capability = str(payload.get("needed_capability") or "").strip()
        title = str(payload.get("title") or "").strip()
        if not requester_member_id:
            return error_response("requester_member_id 必填", 400)
        runtime = load_autonomy_runtime(workspace, tenant_id)
        try:
            created = create_collaboration_request(
                workspace=workspace,
                runtime=runtime,
                requester_member_id=requester_member_id,
                needed_capability=needed_capability,
                title=title,
                description=str(payload.get("description") or "").strip(),
                requester_task_id=str(payload.get("requester_task_id") or "").strip() or None,
                target_work_type_id=str(payload.get("target_work_type_id") or "").strip() or None,
                target_department_id=str(payload.get("target_department_id") or "").strip() or None,
                requester_continues=payload.get("requester_continues", True) is not False,
                policy_id=str(payload.get("policy_id") or "").strip() or None,
                append_relationship_message=append_relationship_message,
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        save_autonomy_runtime(workspace, runtime, tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, tenant_id))
        return success_response({"request": created, "autonomy": enriched}, "协作请求已创建，请求方可继续并行执行")

    @app.post("/api/autonomy/collaborations/{request_id}/assign")
    async def assign_collaboration(request_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        provider_member_id = str(payload.get("provider_member_id") or "").strip()
        if not provider_member_id:
            return error_response("provider_member_id 必填", 400)
        runtime = load_autonomy_runtime(workspace, tenant_id)
        try:
            result = assign_collaboration_request(
                runtime=runtime,
                request_id=str(request_id or "").strip(),
                provider_member_id=provider_member_id,
                provider_task_id=str(payload.get("provider_task_id") or "").strip() or None,
                assigned_by=str(payload.get("assigned_by") or "talent_development_officer").strip(),
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        save_autonomy_runtime(workspace, runtime, tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, tenant_id))
        return success_response({**result, "autonomy": enriched}, "协作请求已指派提供方")

    @app.post("/api/autonomy/collaborations/{request_id}/mark-integrated")
    async def mark_collaboration_integrated_route(request_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        member_id = str(payload.get("member_id") or payload.get("requester_member_id") or "").strip()
        if not member_id:
            return error_response("member_id 必填", 400)
        runtime = load_autonomy_runtime(workspace, tenant_id)
        try:
            updated = mark_collaboration_integrated(
                runtime=runtime,
                request_id=str(request_id or "").strip(),
                member_id=member_id,
            )
        except ValueError as exc:
            return error_response(str(exc), 400)
        save_autonomy_runtime(workspace, runtime, tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, tenant_id))
        return success_response({"request": updated, "autonomy": enriched}, "已标记协作对接完成")
