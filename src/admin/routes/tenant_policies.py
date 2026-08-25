"""
租户级插件/知识/外部学习策略接口。
"""

from __future__ import annotations

from typing import Callable

from fastapi import Request


def register_tenant_policy_routes(
    app,
    *,
    tenant_manager,
    plugin_summary,
    success_response: Callable[[dict | None, str], dict],
    error_response: Callable[[str, int], object],
) -> None:
    @app.get("/api/tenants/{tenant_id}/plugins")
    async def get_tenant_plugins(tenant_id: str):
        tenant = tenant_manager.get_tenant(tenant_id)
        if tenant is None:
            tenant_manager.create_tenant(tenant_id, tenant_id)

        return success_response({
            "tenant_id": tenant_id,
            "policy": tenant_manager.get_plugin_policy(tenant_id),
        })

    @app.put("/api/tenants/{tenant_id}/plugins")
    async def update_tenant_plugins(tenant_id: str, request: Request):
        data = await request.json()
        enabled = data.get("enabled", [])
        disabled = data.get("disabled", [])

        if not isinstance(enabled, list) or not isinstance(disabled, list):
            return error_response("enabled/disabled 必须是数组", 400)

        known_plugins = {item.plugin_name for item in plugin_summary.loaded}
        unknown = sorted({
            name
            for name in [*enabled, *disabled]
            if isinstance(name, str) and name not in known_plugins
        })
        if unknown:
            return error_response(f"未知插件: {unknown}", 400)

        tenant_manager.set_plugin_policy(
            tenant_id=tenant_id,
            enabled=[name for name in enabled if isinstance(name, str)],
            disabled=[name for name in disabled if isinstance(name, str)],
        )

        return success_response({
            "tenant_id": tenant_id,
            "policy": tenant_manager.get_plugin_policy(tenant_id),
        }, "插件策略已更新")

    @app.get("/api/tenants/{tenant_id}/knowledge-policy")
    async def get_tenant_knowledge_policy(tenant_id: str):
        tenant = tenant_manager.get_tenant(tenant_id)
        if tenant is None:
            tenant_manager.create_tenant(tenant_id, tenant_id)

        return success_response({
            "tenant_id": tenant_id,
            "policy": tenant_manager.get_knowledge_policy(tenant_id),
        })

    @app.get("/api/tenants/{tenant_id}/external-learning-policy")
    async def get_tenant_external_learning_policy(tenant_id: str):
        from admin.model_provider_runtime import mask_model_provider

        tenant = tenant_manager.get_tenant(tenant_id)
        if tenant is None:
            tenant_manager.create_tenant(tenant_id, tenant_id)

        policy = tenant_manager.get_external_learning_policy(tenant_id)
        if isinstance(policy, dict):
            policy = {
                **policy,
                "model_provider": mask_model_provider(policy.get("model_provider")),
            }
        return success_response({
            "tenant_id": tenant_id,
            "policy": policy,
        })

    @app.put("/api/tenants/{tenant_id}/knowledge-policy")
    async def update_tenant_knowledge_policy(tenant_id: str, request: Request):
        data = await request.json()
        share_mode = data.get("share_mode", "private_only")
        allow_platform_promotion = bool(data.get("allow_platform_promotion", False))
        review_required = bool(data.get("review_required", True))

        if share_mode not in {"private_only", "reviewed_share", "platform_share"}:
            return error_response("share_mode 非法", 400)

        tenant_manager.set_knowledge_policy(
            tenant_id=tenant_id,
            share_mode=share_mode,
            allow_platform_promotion=allow_platform_promotion,
            review_required=review_required,
        )

        return success_response({
            "tenant_id": tenant_id,
            "policy": tenant_manager.get_knowledge_policy(tenant_id),
        }, "知识共享策略已更新")

    @app.put("/api/tenants/{tenant_id}/external-learning-policy")
    async def update_tenant_external_learning_policy(tenant_id: str, request: Request):
        data = await request.json()
        source_priority = data.get("source_priority", [])
        if not isinstance(source_priority, list):
            return error_response("source_priority 必须是数组", 400)

        tenant_manager.set_external_learning_policy(
            tenant_id=tenant_id,
            allow_ai_assist=bool(data.get("allow_ai_assist", True)),
            allow_web_research=bool(data.get("allow_web_research", True)),
            allow_enterprise_sources=bool(data.get("allow_enterprise_sources", True)),
            source_priority=[item for item in source_priority if isinstance(item, str)],
            validation_required=bool(data.get("validation_required", True)),
            model_provider=data.get("model_provider") if isinstance(data.get("model_provider"), dict) else None,
        )

        from admin.model_provider_runtime import mask_model_provider

        policy = tenant_manager.get_external_learning_policy(tenant_id)
        if isinstance(policy, dict):
            policy = {
                **policy,
                "model_provider": mask_model_provider(policy.get("model_provider")),
            }
        return success_response({
            "tenant_id": tenant_id,
            "policy": policy,
        }, "外部学习策略已更新")
