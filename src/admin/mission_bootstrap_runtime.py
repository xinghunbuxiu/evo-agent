"""
Mission 入口装配运行时：负责工种准备、mission run 刷新与启动编排。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from core.tenant import TenantManager

from admin.mission_request_runtime import prepare_mission_work_type_bundle
from admin.mission_run_builder_runtime import create_mission_run_builder
from admin.mission_runtime import create_start_mission, refresh_mission_runs


def create_mission_bootstrap_runtime_bindings(
    *,
    workspace: Path,
    task_queue,
    tenant_manager: TenantManager,
    mission_planner,
    upsert_plan_learning_tasks: Callable[..., list[str]],
    error_response: Callable[[str, int], object],
    build_mission_actions: Callable[..., dict],
    refresh_runtime_learning_tasks: Callable[..., dict],
    refresh_mission_run: Callable[..., dict],
    build_mission_next_cycle_plan: Callable,
    build_mission_growth_timeline: Callable,
    resolve_work_type_context: Callable,
    summarize_work_type: Callable,
    validate_work_type_request: Callable,
    resolve_runtime_route: Callable[..., dict],
    load_work_types: Callable,
    builtin_worker_manifests,
    load_worker_registry_config: Callable,
    build_project_package_runtime_entries: Callable,
    sync_autonomy_runtime_from_missions: Callable[..., list[dict] | None] | None = None,
    resolve_mission_member_context: Callable[..., dict] | None = None,
):
    def prepare_bundle(**kwargs) -> dict:
        return prepare_mission_work_type_bundle(
            **kwargs,
            resolve_work_type_context=resolve_work_type_context,
            summarize_work_type=summarize_work_type,
            validate_work_type_request=validate_work_type_request,
            resolve_runtime_route=resolve_runtime_route,
            load_work_types=load_work_types,
            builtin_worker_manifests=builtin_worker_manifests,
            load_worker_registry_config=load_worker_registry_config,
            build_project_package_runtime_entries=build_project_package_runtime_entries,
        )

    def refresh_runs(*, workspace: Path, task_queue, tenant_manager: TenantManager, mission_starter=None) -> dict:
        return refresh_mission_runs(
            workspace=workspace,
            task_queue=task_queue,
            tenant_manager=tenant_manager,
            refresh_runtime_learning_tasks=refresh_runtime_learning_tasks,
            refresh_mission_run=lambda **kwargs: refresh_mission_run(
                **kwargs,
                build_mission_next_cycle_plan=build_mission_next_cycle_plan,
                build_mission_growth_timeline=build_mission_growth_timeline,
            ),
            mission_starter=mission_starter,
            sync_autonomy_runtime_from_missions=sync_autonomy_runtime_from_missions,
        )

    start_mission = create_start_mission(
        workspace=workspace,
        task_queue=task_queue,
        tenant_manager=tenant_manager,
        prepare_mission_work_type_bundle=prepare_bundle,
        mission_planner=mission_planner,
        upsert_plan_learning_tasks=upsert_plan_learning_tasks,
        build_mission_run=create_mission_run_builder(
            build_mission_actions=build_mission_actions,
        ),
        refresh_mission_runs_fn=refresh_runs,
        error_response=error_response,
        resolve_mission_member_context=resolve_mission_member_context,
    )

    return {
        "prepare_mission_work_type_bundle": prepare_bundle,
        "refresh_mission_runs": refresh_runs,
        "start_mission": start_mission,
    }


__all__ = ["create_mission_bootstrap_runtime_bindings"]
