"""
测试工种：JavaScript 逆向（默认关闭）。

用户在公司空间启用 Worker 并配置 project package 后，才注册 analyze/reconstruct 与后台样本调研。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_EVO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _EVO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from workers.javascript_reverse import (  # noqa: E402
    register_worker_handlers,
)
from workers.javascript_reverse.runtime import (  # noqa: E402
    build_javascript_reverse_mission_summary,
    handle_javascript_reverse_mission_node,
    handle_javascript_reverse_post_action,
    resolve_javascript_mission_context,
)

JAVASCRIPT_REVERSE_MISSION_KIND_TEMPLATE: dict[str, Any] = {
    "title": "JavaScript Reverse Mission",
    "description": "面向 JS 包/页面的逆向分析、结构恢复、验证与经验沉淀。",
    "primary_capability_type": "javascript_reverse",
    "delivery": [
        "可解释的分析结论",
        "可接手的项目骨架或重建结果",
        "经验、策略和验证记录",
    ],
    "tasks": [
        {
            "id": "identify_target",
            "title": "识别目标形态",
            "objective": "确定入口资源、框架、打包器和运行边界。",
            "task_type": "analyze",
            "capability_type": "javascript_reverse",
            "acceptance": "能说明 bundle 来源、框架线索和后续切入点。",
        },
        {
            "id": "recover_structure",
            "title": "恢复项目结构",
            "objective": "把页面、组件、路由、接口和资源组织成可接手骨架。",
            "task_type": "reconstruct",
            "capability_type": "javascript_reverse",
            "acceptance": "输出可阅读、可继续改造的项目骨架。",
        },
        {
            "id": "validate_result",
            "title": "验证恢复结果",
            "objective": "检查可运行性、结构合理性和关键页面映射准确性。",
            "task_type": "validate",
            "capability_type": "javascript_reverse",
            "acceptance": "明确当前结果是否可交付、哪里还需继续研究。",
        },
        {
            "id": "promote_knowledge",
            "title": "沉淀成长资产",
            "objective": "把有效结论沉淀成经验、技能和策略，供后续复用。",
            "task_type": "promote",
            "capability_type": "javascript_reverse",
            "acceptance": "至少形成经验记录，稳定后可晋升为技能或策略。",
        },
    ],
}

WORKER_DEFINITION = {
    "manifest": {
        "worker_id": "javascript_reverse",
        "title": "JavaScript 逆向",
        "capability_type": "javascript_reverse",
        "experience_domain": "javascript",
        "work_type_ids": ["javascript", "javascript_reverse"],
        "task_types": ["analyze", "reconstruct"],
        "owned_modules": ["runtime"],
        "default_enabled": False,
    },
    "register_handlers": register_worker_handlers,
    "mission_action_handler": handle_javascript_reverse_mission_node,
    "mission_post_action_handler": handle_javascript_reverse_post_action,
    "mission_summary_handler": build_javascript_reverse_mission_summary,
    "mission_context_resolver": resolve_javascript_mission_context,
    "mission_kind_template": JAVASCRIPT_REVERSE_MISSION_KIND_TEMPLATE,
}
