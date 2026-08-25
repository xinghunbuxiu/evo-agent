"""
工种定义层。

人定义工种边界、输入、目标与挂载能力包；
智脑基于工种接管拆解、执行、学习与成长。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _work_types_file(workspace: Path) -> Path:
    path = workspace / ".admin" / "work_types.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _default_work_types() -> Dict[str, Any]:
    return {
        "version": 1,
        "items": [],
    }


def load_work_types(workspace: Path) -> Dict[str, Any]:
    path = _work_types_file(workspace)
    defaults = _default_work_types()
    if not path.is_file():
        payload = defaults
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = defaults
    if not isinstance(payload, dict):
        payload = defaults
    items = payload.get("items", [])
    if not isinstance(items, list):
        items = defaults["items"]
    item_map: Dict[str, Any] = {}
    ordered_ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        work_type_id = str(item.get("work_type_id") or "").strip()
        if not work_type_id:
            continue
        item_map[work_type_id] = item
        ordered_ids.append(work_type_id)
    for default_item in defaults["items"]:
        if not isinstance(default_item, dict):
            continue
        work_type_id = str(default_item.get("work_type_id") or "").strip()
        if not work_type_id:
            continue
        if work_type_id not in item_map:
            item_map[work_type_id] = default_item
            ordered_ids.append(work_type_id)
    return {
        "version": payload.get("version", 1),
        "items": [item_map[work_type_id] for work_type_id in ordered_ids if work_type_id in item_map],
    }


def save_work_types(workspace: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        "version": payload.get("version", 1) if isinstance(payload, dict) else 1,
        "items": [
            item for item in (payload.get("items", []) if isinstance(payload, dict) else [])
            if isinstance(item, dict)
        ],
    }
    _work_types_file(workspace).write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return normalized


def get_work_type(workspace: Path, work_type_id: str) -> Dict[str, Any] | None:
    target = str(work_type_id or "").strip()
    if not target:
        return None
    for item in load_work_types(workspace).get("items", []):
        if str(item.get("work_type_id") or "").strip() == target:
            return item
    return None


def resolve_work_type_context(
    workspace: Path,
    *,
    work_type_id: str | None,
    goal: str,
    mission_kind: str | None,
    context: Dict[str, Any] | None,
) -> Dict[str, Any]:
    context = dict(context or {})
    work_type = get_work_type(workspace, work_type_id or "")
    if not work_type:
        return {
            "goal": goal,
            "mission_kind": mission_kind,
            "context": context,
            "work_type": None,
        }
    resolved_goal = goal or str(
        ((work_type.get("goal_schema") or {}).get("default_goal"))
        or ""
    ).strip()
    resolved_mission_kind = mission_kind or str(work_type.get("mission_kind") or "").strip() or None
    context.setdefault("work_type_id", work_type.get("work_type_id"))
    context.setdefault("capability_type", work_type.get("capability_type"))
    context.setdefault("enabled_packages", work_type.get("enabled_packages", []))
    return {
        "goal": resolved_goal,
        "mission_kind": resolved_mission_kind,
        "context": context,
        "work_type": work_type,
    }


def validate_work_type_request(
    *,
    work_type: Dict[str, Any] | None,
    context: Dict[str, Any] | None,
) -> Dict[str, Any]:
    context = context if isinstance(context, dict) else {}
    if not isinstance(work_type, dict):
        return {
            "ok": True,
            "missing_required_inputs": [],
            "warnings": [],
        }
    input_schema = work_type.get("input_schema", {}) if isinstance(work_type.get("input_schema"), dict) else {}
    required = input_schema.get("required", []) if isinstance(input_schema.get("required"), list) else []
    missing = [
        key for key in required
        if not str(context.get(key) or "").strip()
    ]
    warnings: list[str] = []
    enabled_packages = work_type.get("enabled_packages", [])
    if not isinstance(enabled_packages, list) or not enabled_packages:
        warnings.append("当前工种还没有绑定项目能力包，智脑可能只能做通用分析")
    return {
        "ok": len(missing) == 0,
        "missing_required_inputs": missing,
        "warnings": warnings,
    }


def summarize_work_type(work_type: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(work_type, dict):
        return None
    goal_schema = work_type.get("goal_schema", {}) if isinstance(work_type.get("goal_schema"), dict) else {}
    knowledge_policy = work_type.get("knowledge_policy", {}) if isinstance(work_type.get("knowledge_policy"), dict) else {}
    input_schema = work_type.get("input_schema", {}) if isinstance(work_type.get("input_schema"), dict) else {}
    return {
        "work_type_id": work_type.get("work_type_id"),
        "type_key": work_type.get("type_key") or work_type.get("work_type_id"),
        "title": work_type.get("title"),
        "status": work_type.get("status"),
        "department_id": work_type.get("department_id"),
        "department_label": work_type.get("department_label"),
        "capability_type": work_type.get("capability_type"),
        "mission_kind": work_type.get("mission_kind"),
        "enabled_packages": work_type.get("enabled_packages", []),
        "required_inputs": input_schema.get("required", []),
        "optional_inputs": input_schema.get("optional", []),
        "deliverables": goal_schema.get("deliverables", []),
        "default_goal": goal_schema.get("default_goal"),
        "knowledge_policy": knowledge_policy,
    }


__all__ = [
    "load_work_types",
    "save_work_types",
    "get_work_type",
    "resolve_work_type_context",
    "summarize_work_type",
    "validate_work_type_request",
]
