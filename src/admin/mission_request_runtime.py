"""
Mission 请求预处理：统一准备工种、校验和运行路由。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def _normalize_runtime_route(route: dict[str, Any] | None) -> dict[str, Any]:
    route = route if isinstance(route, dict) else {}
    packages = route.get("packages", []) if isinstance(route.get("packages"), list) else []
    normalized_packages = []
    package_ids: list[str] = []
    capability_ids: list[str] = []
    normalized_capabilities = []
    primary_package_id: str | None = None
    primary_capability_id: str | None = None
    for item in packages:
        if not isinstance(item, dict):
            continue
        package_id = str(item.get("package_id") or "").strip()
        if not package_id:
            continue
        package_ids.append(package_id)
        if primary_package_id is None:
            primary_package_id = package_id
        capabilities = item.get("capabilities", []) if isinstance(item.get("capabilities"), list) else []
        normalized_pkg_capabilities = []
        for capability in capabilities:
            if not isinstance(capability, dict):
                continue
            capability_id = str(capability.get("capability_id") or "").strip()
            if not capability_id:
                continue
            if capability_id not in capability_ids:
                capability_ids.append(capability_id)
            if primary_capability_id is None:
                primary_capability_id = capability_id
            normalized_capability = {
                "capability_id": capability_id,
                "name": capability.get("name") or capability_id,
                "capability_type": str(capability.get("capability_type") or "").strip() or None,
                "supported_tasks": capability.get("supported_tasks", []) if isinstance(capability.get("supported_tasks"), list) else [],
                "provider_kind": str(capability.get("provider_kind") or "").strip() or None,
                "tags": capability.get("tags", []) if isinstance(capability.get("tags"), list) else [],
            }
            normalized_capabilities.append(normalized_capability)
            normalized_pkg_capabilities.append(normalized_capability)
        normalized_packages.append({
            "package_id": package_id,
            "title": item.get("title") or package_id,
            "description": item.get("description"),
            "capability_type": str(item.get("capability_type") or "").strip() or None,
            "adapter": str(item.get("adapter") or "").strip() or None,
            "source": str(item.get("source") or "").strip() or None,
            "capability_ids": [entry["capability_id"] for entry in normalized_pkg_capabilities],
            "capabilities": normalized_pkg_capabilities,
        })
    workers = route.get("workers", []) if isinstance(route.get("workers"), list) else []
    normalized_workers = []
    worker_ids: list[str] = []
    primary_worker_id: str | None = None
    for item in workers:
        if not isinstance(item, dict):
            continue
        worker_id = str(item.get("worker_id") or "").strip()
        if not worker_id:
            continue
        worker_ids.append(worker_id)
        if primary_worker_id is None and bool(item.get("enabled", True)):
            primary_worker_id = worker_id
        normalized_workers.append({
            "worker_id": worker_id,
            "title": item.get("title") or worker_id,
            "enabled": bool(item.get("enabled", True)),
            "capability_type": str(item.get("capability_type") or "").strip() or None,
            "task_types": item.get("task_types", []) if isinstance(item.get("task_types"), list) else [],
            "owned_modules": item.get("owned_modules", []) if isinstance(item.get("owned_modules"), list) else [],
        })
    return {
        "work_type_id": str(route.get("work_type_id") or "").strip() or None,
        "title": route.get("title"),
        "status": route.get("status"),
        "mission_kind": str(route.get("mission_kind") or "").strip() or None,
        "capability_type": str(route.get("capability_type") or "").strip() or None,
        "enabled_packages": route.get("enabled_packages", []) if isinstance(route.get("enabled_packages"), list) else [],
        "execution_preference": str(route.get("execution_preference") or "").strip() or ("capability_package" if package_ids or capability_ids else ("worker" if worker_ids else "unresolved")),
        "primary_package_id": primary_package_id,
        "package_ids": package_ids,
        "packages": normalized_packages,
        "primary_capability_id": primary_capability_id,
        "capability_ids": capability_ids,
        "capabilities": normalized_capabilities,
        "primary_worker_id": primary_worker_id,
        "worker_ids": worker_ids,
        "workers": normalized_workers,
    }


def prepare_mission_work_type_bundle(
    *,
    workspace: Path,
    work_type_id: str | None,
    goal: str,
    mission_kind: str | None,
    context: dict[str, Any] | None,
    resolve_work_type_context: Callable[..., dict],
    summarize_work_type: Callable[[dict | None], dict | None],
    validate_work_type_request: Callable[..., dict],
    resolve_runtime_route: Callable[..., dict],
    load_work_types: Callable[..., dict],
    builtin_worker_manifests: Callable[..., dict],
    load_worker_registry_config: Callable[..., dict],
    build_project_package_runtime_entries: Callable[..., list[dict]],
) -> dict[str, Any]:
    context = dict(context or {})
    resolved = resolve_work_type_context(
        workspace,
        work_type_id=work_type_id,
        goal=goal,
        mission_kind=mission_kind,
        context=context,
    )
    work_type = resolved.get("work_type")
    work_type_summary = summarize_work_type(work_type)
    resolved_goal = str(resolved.get("goal") or "").strip()
    resolved_mission_kind = resolved.get("mission_kind")
    resolved_context = resolved.get("context", {})
    if not isinstance(resolved_context, dict):
        resolved_context = {}

    if isinstance(work_type_summary, dict):
        resolved_context.setdefault("work_type_title", work_type_summary.get("title"))
        resolved_context.setdefault("work_type_required_inputs", work_type_summary.get("required_inputs", []))
        resolved_context.setdefault("work_type_optional_inputs", work_type_summary.get("optional_inputs", []))
        resolved_context.setdefault("work_type_deliverables", work_type_summary.get("deliverables", []))
        resolved_context.setdefault("work_type_knowledge_policy", work_type_summary.get("knowledge_policy", {}))
        resolved_context.setdefault("work_type_type_key", work_type_summary.get("type_key"))

    validation = validate_work_type_request(
        work_type=work_type,
        context=resolved_context,
    )

    capability_type = ""
    if isinstance(work_type_summary, dict):
        capability_type = str(work_type_summary.get("capability_type") or "").strip()
    if not capability_type:
        capability_type = str(resolved_context.get("capability_type") or "").strip()

    route = resolve_runtime_route(
        workspace,
        work_type_id=(
            str((work_type or {}).get("work_type_id") or "").strip()
            if isinstance(work_type, dict)
            else work_type_id
        ),
        mission_kind=resolved_mission_kind,
        capability_type=capability_type or None,
        load_work_types=load_work_types,
        builtin_worker_manifests=builtin_worker_manifests,
        load_worker_registry_config=load_worker_registry_config,
        build_project_package_runtime_entries=build_project_package_runtime_entries,
    )
    runtime_route = _normalize_runtime_route(route)
    resolved_context.setdefault("runtime_route", runtime_route)
    resolved_context.setdefault("runtime_execution_preference", runtime_route.get("execution_preference"))
    resolved_context.setdefault("runtime_primary_package_id", runtime_route.get("primary_package_id"))
    resolved_context.setdefault("runtime_package_ids", runtime_route.get("package_ids", []))
    resolved_context.setdefault("runtime_primary_capability_id", runtime_route.get("primary_capability_id"))
    resolved_context.setdefault("runtime_capability_ids", runtime_route.get("capability_ids", []))
    resolved_context.setdefault("runtime_primary_worker_id", runtime_route.get("primary_worker_id"))
    resolved_context.setdefault("runtime_worker_ids", runtime_route.get("worker_ids", []))
    resolved_context.setdefault("runtime_capability_type", runtime_route.get("capability_type"))

    return {
        "goal": resolved_goal,
        "mission_kind": resolved_mission_kind,
        "context": resolved_context,
        "work_type": work_type,
        "work_type_summary": work_type_summary if isinstance(work_type_summary, dict) else None,
        "work_type_validation": validation if isinstance(validation, dict) else {},
        "runtime_route": runtime_route,
    }


__all__ = [
    "prepare_mission_work_type_bundle",
]
