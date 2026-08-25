"""
项目级外部工种示例：Android。

当前只提供定义骨架，默认不启用。
后续可扩展 adb / frida / dump / replay 等能力。
"""

from __future__ import annotations

from typing import Any


def register_worker_handlers(**_: Any) -> dict[str, object]:
    return {}


def handle_worker_mission_node(**_: Any) -> dict[str, Any]:
    return {
        "action_type": "planned_only",
        "status": "planned_only",
        "detail": "Android 工种模板已接入，等待补充设备连接、注入、分析和验证逻辑。",
        "next_actions": [
            "补充 android/runtime.py 并注册 dump/inject/replay 等 handlers",
            "补充 mission 节点拆解，把目标分解为设备准备、采样、验证、沉淀",
        ],
    }


def build_worker_mission_summary(*, mission_run: dict, refreshed_actions: list[dict]) -> dict[str, Any]:
    return {
        "domain": "android",
        "status": mission_run.get("status"),
        "action_count": len(refreshed_actions),
        "recommended_next_actions": [
            "接入 adb / frida / dump 能力",
            "补充 Android 工种的学习闭环和经验晋升逻辑",
        ],
    }


WORKER_DEFINITION = {
    "manifest": {
        "worker_id": "android",
        "title": "Android",
        "capability_type": "android_reverse",
        "work_type_ids": ["android", "android_reverse"],
        "task_types": ["android_dump", "android_inject", "android_validate"],
        "owned_modules": ["runtime", "reverse", "learning"],
        "default_enabled": False,
    },
    "register_handlers": register_worker_handlers,
    "mission_action_handler": handle_worker_mission_node,
    "mission_summary_handler": build_worker_mission_summary,
}
