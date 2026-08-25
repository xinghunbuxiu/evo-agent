"""
工种注册表。

内置边界：仅育成师、财务为系统职能；业务工种一律从 openSpec / .admin/workers 发现。
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# 业务工种不再内置；保留空 dict 以兼容旧 import。
BUILTIN_WORKER_DEFINITIONS: dict[str, dict[str, Any]] = {}


def builtin_worker_definitions(workspace: Path | None = None) -> dict[str, dict[str, Any]]:
    return _collect_worker_definitions(workspace)


def _external_worker_root_candidates(workspace: Path) -> list[Path]:
    return [
        workspace / ".admin" / "workers",
        workspace / "openSpec" / "workers",
    ]


def _load_external_worker_definition(definition_path: Path) -> dict[str, Any] | None:
    module_name = f"evo_external_worker_{definition_path.parent.name}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, definition_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:
        return None
    definition = getattr(module, "WORKER_DEFINITION", None)
    return definition if isinstance(definition, dict) else None


def load_external_worker_definitions(workspace: Path | None) -> dict[str, dict[str, Any]]:
    if not isinstance(workspace, Path):
        return {}
    loaded: dict[str, dict[str, Any]] = {}
    for root in _external_worker_root_candidates(workspace):
        if not root.is_dir():
            continue
        for worker_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            definition_path = worker_dir / "definition.py"
            if not definition_path.is_file():
                continue
            definition = _load_external_worker_definition(definition_path)
            if not isinstance(definition, dict):
                continue
            manifest = definition.get("manifest", {})
            worker_id = str(
                manifest.get("worker_id")
                or definition.get("worker_id")
                or worker_dir.name
            ).strip()
            if not worker_id:
                continue
            normalized_manifest = dict(manifest) if isinstance(manifest, dict) else {}
            normalized_manifest.setdefault("worker_id", worker_id)
            loaded[worker_id] = {
                **definition,
                "manifest": normalized_manifest,
                "source": "external",
                "definition_path": str(definition_path),
            }
    return loaded


def _collect_worker_definitions(workspace: Path | None) -> dict[str, dict[str, Any]]:
    return {
        **{
            worker_id: dict(definition)
            for worker_id, definition in BUILTIN_WORKER_DEFINITIONS.items()
        },
        **load_external_worker_definitions(workspace),
    }


def _builtin_worker_manifests(workspace: Path | None = None) -> dict[str, dict]:
    return {
        worker_id: {
            **dict(definition.get("manifest", {})),
            "source": definition.get("source", "external"),
            "definition_path": definition.get("definition_path"),
        }
        for worker_id, definition in _collect_worker_definitions(workspace).items()
    }


def _load_registry_config_payload(workspace: Path) -> dict:
    path = _worker_registry_file(workspace)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _enabled_worker_definitions_from_state(
    workers_state: dict[str, dict],
    definitions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        worker_id: definition
        for worker_id, definition in definitions.items()
        if bool((workers_state.get(worker_id) or {}).get("enabled", False))
    }


def _worker_registry_file(workspace: Path) -> Path:
    path = workspace / ".admin" / "worker_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def builtin_worker_manifests(workspace: Path | None = None) -> dict[str, dict]:
    return _builtin_worker_manifests(workspace)


def is_worker_enabled(workspace: Path, worker_id: str) -> bool:
    wid = str(worker_id or "").strip()
    if not wid:
        return False
    registry = load_worker_registry_config(workspace)
    workers = registry.get("workers", {}) if isinstance(registry.get("workers"), dict) else {}
    entry = workers.get(wid, {})
    if isinstance(entry, dict) and "enabled" in entry:
        return bool(entry.get("enabled"))
    manifest = _builtin_worker_manifests(workspace).get(wid, {})
    return bool(manifest.get("default_enabled"))


def _load_enabled_worker_definitions(workspace: Path) -> tuple[dict[str, dict], dict[str, dict[str, Any]]]:
    registry_config = load_worker_registry_config(workspace)
    workers_state = registry_config.get("workers", {})
    return workers_state, _enabled_worker_definitions_from_state(
        workers_state,
        _collect_worker_definitions(workspace),
    )


def load_worker_registry_config(workspace: Path) -> dict:
    manifests = _builtin_worker_manifests(workspace)
    data = _load_registry_config_payload(workspace)
    workers = data.get("workers", {}) if isinstance(data.get("workers"), dict) else {}
    normalized_workers: dict[str, dict] = {}
    for worker_id, manifest in manifests.items():
        current = workers.get(worker_id, {}) if isinstance(workers.get(worker_id), dict) else {}
        normalized_workers[worker_id] = {
            "enabled": bool(current.get("enabled", manifest.get("default_enabled", False))),
            "title": manifest.get("title"),
            "capability_type": manifest.get("capability_type"),
            "task_types": list(manifest.get("task_types", [])),
            "work_type_ids": list(manifest.get("work_type_ids", [])),
            "owned_modules": list(manifest.get("owned_modules", [])),
        }
    return {
        "updated_at": data.get("updated_at"),
        "workers": normalized_workers,
    }


def save_worker_registry_config(workspace: Path, payload: dict) -> dict:
    current = load_worker_registry_config(workspace)
    patch_workers = payload.get("workers", {}) if isinstance(payload, dict) else {}
    workers = current.get("workers", {})
    for worker_id, entry in patch_workers.items():
        if worker_id not in workers or not isinstance(entry, dict):
            continue
        if "enabled" in entry:
            workers[worker_id]["enabled"] = bool(entry.get("enabled"))
    saved = {
        "updated_at": datetime.now().isoformat(),
        "workers": workers,
    }
    _worker_registry_file(workspace).write_text(
        json.dumps(saved, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return saved


def load_worker_mission_kind_templates(workspace: Path | None) -> dict[str, dict[str, Any]]:
    templates: dict[str, dict[str, Any]] = {}
    for worker_id, definition in _collect_worker_definitions(workspace).items():
        payload = definition.get("mission_kind_template")
        if not isinstance(payload, dict):
            continue
        templates[str(worker_id)] = payload
    return templates


def build_mission_context_resolvers(workspace: Path) -> dict[str, Callable]:
    resolvers: dict[str, Callable] = {}
    for worker_id, definition in _collect_worker_definitions(workspace).items():
        resolver = definition.get("mission_context_resolver")
        if callable(resolver):
            resolvers[worker_id] = resolver
    return resolvers


def register_builtin_worker_handlers(
    *,
    task_queue,
    workspace: Path,
    decision_engine,
    extract_task_diagnostics: Callable[[object, dict], dict],
    finalize_operation_result: Callable[[object, dict], dict],
    run_probe_toutiao_connector: Callable[[Path, dict], dict],
    run_toutiao_analytics: Callable[[Path, dict], dict],
    run_toutiao_executor_cli: Callable[..., dict],
    load_recent_automation_experiences: Callable[..., list],
    trim_candidate_text: Callable[[str | None, int], str],
    run_comment_list: Callable[[Path, dict], dict],
    run_comment_reply: Callable[[Path, dict], dict],
    get_account_identity: Callable[[Path, str], dict],
) -> dict[str, dict]:
    registry_config = load_worker_registry_config(workspace)
    workers_state = registry_config.get("workers", {})
    enabled_definitions = _enabled_worker_definitions_from_state(
        workers_state,
        _collect_worker_definitions(workspace),
    )
    return {
        "updated_at": registry_config.get("updated_at"),
        "workers": {
            worker_id: {
                **dict(definition.get("manifest", {})),
                "enabled": True,
                "handler_count": len(handlers),
                "task_types": list(handlers.keys()),
                "source": definition.get("source", "external"),
                "definition_path": definition.get("definition_path"),
            }
            for worker_id, definition in enabled_definitions.items()
            for handlers in [definition["register_handlers"](
                task_queue=task_queue,
                workspace=workspace,
                decision_engine=decision_engine,
                extract_task_diagnostics=extract_task_diagnostics,
                finalize_operation_result=finalize_operation_result,
                run_probe_toutiao_connector=run_probe_toutiao_connector,
                run_toutiao_analytics=run_toutiao_analytics,
                run_toutiao_executor_cli=run_toutiao_executor_cli,
                load_recent_automation_experiences=load_recent_automation_experiences,
                trim_candidate_text=trim_candidate_text,
                run_comment_list=run_comment_list,
                run_comment_reply=run_comment_reply,
                get_account_identity=get_account_identity,
            )]
        },
        "available_workers": workers_state,
    }


def register_builtin_worker_mission_action_handlers(
    *,
    workspace: Path,
) -> dict[str, Callable]:
    _, enabled_definitions = _load_enabled_worker_definitions(workspace)
    return {
        worker_id: handler
        for worker_id, definition in enabled_definitions.items()
        for handler in [definition.get("mission_action_handler")]
        if callable(handler)
    }


def register_builtin_worker_mission_post_action_handlers(
    *,
    workspace: Path,
) -> dict[str, Callable]:
    _, enabled_definitions = _load_enabled_worker_definitions(workspace)
    return {
        worker_id: handler
        for worker_id, definition in enabled_definitions.items()
        for handler in [definition.get("mission_post_action_handler")]
        if callable(handler)
    }


def register_builtin_worker_mission_summary_handlers(
    *,
    workspace: Path,
) -> dict[str, Callable]:
    _, enabled_definitions = _load_enabled_worker_definitions(workspace)
    return {
        worker_id: handler
        for worker_id, definition in enabled_definitions.items()
        for handler in [definition.get("mission_summary_handler")]
        if callable(handler)
    }
