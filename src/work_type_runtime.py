"""
工种路由基表。

统一收口 work_type / capability_type / mission_kind / worker 之间的映射，
供多工种主干复用，而不是分散在各个路由和 runtime 里各自拼接。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_work_type_runtime_index(
    workspace: Path,
    *,
    load_work_types,
    builtin_worker_manifests,
    load_worker_registry_config,
    build_project_package_runtime_entries,
) -> dict[str, Any]:
    work_types_payload = load_work_types(workspace)
    work_type_items = work_types_payload.get("items", []) if isinstance(work_types_payload, dict) else []
    worker_manifests = builtin_worker_manifests(workspace)
    worker_registry = load_worker_registry_config(workspace)
    package_entries = build_project_package_runtime_entries(workspace)
    worker_config = worker_registry.get("workers", {}) if isinstance(worker_registry, dict) else {}

    worker_entries: dict[str, dict[str, Any]] = {}
    for worker_id, manifest in worker_manifests.items():
        manifest = manifest if isinstance(manifest, dict) else {}
        config_entry = worker_config.get(worker_id, {}) if isinstance(worker_config.get(worker_id), dict) else {}
        worker_entries[worker_id] = {
            "worker_id": worker_id,
            "title": manifest.get("title") or worker_id,
            "enabled": bool(config_entry.get("enabled", manifest.get("default_enabled", False))),
            "capability_type": str(manifest.get("capability_type") or "").strip() or None,
            "work_type_ids": [
                str(item).strip()
                for item in (manifest.get("work_type_ids", []) if isinstance(manifest.get("work_type_ids"), list) else [])
                if str(item).strip()
            ],
            "task_types": [
                str(item).strip()
                for item in (manifest.get("task_types", []) if isinstance(manifest.get("task_types"), list) else [])
                if str(item).strip()
            ],
            "owned_modules": [
                str(item).strip()
                for item in (manifest.get("owned_modules", []) if isinstance(manifest.get("owned_modules"), list) else [])
                if str(item).strip()
            ],
        }

    by_work_type: dict[str, dict[str, Any]] = {}
    by_mission_kind: dict[str, list[dict[str, Any]]] = {}
    by_capability_type: dict[str, list[dict[str, Any]]] = {}

    for item in work_type_items:
        if not isinstance(item, dict):
            continue
        work_type_id = str(item.get("work_type_id") or "").strip()
        if not work_type_id:
            continue
        capability_type = str(item.get("capability_type") or "").strip() or None
        mission_kind = str(item.get("mission_kind") or "").strip() or None

        matched_workers = [
            worker
            for worker in worker_entries.values()
            if work_type_id in worker.get("work_type_ids", [])
            or (capability_type and capability_type == worker.get("capability_type"))
        ]
        matched_packages = [
            package
            for package in package_entries
            if capability_type and capability_type == package.get("capability_type")
        ]
        matched_capabilities = []
        seen_capability_ids: set[str] = set()
        for package in matched_packages:
            for capability in package.get("capabilities", []):
                if not isinstance(capability, dict):
                    continue
                capability_id = str(capability.get("capability_id") or "").strip()
                if not capability_id or capability_id in seen_capability_ids:
                    continue
                seen_capability_ids.add(capability_id)
                matched_capabilities.append(capability)

        route_entry = {
            "work_type_id": work_type_id,
            "title": item.get("title") or work_type_id,
            "status": item.get("status") or "active",
            "capability_type": capability_type,
            "mission_kind": mission_kind,
            "enabled_packages": item.get("enabled_packages", []) if isinstance(item.get("enabled_packages"), list) else [],
            "primary_package_id": matched_packages[0]["package_id"] if matched_packages else None,
            "package_ids": [package["package_id"] for package in matched_packages],
            "packages": matched_packages,
            "primary_capability_id": matched_capabilities[0]["capability_id"] if matched_capabilities else None,
            "capability_ids": [capability["capability_id"] for capability in matched_capabilities],
            "capabilities": matched_capabilities,
            "execution_preference": "capability_package" if matched_packages or matched_capabilities else ("worker" if matched_workers else "unresolved"),
            "worker_ids": [worker["worker_id"] for worker in matched_workers],
            "workers": matched_workers,
        }
        by_work_type[work_type_id] = route_entry

        if mission_kind:
            by_mission_kind.setdefault(mission_kind, []).append(route_entry)
        if capability_type:
            by_capability_type.setdefault(capability_type, []).append(route_entry)

    return {
        "work_types": by_work_type,
        "workers": worker_entries,
        "by_mission_kind": by_mission_kind,
        "by_capability_type": by_capability_type,
    }


def resolve_runtime_route(
    workspace: Path,
    *,
    work_type_id: str | None,
    mission_kind: str | None,
    capability_type: str | None,
    load_work_types,
    builtin_worker_manifests,
    load_worker_registry_config,
    build_project_package_runtime_entries,
) -> dict[str, Any]:
    index = build_work_type_runtime_index(
        workspace,
        load_work_types=load_work_types,
        builtin_worker_manifests=builtin_worker_manifests,
        load_worker_registry_config=load_worker_registry_config,
        build_project_package_runtime_entries=build_project_package_runtime_entries,
    )

    normalized_work_type_id = str(work_type_id or "").strip()
    normalized_mission_kind = str(mission_kind or "").strip()
    normalized_capability_type = str(capability_type or "").strip()

    if normalized_work_type_id and normalized_work_type_id in index["work_types"]:
        return index["work_types"][normalized_work_type_id]
    if normalized_mission_kind and normalized_mission_kind in index["by_mission_kind"]:
        return index["by_mission_kind"][normalized_mission_kind][0]
    if normalized_capability_type and normalized_capability_type in index["by_capability_type"]:
        return index["by_capability_type"][normalized_capability_type][0]
    return {
        "work_type_id": normalized_work_type_id or None,
        "mission_kind": normalized_mission_kind or None,
        "capability_type": normalized_capability_type or None,
        "primary_package_id": None,
        "package_ids": [],
        "packages": [],
        "primary_capability_id": None,
        "capability_ids": [],
        "capabilities": [],
        "execution_preference": "unresolved",
        "worker_ids": [],
        "workers": [],
    }


__all__ = [
    "build_work_type_runtime_index",
    "resolve_runtime_route",
]
