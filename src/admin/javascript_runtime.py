"""
兼容转发层。

新的 JavaScript 逆向工种实现已迁入 workers/javascript_reverse/runtime.py。
这里暂时保留，避免旧引用立刻失效。
"""

from workers.javascript_reverse.runtime import (
    auto_submit_javascript_research_tasks,
    create_analyze_handler,
    create_reconstruct_handler,
    discover_javascript_research_samples,
    find_recent_sample_task,
    infer_pre_execution_hints,
    latest_sample_task,
    resolve_javascript_mission_context,
    task_datetime,
    task_matches_research_sample,
)
