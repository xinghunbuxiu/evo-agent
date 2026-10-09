"""工作节点 HTTP 路由（聚合 task_center + 经验 + Gitee 归档）。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import Request

from admin.work_nodes_runtime import (
    archive_work_node_to_storage,
    retry_local_work_node_archive,
    attach_archive_to_task,
    build_work_nodes_from_runtime,
    filter_work_nodes,
    list_skills_for_scope,
)


def register_work_nodes_routes(
    app,
    *,
    workspace: Path,
    load_autonomy_runtime: Callable,
    save_autonomy_runtime: Callable,
    resolve_tenant_id: Callable,
    enrich_autonomy_runtime: Callable,
    success_response: Callable,
    error_response: Callable,
    get_user_gitee_token: Callable,
    tenant_manager,
    config,
    get_git_provider_instance: Callable,
    get_tenant_git_repo: Callable,
) -> None:
    @app.get("/api/autonomy/work-nodes")
    async def list_work_nodes(request: Request):
        tenant_id = resolve_tenant_id(request.query_params.get("tenant_id"))
        work_type_id = str(request.query_params.get("work_type_id") or request.query_params.get("wt") or "").strip() or None
        member_id = str(request.query_params.get("member_id") or request.query_params.get("member") or "").strip() or None
        node_id = str(request.query_params.get("node_id") or request.query_params.get("node") or "").strip() or None
        runtime = load_autonomy_runtime(workspace, tenant_id)
        nodes = build_work_nodes_from_runtime(workspace, runtime)
        items = filter_work_nodes(nodes, work_type_id=work_type_id, member_id=member_id, node_id=node_id)
        return success_response({"items": items, "total": len(items)}, "工作节点列表")

    @app.get("/api/autonomy/work-nodes/skills")
    async def list_work_node_skills(request: Request):
        tenant_id = resolve_tenant_id(request.query_params.get("tenant_id"))
        work_type_id = str(request.query_params.get("work_type_id") or request.query_params.get("wt") or "").strip() or None
        member_id = str(request.query_params.get("member_id") or request.query_params.get("member") or "").strip() or None
        try:
            limit = max(1, min(80, int(request.query_params.get("limit") or 40)))
        except (TypeError, ValueError):
            limit = 40
        items = list_skills_for_scope(
            workspace,
            tenant_id,
            work_type_id=work_type_id,
            member_id=member_id,
            limit=limit,
        )
        return success_response({"items": items, "total": len(items)}, "技能条目列表")


    @app.post("/api/autonomy/work-nodes/{task_id}/archive/retry")
    async def retry_work_node_archive(task_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        normalized_task_id = str(task_id or payload.get("task_id") or "").strip()
        if not normalized_task_id:
            return error_response("task_id 必填", 400)
        runtime = load_autonomy_runtime(workspace, tenant_id)
        archive_result = await retry_local_work_node_archive(
            workspace=workspace,
            tenant_id=tenant_id,
            runtime=runtime,
            task_id=normalized_task_id,
            get_user_gitee_token=get_user_gitee_token,
            tenant_manager=tenant_manager,
            config=config,
            get_git_provider_instance=get_git_provider_instance,
            get_tenant_git_repo=get_tenant_git_repo,
            request=request,
        )
        if archive_result.get("status") == "failed":
            return error_response(str(archive_result.get("next_action") or archive_result.get("reason") or "archive_retry_failed"), 400)
        if archive_result.get("status") == "blocked":
            return error_response(str(archive_result.get("next_action") or archive_result.get("reason") or "blocked"), 400)
        if attach_archive_to_task(runtime, normalized_task_id, archive_result):
            save_autonomy_runtime(workspace, runtime, tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, tenant_id))
        return success_response(
            {"archive": archive_result, "autonomy": enriched},
            str(archive_result.get("next_action") or "本地归档同步完成"),
        )

    @app.post("/api/autonomy/work-nodes/{task_id}/archive")
    async def archive_work_node(task_id: str, request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        normalized_task_id = str(task_id or payload.get("task_id") or "").strip()
        if not normalized_task_id:
            return error_response("task_id 必填", 400)
        runtime = load_autonomy_runtime(workspace, tenant_id)
        archive_result = await archive_work_node_to_storage(
            workspace=workspace,
            tenant_id=tenant_id,
            runtime=runtime,
            task_id=normalized_task_id,
            get_user_gitee_token=get_user_gitee_token,
            tenant_manager=tenant_manager,
            config=config,
            get_git_provider_instance=get_git_provider_instance,
            get_tenant_git_repo=get_tenant_git_repo,
            request=request,
        )
        if archive_result.get("status") == "failed":
            return error_response(str(archive_result.get("reason") or "archive_failed"), 404)
        if archive_result.get("status") == "blocked":
            return error_response(str(archive_result.get("next_action") or archive_result.get("reason") or "blocked"), 400)
        if attach_archive_to_task(runtime, normalized_task_id, archive_result):
            save_autonomy_runtime(workspace, runtime, tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, tenant_id))
        return success_response({"archive": archive_result, "autonomy": enriched}, str(archive_result.get("next_action") or "节点归档完成"))
