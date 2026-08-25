"""
项目级能力包注册入口。

核心系统不直接感知 javascript/android/pc 等具体方向，
而是根据当前工作区声明的 project packages 注册能力与编排。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.capabilities import CapabilityRegistry, get_capability_registry
from core.orchestration import (
    EvaluatorRegistry,
    StrategyRegistry,
    get_evaluator_registry,
    get_strategy_registry,
)


def _project_packages_file(workspace: Path) -> Path:
    path = workspace / ".admin" / "project_packages.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _default_project_packages() -> Dict[str, Any]:
    return {
        "version": 1,
        "packages": [],
    }


PRESET_PROJECT_PACKAGE_IDS = frozenset({"project.javascript"})


def purge_preset_project_packages(workspace: Path) -> list[str]:
    """移除历史预置项目能力包，避免未启用工种时自动注册 JS 等能力。"""
    payload = load_project_packages(workspace)
    packages = payload.get("packages", []) if isinstance(payload.get("packages"), list) else []
    kept = [
        item for item in packages
        if isinstance(item, dict)
        and str(item.get("package_id") or "").strip() not in PRESET_PROJECT_PACKAGE_IDS
    ]
    removed = [
        str(item.get("package_id") or "")
        for item in packages
        if isinstance(item, dict) and str(item.get("package_id") or "").strip() in PRESET_PROJECT_PACKAGE_IDS
    ]
    if len(kept) != len(packages):
        save_project_packages(workspace, {"version": payload.get("version", 1), "packages": kept})
    return removed


def load_project_packages(workspace: Path) -> Dict[str, Any]:
    path = _project_packages_file(workspace)
    if not path.is_file():
        payload = _default_project_packages()
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = _default_project_packages()
    if not isinstance(payload, dict):
        payload = _default_project_packages()
    packages = payload.get("packages", [])
    if not isinstance(packages, list):
        packages = _default_project_packages()["packages"]
    return {
        "version": payload.get("version", 1),
        "packages": [item for item in packages if isinstance(item, dict)],
    }


def save_project_packages(workspace: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        "version": payload.get("version", 1) if isinstance(payload, dict) else 1,
        "packages": [
            item for item in (payload.get("packages", []) if isinstance(payload, dict) else [])
            if isinstance(item, dict)
        ],
    }
    _project_packages_file(workspace).write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return normalized


def register_project_capabilities(
    workspace: Path,
    registry: CapabilityRegistry | None = None,
) -> CapabilityRegistry:
    registry = registry or get_capability_registry()
    packages = load_project_packages(workspace).get("packages", [])
    for item in packages:
        if not bool(item.get("enabled", True)):
            continue
        adapter = str(item.get("adapter") or "").strip().lower()
        if adapter == "javascript":
            from workers.registry import is_worker_enabled

            if not is_worker_enabled(workspace, "javascript_reverse"):
                continue
            from domains.javascript.provider import JavaScriptCapabilityProvider

            provider = JavaScriptCapabilityProvider()
            registered_ids = {descriptor.id for descriptor in registry.list_descriptors()}
            if provider.descriptor.id not in registered_ids:
                registry.register(provider)
    return registry


def register_project_orchestration(
    workspace: Path,
    strategy_registry: StrategyRegistry | None = None,
    evaluator_registry: EvaluatorRegistry | None = None,
) -> tuple[StrategyRegistry, EvaluatorRegistry]:
    strategy_registry = strategy_registry or get_strategy_registry()
    evaluator_registry = evaluator_registry or get_evaluator_registry()
    packages = load_project_packages(workspace).get("packages", [])
    for item in packages:
        if not bool(item.get("enabled", True)):
            continue
        adapter = str(item.get("adapter") or "").strip().lower()
        if adapter == "javascript":
            from workers.registry import is_worker_enabled

            if not is_worker_enabled(workspace, "javascript_reverse"):
                continue
            from domains.javascript.strategy import (
                JavaScriptAnalyzeStrategy,
                JavaScriptEvaluator,
                JavaScriptReconstructStrategy,
            )

            analyze_strategy = JavaScriptAnalyzeStrategy()
            reconstruct_strategy = JavaScriptReconstructStrategy()
            evaluator = JavaScriptEvaluator()

            existing_analyze = {
                provider.descriptor.id
                for provider in strategy_registry.matching("builtin.javascript", "analyze")
            }
            if analyze_strategy.descriptor.id not in existing_analyze:
                strategy_registry.register(analyze_strategy)

            existing_reconstruct = {
                provider.descriptor.id
                for provider in strategy_registry.matching("builtin.javascript", "reconstruct")
            }
            if reconstruct_strategy.descriptor.id not in existing_reconstruct:
                strategy_registry.register(reconstruct_strategy)

            existing_evaluators = {
                provider.id for provider in evaluator_registry.matching("builtin.javascript", "analyze")
            }
            if evaluator.id not in existing_evaluators:
                evaluator_registry.register(evaluator)
    return strategy_registry, evaluator_registry


def build_project_package_runtime_entries(
    workspace: Path,
    registry: CapabilityRegistry | None = None,
) -> list[dict[str, Any]]:
    registry = registry or get_capability_registry()
    descriptors = registry.list_descriptors()
    packages = load_project_packages(workspace).get("packages", [])
    entries: list[dict[str, Any]] = []
    for item in packages:
        if not isinstance(item, dict):
            continue
        if not bool(item.get("enabled", True)):
            continue
        capability_type = str(item.get("capability_type") or "").strip() or None
        package_id = str(item.get("package_id") or "").strip()
        if not package_id:
            continue
        matching = [
            descriptor for descriptor in descriptors
            if (capability_type and descriptor.capability_type == capability_type)
            or str(item.get("adapter") or "").strip().lower() in {tag.lower() for tag in descriptor.tags}
        ]
        entries.append({
            "package_id": package_id,
            "title": str(item.get("title") or package_id).strip() or package_id,
            "description": str(item.get("description") or "").strip() or None,
            "capability_type": capability_type,
            "adapter": str(item.get("adapter") or "").strip() or None,
            "source": str(item.get("source") or "workspace_project").strip() or "workspace_project",
            "capability_ids": [descriptor.id for descriptor in matching],
            "capabilities": [
                {
                    "capability_id": descriptor.id,
                    "name": descriptor.name,
                    "capability_type": descriptor.capability_type,
                    "supported_tasks": list(descriptor.supported_tasks),
                    "provider_kind": descriptor.provider_kind,
                    "tags": list(descriptor.tags),
                }
                for descriptor in matching
            ],
        })
    return entries


__all__ = [
    "build_project_package_runtime_entries",
    "load_project_packages",
    "save_project_packages",
    "register_project_capabilities",
    "register_project_orchestration",
]
