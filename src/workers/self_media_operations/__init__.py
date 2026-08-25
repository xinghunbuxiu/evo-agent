"""
自媒体运营工种。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

WORKER_MANIFEST = {
    "worker_id": "self_media_operations",
    "title": "自媒体运营师",
    "capability_type": "automation",
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
}

from .feedback import (
    process_toutiao_feedback,
    process_toutiao_feedback_collection,
)
from .content import (
    build_toutiao_content_strategy,
    build_toutiao_draft_content,
    run_toutiao_publish_draft,
)
from .monitor import (
    advance_background_self_media_autonomy_for_tenant,
    advance_background_feedback_monitor_for_tenant,
)
from .runtime import (
    build_operation_experience_timeline,
    build_self_media_operation_mission_summary,
    build_toutiao_operation_experience,
    handle_self_media_operation_mission_node,
    record_operation_experience,
    register_self_media_operation_handlers,
    summarize_toutiao_analytics_result,
)


def register_worker_handlers(
    *,
    task_queue,
    workspace: Path,
    finalize_operation_result: Callable[[object, dict], dict],
    run_probe_toutiao_connector: Callable[[Path, dict], dict],
    run_toutiao_analytics: Callable[[Path, dict], dict],
    run_toutiao_executor_cli: Callable[..., dict],
    load_recent_automation_experiences: Callable[..., list],
    trim_candidate_text: Callable[[str | None, int], str],
    run_comment_list: Callable[[Path, dict], dict],
    run_comment_reply: Callable[[Path, dict], dict],
    get_account_identity: Callable[[Path, str], dict],
    **_: Any,
) -> dict:
    return register_self_media_operation_handlers(
        task_queue=task_queue,
        workspace=workspace,
        finalize_operation_result=finalize_operation_result,
        run_probe_toutiao_connector=run_probe_toutiao_connector,
        run_toutiao_analytics=run_toutiao_analytics,
        run_toutiao_executor_cli=run_toutiao_executor_cli,
        load_recent_automation_experiences=load_recent_automation_experiences,
        trim_candidate_text=trim_candidate_text,
        run_comment_list=run_comment_list,
        run_comment_reply=run_comment_reply,
        get_account_identity=get_account_identity,
    )


WORKER_DEFINITION = {
    "manifest": WORKER_MANIFEST,
    "register_handlers": register_worker_handlers,
    "mission_action_handler": handle_self_media_operation_mission_node,
    "mission_summary_handler": build_self_media_operation_mission_summary,
}

__all__ = [
    "WORKER_DEFINITION",
    "WORKER_MANIFEST",
    "advance_background_self_media_autonomy_for_tenant",
    "advance_background_feedback_monitor_for_tenant",
    "build_toutiao_content_strategy",
    "build_toutiao_draft_content",
    "build_operation_experience_timeline",
    "build_self_media_operation_mission_summary",
    "build_toutiao_operation_experience",
    "handle_self_media_operation_mission_node",
    "process_toutiao_feedback",
    "process_toutiao_feedback_collection",
    "record_operation_experience",
    "register_worker_handlers",
    "register_self_media_operation_handlers",
    "run_toutiao_publish_draft",
    "summarize_toutiao_analytics_result",
]
