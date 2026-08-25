"""
自媒体运营工种 - 后台观察域。

计划承接:
- 评论轮询
- 自动互动调度
- 后台自治状态同步
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from admin.worker_route_runtime import (
    resolve_autonomy_job_tag,
    resolve_primary_worker_id,
    worker_uses_self_media_tenant_bucket,
)


def _list_background_tasks(task_queue, tenant_id: str, *, task_type: str, source: str) -> list:
    items = []
    for task in task_queue.list_tasks(tenant_id=tenant_id, limit=80):
        if getattr(task, "type", "") != task_type:
            continue
        payload = task.payload if isinstance(task.payload, dict) else {}
        if str(payload.get("_source") or "").strip() != source:
            continue
        items.append(task)
    return items


def _latest_background_task(task_queue, tenant_id: str, *, task_type: str, source: str):
    items = _list_background_tasks(task_queue, tenant_id, task_type=task_type, source=source)
    return items[0] if items else None


def _has_active_background_task(task_queue, tenant_id: str, *, task_type: str, source: str, pending_status, running_status) -> bool:
    for status in (pending_status, running_status):
        tasks = task_queue.list_tasks(tenant_id=tenant_id, status=status, limit=80)
        for task in tasks:
            if getattr(task, "type", "") != task_type:
                continue
            payload = task.payload if isinstance(task.payload, dict) else {}
            if str(payload.get("_source") or "").strip() == source:
                return True
    return False


def _latest_successful_background_task(task_queue, tenant_id: str, *, task_type: str, source: str):
    for task in _list_background_tasks(task_queue, tenant_id, task_type=task_type, source=source):
        if getattr(getattr(task, "status", None), "value", "") == "success":
            return task
    return None


def _latest_successful_self_media_runtime_task(task_queue, tenant_id: str):
    candidates: list = []
    task_specs = [
        ("operation_publish_draft", "background_self_media_autonomy_draft"),
        ("operation_analytics", "background_self_media_autonomy_analytics"),
        ("operation_feedback_collect", "background_feedback_monitor"),
        ("operation_publish_draft", "background_feedback_followup"),
    ]
    for task_type, source in task_specs:
        task = _latest_successful_background_task(
            task_queue,
            tenant_id,
            task_type=task_type,
            source=source,
        )
        if task is not None:
            candidates.append(task)
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: str(
            getattr(item, "completed_at", None)
            or getattr(item, "started_at", None)
            or getattr(item, "created_at", None)
            or ""
        ),
        reverse=True,
    )
    return candidates[0]


def _find_member_by_id(runtime: dict, member_id: str) -> dict | None:
    child_members = runtime.get("child_members", {}) if isinstance(runtime.get("child_members"), dict) else {}
    items = child_members.get("items", []) if isinstance(child_members.get("items"), list) else []
    target = str(member_id or "").strip()
    for item in items:
        if isinstance(item, dict) and str(item.get("member_id") or "").strip() == target:
            return item
    return None


def _resolve_self_media_member_state_key(runtime: dict, workspace: Path) -> str:
    child_members = runtime.get("child_members", {}) if isinstance(runtime.get("child_members"), dict) else {}
    selected_member_id = str(child_members.get("selected_member_id") or "").strip()
    items = child_members.get("items", []) if isinstance(child_members.get("items"), list) else []
    selected_member = next(
        (
            item for item in items
            if isinstance(item, dict) and str(item.get("member_id") or "").strip() == selected_member_id
        ),
        None,
    )
    candidates = []
    if isinstance(selected_member, dict):
        candidates.append(selected_member)
    candidates.extend(item for item in items if isinstance(item, dict) and item is not selected_member)
    for item in candidates:
        worker_id = resolve_primary_worker_id(workspace, member=item)
        if worker_id and worker_uses_self_media_tenant_bucket(worker_id):
            return str(item.get("member_id") or "default").strip() or "default"
    return "default"


def _has_active_background_feedback_task(task_queue, tenant_id: str, *, pending_status, running_status) -> bool:
    for status in (pending_status, running_status):
        tasks = task_queue.list_tasks(tenant_id=tenant_id, status=status, limit=50)
        for task in tasks:
            if getattr(task, "type", "") == "operation_feedback_collect":
                payload = task.payload if isinstance(task.payload, dict) else {}
                if payload.get("_source") == "background_feedback_monitor":
                    return True
    return False


def _latest_background_feedback_task(task_queue, tenant_id: str):
    tasks = task_queue.list_tasks(tenant_id=tenant_id, limit=50)
    for task in tasks:
        if getattr(task, "type", "") != "operation_feedback_collect":
            continue
        payload = task.payload if isinstance(task.payload, dict) else {}
        if payload.get("_source") == "background_feedback_monitor":
            return task
    return None


def _list_background_followup_draft_tasks(task_queue, tenant_id: str) -> list:
    tasks = task_queue.list_tasks(tenant_id=tenant_id, limit=50)
    items = []
    for task in tasks:
        if getattr(task, "type", "") != "operation_publish_draft":
            continue
        payload = task.payload if isinstance(task.payload, dict) else {}
        if payload.get("_source") == "background_feedback_followup":
            items.append(task)
    return items


def _has_active_background_followup_draft_task(task_queue, tenant_id: str, *, pending_status, running_status) -> bool:
    for status in (pending_status, running_status):
        tasks = task_queue.list_tasks(tenant_id=tenant_id, status=status, limit=50)
        for task in tasks:
            if getattr(task, "type", "") != "operation_publish_draft":
                continue
            payload = task.payload if isinstance(task.payload, dict) else {}
            if payload.get("_source") == "background_feedback_followup":
                return True
    return False


def _sync_followup_strategy_runs_for_tenant(
    *,
    tenant_id: str,
    task_queue,
    tenant_state: dict,
    followup_observations: list[dict] | None = None,
) -> None:
    runs = tenant_state.get("followup_strategy_runs", []) if isinstance(tenant_state.get("followup_strategy_runs"), list) else []
    run_map = {
        str(item.get("task_id") or ""): dict(item)
        for item in runs
        if isinstance(item, dict) and str(item.get("task_id") or "").strip()
    }
    for task in _list_background_followup_draft_tasks(task_queue, tenant_id):
        task_id = str(getattr(task, "id", "") or "")
        if not task_id or task_id in run_map:
            continue
        payload = task.payload if isinstance(task.payload, dict) else {}
        result = task.result if isinstance(task.result, dict) else {}
        draft_generation = result.get("draft_generation", {}) if isinstance(result.get("draft_generation"), dict) else {}
        strategy = draft_generation.get("strategy", {}) if isinstance(draft_generation.get("strategy"), dict) else {}
        run_map[task_id] = {
            "task_id": task_id,
            "comment_id": str(payload.get("_followup_comment_id") or "").strip(),
            "content_mode": str(
                payload.get("content_mode")
                or strategy.get("response_mode")
                or "general"
            ).strip(),
            "topic": str(payload.get("topic") or "").strip(),
            "feedback_goal_hint": str(payload.get("feedback_goal_hint") or "").strip(),
            "strategy_title": str(strategy.get("title") or "").strip(),
            "strategy_style": str(strategy.get("style_hint") or "").strip(),
            "status": "waiting_observation",
            "continued_cycles": 0,
            "created_at": getattr(task, "created_at", None),
            "observed_at": None,
        }

    observation_map = {
        str(item.get("comment_id") or "").strip(): item
        for item in (followup_observations or [])
        if isinstance(item, dict) and str(item.get("comment_id") or "").strip()
    }
    for task_id, run in list(run_map.items()):
        comment_id = str(run.get("comment_id") or "").strip()
        observation = observation_map.get(comment_id)
        if not isinstance(observation, dict):
            continue
        status = str(observation.get("status") or "").strip()
        run["last_observation_summary"] = str(observation.get("summary") or "").strip()
        run["observed_at"] = datetime.now().isoformat()
        if status == "continued_interaction":
            run["continued_cycles"] = int(run.get("continued_cycles") or 0) + 1
            run["status"] = "improved"
        elif status:
            run["status"] = "waiting_observation"
        run_map[task_id] = run

    ordered_runs = sorted(
        run_map.values(),
        key=lambda item: str(item.get("created_at") or ""),
        reverse=True,
    )[:20]
    tenant_state["followup_strategy_runs"] = ordered_runs

    scoreboard: dict[str, dict] = {}
    for run in ordered_runs:
        mode = str(run.get("content_mode") or "general").strip() or "general"
        current = scoreboard.setdefault(mode, {
            "content_mode": mode,
            "total_runs": 0,
            "improved_runs": 0,
            "waiting_runs": 0,
            "continued_cycles": 0,
        })
        current["total_runs"] += 1
        current["continued_cycles"] += int(run.get("continued_cycles") or 0)
        if str(run.get("status") or "") == "improved":
            current["improved_runs"] += 1
        else:
            current["waiting_runs"] += 1
    tenant_state["followup_strategy_scoreboard"] = list(scoreboard.values())[:8]


def _submit_background_followup_draft_for_tenant(
    *,
    tenant_id: str,
    task_queue,
    feedback_monitor: dict,
    tenant_state: dict,
    continued_observations: list[dict],
    task_priority_normal,
    pending_status,
    running_status,
) -> None:
    if not continued_observations:
        return
    if not bool(feedback_monitor.get("auto_draft_from_followup", True)):
        return
    if _has_active_background_followup_draft_task(
        task_queue,
        tenant_id,
        pending_status=pending_status,
        running_status=running_status,
    ):
        return

    tracked_replies = tenant_state.get("tracked_replies", []) if isinstance(tenant_state.get("tracked_replies"), list) else []
    tracked_map = {}
    for item in tracked_replies:
        if not isinstance(item, dict):
            continue
        comment_id = str(item.get("comment_id") or "").strip()
        if comment_id:
            tracked_map[comment_id] = item

    target_observation = next(
        (
            item for item in continued_observations
            if isinstance(item, dict) and str(item.get("comment_id") or "").strip()
        ),
        None,
    )
    if not isinstance(target_observation, dict):
        return
    comment_id = str(target_observation.get("comment_id") or "").strip()
    tracked = tracked_map.get(comment_id, {})
    if not isinstance(tracked, dict):
        return

    draft_key = f"{comment_id}:{str(target_observation.get('summary') or '').strip()}"
    if str(tenant_state.get("last_followup_draft_key") or "") == draft_key:
        return

    category = str(tracked.get("category") or "").strip().lower()
    content_mode = "follow_response"
    if category in {"worth_content", "question", "request"}:
        content_mode = "content_response"
    payload = {
        "channel": "toutiao",
        "account_id": str(tenant_state.get("account_id") or "default"),
        "topic": str(tenant_state.get("topic") or tracked.get("article_title") or "自媒体运营"),
        "deliverable_goal": "针对已经被激活的互动线程，生成一条承接讨论的草稿",
        "goal_hint": str(target_observation.get("summary") or "优先承接已发酵的评论线程"),
        "feedback_goal_hint": str(tracked.get("feedback_text") or target_observation.get("summary") or "").strip(),
        "content_mode": content_mode,
        "audience_hint": "已产生互动兴趣的读者",
        "_source": "background_feedback_followup",
        "_followup_comment_id": comment_id,
        "_followup_summary": str(target_observation.get("summary") or "").strip(),
    }
    created = task_queue.submit(
        task_type="operation_publish_draft",
        payload=payload,
        priority=task_priority_normal,
        tenant_id=tenant_id,
    )
    tenant_state["last_followup_draft_key"] = draft_key
    tenant_state["last_followup_draft_task_id"] = created.id
    tenant_state["last_followup_draft_at"] = datetime.now().isoformat()


def advance_background_feedback_monitor_for_tenant(
    *,
    workspace: Path,
    tenant_id: str,
    task_queue,
    runtime: dict,
    normalize_feedback_monitor_runtime: Callable[[dict | None], dict],
    task_priority_normal,
    pending_status,
    running_status,
) -> None:
    feedback_monitor = normalize_feedback_monitor_runtime(runtime.get("feedback_monitor"))
    if not feedback_monitor.get("enabled", True):
        runtime["feedback_monitor"] = feedback_monitor
        return

    tenants_state = feedback_monitor.get("tenants", {})
    if not isinstance(tenants_state, dict):
        tenants_state = {}
    tenant_state = tenants_state.get(tenant_id, {})
    if not isinstance(tenant_state, dict):
        tenant_state = {}

    latest_task = _latest_background_feedback_task(task_queue, tenant_id)
    if latest_task:
        latest_result = latest_task.result if isinstance(latest_task.result, dict) else {}
        collection = latest_result.get("feedback_collection", {}) if isinstance(latest_result.get("feedback_collection"), dict) else {}
        tenant_state["last_task_id"] = latest_task.id
        tenant_state["last_task_status"] = latest_task.status.value
        tenant_state["last_checked_at"] = latest_task.completed_at or latest_task.started_at or latest_task.created_at
        if collection:
            tenant_state["last_feedback_summary"] = {
                "headline": collection.get("headline"),
                "category_counts": collection.get("category_counts"),
                "recommended_actions": collection.get("recommended_actions"),
                "skipped_self_authored_count": collection.get("skipped_self_authored_count"),
            }
            if isinstance(collection.get("updated_tracked_replies"), list):
                tenant_state["tracked_replies"] = collection.get("updated_tracked_replies", [])[:12]
            if isinstance(collection.get("followup_observations"), list):
                tenant_state["followup_observations"] = collection.get("followup_observations", [])[:6]
                _sync_followup_strategy_runs_for_tenant(
                    tenant_id=tenant_id,
                    task_queue=task_queue,
                    tenant_state=tenant_state,
                    followup_observations=collection.get("followup_observations", []),
                )
                continued_observations = [
                    item for item in collection.get("followup_observations", [])
                    if isinstance(item, dict) and str(item.get("status") or "") == "continued_interaction"
                ]
                _submit_background_followup_draft_for_tenant(
                    tenant_id=tenant_id,
                    task_queue=task_queue,
                    feedback_monitor=feedback_monitor,
                    tenant_state=tenant_state,
                    continued_observations=continued_observations,
                    task_priority_normal=task_priority_normal,
                    pending_status=pending_status,
                    running_status=running_status,
                )
        elif latest_result.get("message"):
            tenant_state["last_feedback_summary"] = {
                "headline": latest_result.get("message"),
            }
    else:
        _sync_followup_strategy_runs_for_tenant(
            tenant_id=tenant_id,
            task_queue=task_queue,
            tenant_state=tenant_state,
        )

    if isinstance(tenant_state.get("followup_strategy_scoreboard"), list) and tenant_state.get("last_feedback_summary"):
        tenant_state["last_feedback_summary"]["strategy_scoreboard"] = tenant_state.get("followup_strategy_scoreboard", [])[:4]

    if _has_active_background_feedback_task(
        task_queue,
        tenant_id,
        pending_status=pending_status,
        running_status=running_status,
    ):
        tenants_state[tenant_id] = tenant_state
        feedback_monitor["tenants"] = tenants_state
        runtime["feedback_monitor"] = feedback_monitor
        return

    interval_seconds = int(feedback_monitor.get("interval_seconds", 1800) or 1800)
    last_submitted_at = str(tenant_state.get("last_submitted_at") or "").strip()
    if last_submitted_at:
        try:
            next_due = datetime.fromisoformat(last_submitted_at) + timedelta(seconds=interval_seconds)
            if datetime.now() < next_due:
                tenants_state[tenant_id] = tenant_state
                feedback_monitor["tenants"] = tenants_state
                runtime["feedback_monitor"] = feedback_monitor
                return
        except Exception:
            pass

    created = task_queue.submit(
        task_type="operation_feedback_collect",
        payload={
            "channel": "toutiao",
            "account_id": str(tenant_state.get("account_id") or "default"),
            "topic": str(tenant_state.get("topic") or "自媒体运营"),
            "max_comments": feedback_monitor.get("max_comments", 6),
            "auto_reply_feedback": feedback_monitor.get("auto_reply_feedback", False),
            "reply_limit": feedback_monitor.get("reply_limit", 2),
            "with_replies": True,
            "_tracked_replies": tenant_state.get("tracked_replies", []),
            "_source": "background_feedback_monitor",
        },
        priority=task_priority_normal,
        tenant_id=tenant_id,
    )
    tenant_state["last_submitted_at"] = datetime.now().isoformat()
    tenant_state["last_task_id"] = created.id
    tenant_state["last_task_status"] = "pending"
    tenants_state[tenant_id] = tenant_state
    feedback_monitor["tenants"] = tenants_state
    runtime["feedback_monitor"] = feedback_monitor


def advance_background_self_media_autonomy_for_tenant(
    *,
    workspace: Path,
    tenant_id: str,
    task_queue,
    runtime: dict,
    get_account_identity: Callable[[Path, str], dict],
    get_git_export_status: Callable[[str], dict],
    task_priority_normal,
    pending_status,
    running_status,
) -> None:
    self_media_runtime = runtime.get("self_media", {}) if isinstance(runtime.get("self_media"), dict) else {}
    tenants_state = self_media_runtime.get("tenants", {}) if isinstance(self_media_runtime.get("tenants"), dict) else {}
    member_state_key = _resolve_self_media_member_state_key(runtime, workspace)
    member = _find_member_by_id(runtime, member_state_key)
    autonomy_job = resolve_autonomy_job_tag(workspace, member=member)
    tenant_state = tenants_state.get(member_state_key, {})
    if not isinstance(tenant_state, dict):
        tenant_state = tenants_state.get(tenant_id, {})
    if not isinstance(tenant_state, dict):
        tenant_state = tenants_state.get("default", {})
    if not isinstance(tenant_state, dict):
        tenant_state = {}

    tenant_state.setdefault("account_id", "default")
    tenant_state.setdefault("topic", "自媒体运营")
    tenant_state.setdefault("target_outcome", "跑通首篇文章草稿并进入持续复盘")
    tenant_state["last_decision_at"] = datetime.now().isoformat()
    tenant_state["git_export"] = get_git_export_status(tenant_id)
    latest_runtime_task = _latest_successful_self_media_runtime_task(task_queue, tenant_id)
    if latest_runtime_task is not None:
        latest_result = latest_runtime_task.result if isinstance(latest_runtime_task.result, dict) else {}
        last_export = latest_result.get("git_export", {}) if isinstance(latest_result.get("git_export"), dict) else {}
        if last_export:
            current_git_export = tenant_state.get("git_export", {}) if isinstance(tenant_state.get("git_export"), dict) else {}
            current_git_export["last_export"] = {
                "task_id": getattr(latest_runtime_task, "id", None),
                "task_type": getattr(latest_runtime_task, "type", None),
                "completed_at": getattr(latest_runtime_task, "completed_at", None),
                **last_export,
            }
            tenant_state["git_export"] = current_git_export

    account_id = str(tenant_state.get("account_id") or "default").strip() or "default"
    account_state = get_account_identity(workspace, account_id)
    tenant_state["account_snapshot"] = {
        "account_id": account_id,
        "display_name": account_state.get("display_name"),
        "logged_in": bool(account_state.get("logged_in")),
    }
    profile = account_state.get("profile", {}) if isinstance(account_state.get("profile"), dict) else {}
    tenant_state["login_status"] = str(profile.get("login_status") or ("ready" if account_state.get("logged_in") else "pending")).strip()

    executor = {}
    command_result = account_state.get("command_result", {}) if isinstance(account_state.get("command_result"), dict) else {}
    if isinstance(command_result.get("executor"), dict):
        executor = command_result.get("executor", {})
    tenant_state["executor_snapshot"] = {
        "adapter": executor.get("adapter"),
        "available": bool(executor.get("available")),
        "root_dir": executor.get("root_dir"),
    }

    if executor and not bool(executor.get("available")):
        tenant_state["stage"] = "executor_missing"
        tenant_state["blocked_reason"] = "toutiao_executor_missing"
        tenant_state["next_action"] = "配置可用执行器后继续自主运营"
        tenants_state[member_state_key] = tenant_state
        tenants_state["default"] = tenant_state
        self_media_runtime["tenants"] = tenants_state
        runtime["self_media"] = self_media_runtime
        return

    git_export = tenant_state.get("git_export", {}) if isinstance(tenant_state.get("git_export"), dict) else {}
    if str(git_export.get("status") or "").strip() != "ready":
        tenant_state["stage"] = "git_export_not_ready"
        tenant_state["blocked_reason"] = str(git_export.get("reason") or "git_export_not_ready").strip() or "git_export_not_ready"
        tenant_state["next_action"] = str(git_export.get("next_action") or "补齐 Gitee token 和 toutiao 仓配置后继续").strip() or "补齐 Gitee token 和 toutiao 仓配置后继续"
        tenants_state[member_state_key] = tenant_state
        tenants_state["default"] = tenant_state
        self_media_runtime["tenants"] = tenants_state
        runtime["self_media"] = self_media_runtime
        return

    if not bool(account_state.get("logged_in")):
        tenant_state["stage"] = "waiting_login"
        tenant_state["blocked_reason"] = tenant_state.get("login_status") or "login_required"
        tenant_state["next_action"] = "等待账号完成登录接管"
        tenants_state[member_state_key] = tenant_state
        tenants_state["default"] = tenant_state
        self_media_runtime["tenants"] = tenants_state
        runtime["self_media"] = self_media_runtime
        return

    if _has_active_background_task(
        task_queue,
        tenant_id,
        task_type="operation_publish_draft",
        source="background_self_media_autonomy_draft",
        pending_status=pending_status,
        running_status=running_status,
    ):
        tenant_state["stage"] = "draft_running"
        tenant_state["blocked_reason"] = None
        tenant_state["next_action"] = "等待当前内容草稿任务完成"
        tenants_state[member_state_key] = tenant_state
        tenants_state["default"] = tenant_state
        self_media_runtime["tenants"] = tenants_state
        runtime["self_media"] = self_media_runtime
        return

    if _has_active_background_task(
        task_queue,
        tenant_id,
        task_type="operation_analytics",
        source="background_self_media_autonomy_analytics",
        pending_status=pending_status,
        running_status=running_status,
    ):
        tenant_state["stage"] = "analytics_running"
        tenant_state["blocked_reason"] = None
        tenant_state["next_action"] = "等待账号分析任务完成"
        tenants_state[member_state_key] = tenant_state
        tenants_state["default"] = tenant_state
        self_media_runtime["tenants"] = tenants_state
        runtime["self_media"] = self_media_runtime
        return

    latest_draft_task = _latest_successful_background_task(
        task_queue,
        tenant_id,
        task_type="operation_publish_draft",
        source="background_self_media_autonomy_draft",
    )
    if latest_draft_task is None:
        payload = {
            "channel": "toutiao",
            "account_id": account_id,
            "topic": str(tenant_state.get("topic") or "自媒体运营"),
            "deliverable_goal": str(tenant_state.get("target_outcome") or "跑通首篇文章草稿并进入持续复盘"),
            "goal_hint": "先产出一篇可复盘的文章草稿，让系统具备持续产出起点",
            "audience_hint": "关注自动化运营与真实落地案例的读者",
            "publish_content_type": "article",
            "_source": "background_self_media_autonomy_draft",
            "_autonomy_job": autonomy_job,
        }
        created = task_queue.submit(
            task_type="operation_publish_draft",
            payload=payload,
            priority=task_priority_normal,
            tenant_id=tenant_id,
        )
        tenant_state["stage"] = "draft_submitted"
        tenant_state["blocked_reason"] = None
        tenant_state["next_action"] = "等待首篇文章草稿生成完成"
        tenant_state["last_draft_task_id"] = created.id
        tenant_state["last_draft_submitted_at"] = datetime.now().isoformat()
        tenants_state[member_state_key] = tenant_state
        tenants_state["default"] = tenant_state
        self_media_runtime["tenants"] = tenants_state
        runtime["self_media"] = self_media_runtime
        return

    latest_draft_result = latest_draft_task.result if isinstance(latest_draft_task.result, dict) else {}
    publish_result = latest_draft_result.get("result", {}) if isinstance(latest_draft_result.get("result"), dict) else {}
    tenant_state["last_draft_task_id"] = latest_draft_task.id
    tenant_state["last_draft_completed_at"] = getattr(latest_draft_task, "completed_at", None)
    tenant_state["last_draft_summary"] = latest_draft_result.get("insight_summary") or latest_draft_result.get("message")
    tenant_state["last_article_title"] = latest_draft_result.get("article_title")
    tenant_state["last_article_path"] = publish_result.get("article_path") or publish_result.get("draft_path")

    successful_analytics = [
        task for task in _list_background_tasks(
            task_queue,
            tenant_id,
            task_type="operation_analytics",
            source="background_self_media_autonomy_analytics",
        )
        if getattr(getattr(task, "status", None), "value", "") == "success"
    ]
    completed_types: list[str] = []
    for task in successful_analytics:
        payload = task.payload if isinstance(task.payload, dict) else {}
        analytics_type = str(payload.get("analytics_type") or "").strip().lower()
        if analytics_type and analytics_type not in completed_types:
            completed_types.append(analytics_type)
    required_types = ["fans", "works", "income"]
    missing_types = [item for item in required_types if item not in completed_types]
    if missing_types:
        for analytics_type in missing_types:
            task_queue.submit(
                task_type="operation_analytics",
                payload={
                    "channel": "toutiao",
                    "account_id": account_id,
                    "analytics_type": analytics_type,
                    "_source": "background_self_media_autonomy_analytics",
                    "_autonomy_job": autonomy_job,
                },
                priority=task_priority_normal,
                tenant_id=tenant_id,
            )
        tenant_state["stage"] = "analytics_submitted"
        tenant_state["blocked_reason"] = None
        tenant_state["next_action"] = "等待粉丝/作品/收益分析完成"
        tenant_state["last_analytics_submitted_at"] = datetime.now().isoformat()
        tenant_state["analytics_completed_types"] = completed_types
        tenants_state[member_state_key] = tenant_state
        tenants_state["default"] = tenant_state
        self_media_runtime["tenants"] = tenants_state
        runtime["self_media"] = self_media_runtime
        return

    tenant_state["stage"] = "observing_feedback"
    tenant_state["blocked_reason"] = None
    tenant_state["next_action"] = "继续观察评论、互动和账号分析结果，准备下一轮内容策略"
    tenant_state["analytics_completed_types"] = completed_types
    tenants_state[member_state_key] = tenant_state
    tenants_state["default"] = tenant_state
    self_media_runtime["tenants"] = tenants_state
    runtime["self_media"] = self_media_runtime
