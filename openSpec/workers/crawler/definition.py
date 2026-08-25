"""
项目级外部工种示例：Crawler。

当前先作为模板接入系统，默认不启用。
后续可在同目录补 runtime / learning / review 逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def register_worker_handlers(**_: Any) -> dict[str, object]:
    # 模板工种先返回空 handlers，确保只接入注册表，不影响现有运行链路。
    return {}


def handle_worker_mission_node(**_: Any) -> dict[str, Any]:
    return {
        "action_type": "planned_only",
        "status": "planned_only",
        "detail": "Crawler 工种模板已接入，等待补充具体 runtime handlers。",
        "next_actions": [
            "补充 crawler/runtime.py 并注册 crawl_collect 等 task handlers",
            "补充 mission_action_handler，把目标拆成抓取、解析、验证等节点",
        ],
    }


def build_worker_mission_summary(*, mission_run: dict, refreshed_actions: list[dict]) -> dict[str, Any]:
    return {
        "domain": "crawler",
        "status": mission_run.get("status"),
        "action_count": len(refreshed_actions),
        "recommended_next_actions": [
            "为 crawler 工种增加真实 task handlers",
            "补充抓取结果验证与经验沉淀逻辑",
        ],
    }


WORKER_DEFINITION = {
    "manifest": {
        "worker_id": "crawler",
        "title": "Crawler",
        "capability_type": "automation",
        "work_type_ids": ["crawler", "web_crawler"],
        "task_types": ["crawl_collect", "crawl_parse", "crawl_validate"],
        "owned_modules": ["runtime", "learning"],
        "default_enabled": False,
    },
    "register_handlers": register_worker_handlers,
    "mission_action_handler": handle_worker_mission_node,
    "mission_summary_handler": build_worker_mission_summary,
}
