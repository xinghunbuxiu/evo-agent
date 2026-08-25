"""
插件、能力类型、项目能力包、工种目录等静态/配置型接口。
"""

from __future__ import annotations

from typing import Callable

from core import PluginLoader

RESERVED_WORK_TYPE_IDS = frozenset({
    "talent_development",
    "talent_development_officer",
    "finance",
})


def _validate_work_types_payload(data: dict) -> str | None:
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return "工种配置 items 必须为数组"
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        work_type_id = str(item.get("work_type_id") or "").strip()
        if not work_type_id:
            return "工种配置存在空的 work_type_id"
        if work_type_id in RESERVED_WORK_TYPE_IDS:
            return f"工种 ID {work_type_id} 为系统内置职能保留"
        if work_type_id in seen:
            return f"工种 ID {work_type_id} 重复"
        seen.add(work_type_id)
    return None


def register_catalog_routes(
    app,
    *,
    workspace,
    plugin_summary,
    capability_registry,
    capability_type_label: Callable[[str], str],
    capability_type_catalog: Callable[[], list[dict]],
    mission_kind_templates: dict,
    load_project_packages: Callable,
    save_project_packages: Callable,
    load_work_types: Callable,
    save_work_types: Callable,
    builtin_worker_manifests: Callable[..., dict[str, dict]],
    load_worker_registry_config: Callable,
    build_project_package_runtime_entries: Callable[..., list[dict]],
    build_work_type_runtime_index: Callable[..., dict],
    success_response: Callable[[dict | None, str], dict],
) -> None:
    @app.get("/api/plugins")
    async def list_plugins():
        plugins = []
        for item in plugin_summary.loaded:
            manifest = PluginLoader.manifests.get(item.plugin_name, {})
            plugins.append({
                "name": item.plugin_name,
                "version": item.version,
                "capability_types": item.capability_types,
                "manifest": manifest,
                "capabilities": item.capabilities,
                "strategies": item.strategies,
                "evaluators": item.evaluators,
                "module_path": item.module_path,
            })

        return success_response({
            "plugins": plugins,
            "skipped": plugin_summary.skipped,
        })

    @app.get("/api/capability-types")
    async def list_capability_types():
        descriptors = capability_registry.list_descriptors()
        usage: dict[str, dict] = {}
        for descriptor in descriptors:
            capability_type = descriptor.capability_type
            entry = usage.setdefault(capability_type, {
                "id": capability_type,
                "name": capability_type_label(capability_type),
                "capability_ids": [],
                "provider_kinds": [],
                "tags": [],
            })
            entry["capability_ids"].append(descriptor.id)
            if descriptor.provider_kind not in entry["provider_kinds"]:
                entry["provider_kinds"].append(descriptor.provider_kind)
            for tag in descriptor.tags:
                if tag not in entry["tags"]:
                    entry["tags"].append(tag)

        catalog = capability_type_catalog()
        for item in catalog:
            current = usage.setdefault(item["id"], {
                "id": item["id"],
                "name": item["name"],
                "capability_ids": [],
                "provider_kinds": [],
                "tags": [],
            })
            current["description"] = item.get("description", "")
            current["legacy_domains"] = item.get("legacy_domains", [])

        return success_response({
            "items": sorted(usage.values(), key=lambda item: item["id"]),
        })

    @app.get("/api/missions/templates")
    async def list_mission_templates():
        items = []
        for mission_kind, template in mission_kind_templates.items():
            items.append({
                "mission_kind": mission_kind,
                "title": template.get("title"),
                "description": template.get("description"),
                "primary_capability_type": template.get("primary_capability_type"),
                "delivery_targets": template.get("delivery", []),
            })
        return success_response({"items": items})

    @app.get("/api/project-packages")
    async def get_project_packages():
        return success_response(load_project_packages(workspace))

    @app.put("/api/project-packages")
    async def update_project_packages(request):
        data = await request.json()
        saved = save_project_packages(workspace, data if isinstance(data, dict) else {})
        return success_response(saved, "项目能力包配置已更新")

    @app.get("/api/work-types")
    async def get_work_types():
        payload = load_work_types(workspace)
        runtime_index = build_work_type_runtime_index(
            workspace,
            load_work_types=load_work_types,
            builtin_worker_manifests=builtin_worker_manifests,
            load_worker_registry_config=load_worker_registry_config,
            build_project_package_runtime_entries=build_project_package_runtime_entries,
        )
        items = payload.get("items", []) if isinstance(payload, dict) else []
        enriched_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            work_type_id = str(item.get("work_type_id") or "").strip()
            route = runtime_index.get("work_types", {}).get(work_type_id, {})
            enriched_items.append({
                **item,
                "runtime_route": route,
            })
        return success_response({
            **(payload if isinstance(payload, dict) else {"version": 1}),
            "items": enriched_items,
            "runtime_index": runtime_index,
        })

    @app.put("/api/work-types")
    async def update_work_types(request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        error = _validate_work_types_payload(payload)
        if error:
            return {"code": 400, "success": False, "message": error, "data": {}}
        saved = save_work_types(workspace, payload)
        return success_response(saved, "工种配置已更新")
