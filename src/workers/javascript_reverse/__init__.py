"""
JavaScript 逆向工种。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

WORKER_MANIFEST = {
    "worker_id": "javascript_reverse",
    "title": "JavaScript Reverse",
    "capability_type": "javascript_reverse",
    "work_type_ids": ["javascript", "javascript_reverse"],
    "task_types": ["analyze", "reconstruct"],
    "owned_modules": ["runtime"],
    "default_enabled": False,
}

from .runtime import (
    auto_submit_javascript_research_tasks,
    build_javascript_reverse_mission_summary,
    create_analyze_handler,
    create_reconstruct_handler,
    discover_javascript_research_samples,
    handle_javascript_reverse_mission_node,
    handle_javascript_reverse_post_action,
    latest_sample_task,
    register_javascript_reverse_handlers,
    resolve_javascript_mission_context,
)


def register_worker_handlers(
    *,
    task_queue,
    workspace: Path,
    decision_engine,
    extract_task_diagnostics: Callable[[object, dict], dict],
    **_: Any,
) -> dict:
    return register_javascript_reverse_handlers(
        task_queue=task_queue,
        workspace=workspace,
        decision_engine=decision_engine,
        extract_task_diagnostics=extract_task_diagnostics,
    )


WORKER_DEFINITION = {
    "manifest": WORKER_MANIFEST,
    "register_handlers": register_worker_handlers,
    "mission_action_handler": handle_javascript_reverse_mission_node,
    "mission_post_action_handler": handle_javascript_reverse_post_action,
    "mission_summary_handler": build_javascript_reverse_mission_summary,
}

__all__ = [
    "WORKER_DEFINITION",
    "WORKER_MANIFEST",
    "auto_submit_javascript_research_tasks",
    "build_javascript_reverse_mission_summary",
    "create_analyze_handler",
    "create_reconstruct_handler",
    "discover_javascript_research_samples",
    "handle_javascript_reverse_mission_node",
    "handle_javascript_reverse_post_action",
    "latest_sample_task",
    "register_worker_handlers",
    "register_javascript_reverse_handlers",
    "resolve_javascript_mission_context",
]
