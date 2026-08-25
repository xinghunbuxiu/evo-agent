"""
Worker 入口装配运行时：负责内置工种 handler 注册与队列接线。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from workers import register_builtin_worker_handlers


def create_worker_bootstrap_runtime_bindings(
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
) -> dict[str, object]:
    worker_runtime = register_builtin_worker_handlers(
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
    )
    task_queue.register_handler("sync_cloud", lambda t: {"status": "todo"})
    return {
        "worker_runtime": worker_runtime,
    }


__all__ = ["create_worker_bootstrap_runtime_bindings"]
