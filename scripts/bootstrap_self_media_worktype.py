#!/usr/bin/env python3
"""
可选 · 研发冒烟：向 work_types 写入一条测试工种（正式环境应走 Admin「添加工种」/ PUT /api/work-types）。

用法:
  cd evo-mcp
  PYTHONPATH=src python3 scripts/bootstrap_self_media_worktype.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from work_types import load_work_types, save_work_types  # noqa: E402
from workers.registry import load_worker_registry_config, save_worker_registry_config  # noqa: E402

WORK_TYPE_ID = "self_media_operations"
WORKER_ID = "self_media_operations"

# 正式闭环参考工种：头条运营（非写死业务，仅为 M1 可演示的完整链路样板）
WORK_TYPE_ITEM = {
    "work_type_id": WORK_TYPE_ID,
    "title": "头条运营",
    "department_id": "operations",
    "department_label": "运营",
    "status": "active",
    "capability_type": "automation",
    "mission_kind": "automation_operation",
    "worker_id": WORKER_ID,
    "finance_project_id": WORK_TYPE_ID,
    "enabled": True,
    "goal_schema": {
        "default_goal": "以头条号为核心渠道，稳定产出内容、回收阅读与收益数据，并形成可复用的运营经验。",
        "deliverables": [
            "账号登录与环境验证通过（operation_validate）",
            "阅读/互动/收益数据回收并落盘财务（operation_analytics）",
            "至少一条可发布草稿或已发布内容（operation_publish_draft）",
            "反馈回收与育成师复盘确认（operation_feedback_collect → approve）",
        ],
    },
    "input_schema": {
        "required": ["topic", "account_id"],
        "optional": ["title", "content_direction", "publish_mode"],
    },
    "closure_loop": {
        "label": "头条运营正式闭环",
        "channel": "toutiao",
        "steps": [
            "公司设置启用本工种与执行器（重启 Admin）",
            "育成师建档并将员工绑定到 self_media_operations",
            "派首个正式任务：validate → analytics → publish_draft → feedback",
            "财务看板出现收益信号后记录经营决策",
        ],
    },
    "enabled_packages": [],
}


def _merge_work_type_item(existing: dict) -> dict:
    merged = {**existing}
    for key, value in WORK_TYPE_ITEM.items():
        if key == "updated_at":
            continue
        if key in {"goal_schema", "input_schema", "closure_loop"}:
            if not isinstance(merged.get(key), dict) or not merged.get(key):
                merged[key] = value
            elif key == "goal_schema":
                goal = merged.get("goal_schema") if isinstance(merged.get("goal_schema"), dict) else {}
                if not str(goal.get("default_goal") or "").strip():
                    goal["default_goal"] = value.get("default_goal", "")
                if not goal.get("deliverables"):
                    goal["deliverables"] = value.get("deliverables", [])
                merged["goal_schema"] = goal
            continue
        if not str(merged.get(key) or "").strip() and value:
            merged[key] = value
    merged["updated_at"] = datetime.now().isoformat()
    return merged


def main() -> int:
    workspace = ROOT

    registry = load_worker_registry_config(workspace)
    workers = registry.get("workers", {}) if isinstance(registry.get("workers"), dict) else {}
    entry = workers.get(WORKER_ID, {}) if isinstance(workers.get(WORKER_ID), dict) else {}
    entry["enabled"] = True
    workers[WORKER_ID] = entry
    save_worker_registry_config(workspace, {"workers": {WORKER_ID: {"enabled": True}}})

    work_types = load_work_types(workspace)
    items = work_types.get("items", []) if isinstance(work_types.get("items"), list) else []
    next_items = []
    found = False
    for item in items:
        if not isinstance(item, dict):
            next_items.append(item)
            continue
        if str(item.get("work_type_id") or "").strip() != WORK_TYPE_ID:
            next_items.append(item)
            continue
        found = True
        next_items.append(_merge_work_type_item(item))

    if not found:
        next_items.append({
            **WORK_TYPE_ITEM,
            "updated_at": datetime.now().isoformat(),
        })

    save_work_types(workspace, {"version": work_types.get("version", 1), "items": next_items})

    print(json.dumps({
        "ok": True,
        "worker_enabled": True,
        "work_type_registered": True,
        "work_type_id": WORK_TYPE_ID,
        "mission_kind": WORK_TYPE_ITEM["mission_kind"],
        "next_steps": [
            "重启 Admin 使 operation_* handler 注册生效",
            "公司空间或育成官建档后跳转派任务页",
            "PYTHONPATH=src python3 scripts/m1_ops_check.py --with-worker-smoke",
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
