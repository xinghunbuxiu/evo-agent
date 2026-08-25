"""
演化总览、策略复盘与平台共享接口。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import Request


def register_evolution_strategy_routes(
    app,
    *,
    workspace: Path,
    task_queue,
    tenant_manager,
    plugin_summary,
    build_evolution_overview: Callable[..., dict],
    load_review_queue: Callable[[Path, str], list[dict]],
    enqueue_strategy_review: Callable[..., dict],
    generate_review_draft: Callable[[Path, str, str], dict | None],
    generate_review_experiment_plan: Callable[[Path, str, str], dict | None],
    run_review_experiment: Callable[..., dict | None],
    update_upgrade_candidate_decision: Callable[..., dict | None],
    promote_review_entry_to_platform: Callable[..., dict],
    save_review_queue: Callable[[Path, str, list[dict]], None],
    list_platform_strategy_promotions: Callable[[Path, int], list[dict]],
    platform_shared_seed_recommendations: Callable[..., dict],
    apply_platform_shared_seeds: Callable[..., dict],
    rollback_strategy_override: Callable[[Path, str, str], dict],
    success_response: Callable[[dict | None, str], dict],
    error_response: Callable[[str, int], object],
) -> None:
    @app.get("/api/evolution/overview")
    async def get_evolution_overview(tenant_id: str = "default"):
        return success_response(
            build_evolution_overview(
                workspace=workspace,
                tenant_id=tenant_id,
                task_queue=task_queue,
                plugin_summary=plugin_summary,
                tenant_manager=tenant_manager,
            )
        )

    @app.get("/api/tenants/{tenant_id}/strategy-review-queue")
    async def get_strategy_review_queue(tenant_id: str):
        return success_response({
            "tenant_id": tenant_id,
            "items": load_review_queue(workspace, tenant_id),
        })

    @app.post("/api/tenants/{tenant_id}/strategy-review-queue")
    async def add_strategy_review_queue(tenant_id: str, request: Request):
        data = await request.json()
        strategy_id = data.get("strategy_id")
        if not strategy_id:
            return error_response("strategy_id 不能为空", 400)

        entry = enqueue_strategy_review(
            workspace=workspace,
            tenant_id=tenant_id,
            strategy_id=strategy_id,
            payload=data,
        )
        return success_response({
            "tenant_id": tenant_id,
            "entry": entry,
        }, "已加入复盘队列")

    @app.post("/api/tenants/{tenant_id}/strategy-review-queue/{review_id}/draft")
    async def generate_strategy_review_draft_route(tenant_id: str, review_id: str):
        entry = generate_review_draft(workspace, tenant_id, review_id)
        if not entry:
            return error_response("复盘项不存在", 404)
        return success_response({
            "tenant_id": tenant_id,
            "entry": entry,
        }, "优化草案已生成")

    @app.post("/api/tenants/{tenant_id}/strategy-review-queue/{review_id}/experiment")
    async def generate_strategy_review_experiment(tenant_id: str, review_id: str):
        entry = generate_review_experiment_plan(workspace, tenant_id, review_id)
        if not entry:
            return error_response("复盘项不存在或尚未生成草案", 404)
        return success_response({
            "tenant_id": tenant_id,
            "entry": entry,
        }, "重放实验计划已生成")

    @app.post("/api/tenants/{tenant_id}/strategy-review-queue/{review_id}/run")
    async def run_strategy_review_experiment_route(tenant_id: str, review_id: str):
        try:
            entry = run_review_experiment(workspace, tenant_id, review_id, task_queue)
        except ValueError as exc:
            return error_response(str(exc), 400)

        if not entry:
            return error_response("复盘项不存在或尚未生成实验计划", 404)
        return success_response({
            "tenant_id": tenant_id,
            "entry": entry,
        }, "实验计划已开始执行")

    @app.post("/api/tenants/{tenant_id}/strategy-review-queue/{review_id}/upgrade/{decision}")
    async def decide_strategy_upgrade_candidate(tenant_id: str, review_id: str, decision: str):
        try:
            entry = update_upgrade_candidate_decision(
                workspace=workspace,
                tenant_id=tenant_id,
                review_id=review_id,
                decision=decision,
            )
        except ValueError as exc:
            return error_response(str(exc), 400)

        if not entry:
            return error_response("升级候选不存在，请先完成正向实验", 404)
        return success_response({
            "tenant_id": tenant_id,
            "entry": entry,
        }, "升级候选决策已更新")

    @app.post("/api/tenants/{tenant_id}/strategy-review-queue/{review_id}/promote")
    async def promote_strategy_review_to_platform(tenant_id: str, review_id: str):
        items = load_review_queue(workspace, tenant_id)
        target = next((item for item in items if item.get("id") == review_id), None)
        if not target:
            return error_response("复盘项不存在", 404)

        try:
            promoted = promote_review_entry_to_platform(
                workspace=workspace,
                tenant_id=tenant_id,
                review_entry=target,
                tenant_manager=tenant_manager,
            )
        except PermissionError as exc:
            return error_response(f"当前租户不允许平台共享: {exc}", 403)
        except ValueError as exc:
            return error_response(str(exc), 400)

        save_review_queue(workspace, tenant_id, items)
        return success_response({
            "tenant_id": tenant_id,
            "entry": promoted,
        }, "已上报到平台共享层")

    @app.get("/api/platform-shared/strategy-promotions")
    async def list_platform_shared_strategy_promotions_route(limit: int = 20):
        return success_response({
            "items": list_platform_strategy_promotions(workspace, limit=max(1, min(limit, 100))),
        })

    @app.get("/api/tenants/{tenant_id}/platform-shared/seeds")
    async def get_platform_shared_seed_recommendations(tenant_id: str, limit: int = 5):
        return success_response(
            platform_shared_seed_recommendations(
                workspace=workspace,
                tenant_id=tenant_id,
                tenant_manager=tenant_manager,
                limit=max(1, min(limit, 20)),
            )
        )

    @app.post("/api/tenants/{tenant_id}/platform-shared/seeds/apply")
    async def apply_platform_shared_seeds_route(tenant_id: str, request: Request):
        data = await request.json()
        strategy_ids = data.get("strategy_ids", [])
        if not isinstance(strategy_ids, list):
            return error_response("strategy_ids 必须是数组", 400)
        return success_response(
            apply_platform_shared_seeds(
                workspace=workspace,
                tenant_id=tenant_id,
                tenant_manager=tenant_manager,
                strategy_ids=[item for item in strategy_ids if isinstance(item, str)],
            ),
            "平台冷启动种子已应用",
        )

    @app.post("/api/tenants/{tenant_id}/strategy-overrides/{strategy_id}/rollback")
    async def rollback_strategy_override_route(tenant_id: str, strategy_id: str):
        overrides = rollback_strategy_override(workspace, tenant_id, strategy_id)
        return success_response({
            "tenant_id": tenant_id,
            "strategy_id": strategy_id,
            "strategy_overrides": overrides,
        }, "策略运行时覆盖已回滚")
