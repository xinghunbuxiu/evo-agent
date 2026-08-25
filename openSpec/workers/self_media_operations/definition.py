"""
测试工种：自媒体运营师（头条 executor 为测试插件，默认不启用）。

用户在平台添加工种并启用本 Worker 后，由内置育成师创建岗位成员并驱动任务队列。
"""

from __future__ import annotations

import sys
from pathlib import Path

_EVO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _EVO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from workers.self_media_operations import (  # noqa: E402
    build_self_media_operation_mission_summary,
    handle_self_media_operation_mission_node,
    register_worker_handlers,
)

WORKER_DEFINITION = {
    "manifest": {
        "worker_id": "self_media_operations",
        "title": "自媒体运营师",
        "capability_type": "automation",
        "experience_domain": "self_media",
        "work_type_ids": ["self_media_operations", "toutiao_operations"],
        "task_types": [
            "operation_validate",
            "operation_analytics",
            "operation_publish_draft",
            "operation_feedback_review",
            "operation_feedback_collect",
        ],
        "owned_modules": ["content", "feedback", "monitor", "runtime"],
        "default_enabled": False,
    },
    "register_handlers": register_worker_handlers,
    "mission_action_handler": handle_self_media_operation_mission_node,
    "mission_summary_handler": build_self_media_operation_mission_summary,
}
