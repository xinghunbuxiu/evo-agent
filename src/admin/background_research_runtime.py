"""
后台自治研究运行时：
负责样本发现、学习刷新、成长推进与反馈轮询。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from admin.worker_route_runtime import (
    member_uses_operation_automation,
    resolve_primary_worker_id,
    resolve_work_type_id,
    worker_uses_self_media_tenant_bucket,
)
from workers.registry import is_worker_enabled


def create_background_research_runtime_bindings(
    *,
    load_autonomy_runtime: Callable[[Path], dict],
    load_learning_tasks: Callable[[Path], dict],
    normalize_child_members_runtime: Callable[[object], dict],
    normalize_feedback_monitor_runtime: Callable[[dict | None], dict],
    save_autonomy_runtime: Callable[[Path, dict], None],
    save_learning_tasks: Callable[[Path, dict], None],
    discover_javascript_research_samples: Callable[[Path], list[dict]],
    auto_submit_javascript_research_tasks: Callable[[str, object, dict], dict],
    diagnose_research_sample: Callable[..., dict],
    build_external_learning_plan: Callable[..., dict],
    refresh_learning_task: Callable[..., dict],
    advance_background_research_for_tenant: Callable[..., dict],
    auto_draft_stable_experience_skills: Callable[..., object],
    record_growth_event: Callable[..., object],
    record_member_experience_journal: Callable[..., list[str]],
    safe_float: Callable[[object, float], float],
    advance_background_self_media_autonomy_for_tenant: Callable[..., object],
    get_account_identity: Callable[..., dict],
    describe_toutiao_executor_registry: Callable[[Path], dict],
    get_git_export_status: Callable[[str], dict],
    advance_background_feedback_monitor_for_tenant: Callable[..., object],
    task_priority_normal,
    pending_status,
    running_status,
):
    def _append_relationship_message(
        relationship_center: dict,
        *,
        thread_id: str,
        participants: list[str],
        sender_member_id: str,
        sender_role: str,
        message_type: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        threads = relationship_center.get("conversation_threads")
        if not isinstance(threads, list):
            threads = []
            relationship_center["conversation_threads"] = threads
        thread = next(
            (item for item in threads if isinstance(item, dict) and str(item.get("thread_id") or "") == thread_id),
            None,
        )
        if thread is None:
            thread = {
                "thread_id": thread_id,
                "participants": participants,
                "messages": [],
            }
            threads.append(thread)
        messages = thread.get("messages")
        if not isinstance(messages, list):
            messages = []
            thread["messages"] = messages
        messages.append({
            "message_id": f"{thread_id}:{int(datetime.now().timestamp() * 1000)}",
            "sender_member_id": sender_member_id,
            "sender_role": sender_role,
            "message_type": message_type,
            "content": content,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
        })
        thread["messages"] = messages[-40:]
        relationship_center["conversation_threads"] = threads[-40:]

    def _append_parent_inbox_message(relationship_center: dict, payload: dict) -> None:
        inbox = relationship_center.get("parent_inbox")
        if not isinstance(inbox, list):
            inbox = []
            relationship_center["parent_inbox"] = inbox
        inbox.append(payload)
        relationship_center["parent_inbox"] = inbox[-40:]

    def _future_iso(hours: int) -> str:
        return (datetime.now() + timedelta(hours=max(1, hours))).isoformat()

    def _derive_training_plan_for_member(member: dict, runtime: dict, workspace: Path) -> tuple[dict, dict]:
        current_plan = member.get("training_plan", {}) if isinstance(member.get("training_plan"), dict) else {}
        current_jobs = member.get("current_jobs", []) if isinstance(member.get("current_jobs"), list) else []
        active_job = current_jobs[0] if current_jobs and isinstance(current_jobs[0], dict) else {}
        if str(member.get("primary_role") or "") == "talent_development":
            return current_plan, {
                "auto_updated": False,
                "reason": "trainer_member",
                "applied_rules": [],
                "observations": [],
            }

        status = str(member.get("growth_state", {}).get("phase") or member.get("status") or "idle").strip() or "idle"
        blocked_reason = str(member.get("growth_state", {}).get("blocked_reason") or "").strip()
        next_action = str(member.get("growth_state", {}).get("next_goal") or current_plan.get("next_action") or "").strip()
        issue_signals: list[str] = []
        rules: list[str] = []
        review_after = current_plan.get("review_after")
        tenant_state = {}

        work_type_id = resolve_work_type_id(member)
        worker_id = resolve_primary_worker_id(workspace, member=member, work_type_id=work_type_id)
        if worker_id and worker_uses_self_media_tenant_bucket(worker_id):
            executor_registry = describe_toutiao_executor_registry(workspace)
            selected_executor = executor_registry.get("selected") if isinstance(executor_registry, dict) else None
            account_id = str(active_job.get("account_id") or "default").strip() or "default"
            account_state = get_account_identity(workspace, account_id)
            self_media_runtime = runtime.get("self_media", {}) if isinstance(runtime.get("self_media"), dict) else {}
            tenant_states = self_media_runtime.get("tenants", {}) if isinstance(self_media_runtime.get("tenants"), dict) else {}
            tenant_state = tenant_states.get(str(member.get("member_id") or ""), {}) if isinstance(tenant_states.get(str(member.get("member_id") or "")), dict) else {}
            if not tenant_state:
                tenant_state = tenant_states.get("default", {}) if isinstance(tenant_states.get("default"), dict) else {}
            if not isinstance(selected_executor, dict) or not selected_executor.get("available"):
                status = "executor_missing"
                blocked_reason = "toutiao_executor_missing"
                next_action = "配置可用的 Toutiao Executor，恢复发布链路"
            elif not account_state.get("logged_in"):
                profile = account_state.get("profile", {}) if isinstance(account_state.get("profile"), dict) else {}
                status = "waiting_login"
                blocked_reason = str(profile.get("login_status") or "login_required")
                next_action = "完成头条账号登录接管，让子女智脑获得真实发布入口"
            elif str(tenant_state.get("stage") or "").strip():
                status = str(tenant_state.get("stage") or "ready_to_publish")
                blocked_reason = str(tenant_state.get("blocked_reason") or "").strip()
                next_action = str(tenant_state.get("next_action") or "继续自主运营")
            else:
                status = "ready_to_publish"
                blocked_reason = ""
                next_action = "继续生成选题、起草内容、观察反馈并进入下一轮复盘"

        runtime_stage = str(tenant_state.get("stage") or status or "").strip()
        if blocked_reason:
            plan_stage = "environment_blocked"
            rules.append("blocked_runtime_to_environment_blocked")
            issue_signals.append(f"blocked:{blocked_reason}")
            review_after = _future_iso(12)
        elif runtime_stage in {"ready_to_publish", "draft_ready", "awaiting_publish"}:
            plan_stage = "delivering"
            rules.append("publish_ready_to_delivering")
            issue_signals.append(f"runtime:{runtime_stage}")
            review_after = _future_iso(24)
        elif runtime_stage in {"published", "feedback_collecting", "observing_feedback"}:
            plan_stage = "stabilizing"
            rules.append("published_to_stabilizing")
            issue_signals.append(f"runtime:{runtime_stage}")
            review_after = _future_iso(48)
        elif runtime_stage in {"stable", "validated_improved", "validated_unchanged"}:
            plan_stage = "stable"
            rules.append("validated_to_stable")
            issue_signals.append(f"runtime:{runtime_stage}")
            review_after = _future_iso(72)
        elif status in {"bootstrapping", "idle", "planned"}:
            plan_stage = "profile_initialized"
            rules.append("early_status_to_profile_initialized")
            review_after = _future_iso(24)
        else:
            plan_stage = str(current_plan.get("stage") or "active_training").strip() or "active_training"
            if plan_stage == "profile_initialized":
                plan_stage = "active_training"
                rules.append("default_progress_to_active_training")
            review_after = review_after or _future_iso(24)

        if isinstance(tenant_state.get("git_export"), dict) and tenant_state.get("git_export", {}).get("status") == "exported":
            issue_signals.append("knowledge_exported")
        if tenant_state.get("last_article_title"):
            issue_signals.append("article_produced")
        if isinstance(tenant_state.get("analytics_completed_types"), list) and tenant_state.get("analytics_completed_types"):
            issue_signals.append("feedback_analytics_ready")

        adapted_plan = {
            **current_plan,
            "stage": plan_stage,
            "next_action": next_action or current_plan.get("next_action") or "继续推进下一轮训练与实践",
            "review_after": review_after,
        }
        return adapted_plan, {
            "auto_updated": bool(rules),
            "reason": blocked_reason or runtime_stage or status or "profile_initialized",
            "applied_rules": rules,
            "observations": issue_signals,
        }

    def sync_training_review_state(workspace: Path, runtime: dict, *, trigger: str) -> dict:
        relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}
        runtime_tenant_id = str(runtime.get("tenant_id") or "default").strip() or "default"
        child_members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        items = child_members.get("items", []) if isinstance(child_members.get("items"), list) else []
        changed_members: list[dict] = []
        next_items: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("status") or "active").strip() == "archived":
                next_items.append(item)
                continue
            next_item = dict(item)
            next_plan, autopilot = _derive_training_plan_for_member(next_item, runtime, workspace)
            current_plan = next_item.get("training_plan", {}) if isinstance(next_item.get("training_plan"), dict) else {}
            current_journal = next_item.get("experience_journal", {}) if isinstance(next_item.get("experience_journal"), dict) else {}
            next_item["training_plan"] = next_plan
            next_item["training_autopilot"] = autopilot
            next_journal = next_item.get("experience_journal", {}) if isinstance(next_item.get("experience_journal"), dict) else {}
            if current_journal != next_journal:
                record_member_experience_journal(
                    workspace,
                    runtime_tenant_id,
                    member=next_item,
                    journal=next_journal,
                    source=f"background_loop:{trigger}",
                )
            if current_plan != next_plan:
                changed_members.append({
                    "member_id": next_item.get("member_id"),
                    "name": next_item.get("name"),
                    "primary_role": next_item.get("primary_role"),
                    "training_stage": next_plan.get("stage"),
                    "next_action": next_plan.get("next_action"),
                })
                _append_relationship_message(
                    relationship_center,
                    thread_id=f"trainer:{next_item.get('member_id')}",
                    participants=["talent_development_officer", str(next_item.get("member_id") or "")],
                    sender_member_id="talent_development_officer",
                    sender_role="talent_development",
                    message_type="training_update",
                    content=(
                        f"我已根据你当前运行态，把训练阶段调整为 {next_plan.get('stage') or '--'}。"
                        f" 下一步请先执行：{next_plan.get('next_action') or '继续推进当前实践'}。"
                    ),
                    metadata={
                        "trigger": trigger,
                        "training_stage": next_plan.get("stage"),
                        "reason": autopilot.get("reason"),
                        "applied_rules": autopilot.get("applied_rules"),
                    },
                )
            next_items.append(next_item)
        runtime["child_members"] = {
            "selected_member_id": child_members.get("selected_member_id"),
            "items": next_items,
        }
        runtime["primary_child_member_id"] = child_members.get("selected_member_id")
        runtime["training_review"] = {
            "last_review_at": datetime.now().isoformat(),
            "last_trigger": trigger,
            "changed_count": len(changed_members),
            "changed_members": changed_members[:20],
            "last_message": (
                f"育成官已更新 {len(changed_members)} 个子女的训练计划"
                if changed_members
                else "育成官巡检完成，当前没有需要调整的训练计划"
            ),
        }
        _append_parent_inbox_message(relationship_center, {
            "message_id": f"parent:{int(datetime.now().timestamp() * 1000)}",
            "sender_member_id": "talent_development_officer",
            "sender_role": "talent_development",
            "message_type": "training_review_summary",
            "title": "育成官巡检汇报",
            "content": runtime["training_review"]["last_message"],
            "created_at": datetime.now().isoformat(),
            "metadata": {
                "trigger": trigger,
                "changed_count": len(changed_members),
            },
        })
        relationship_center["last_delivery_at"] = datetime.now().isoformat()
        runtime["relationship_center"] = relationship_center
        return runtime

    def background_javascript_research_loop(
        workspace: Path,
        task_queue,
        plugin_summary,
        tenant_manager,
        stop_event,
    ) -> None:
        while not stop_event.is_set():
            runtime = load_autonomy_runtime(workspace)
            learning_state = load_learning_tasks(workspace)
            interval = max(10, int(runtime.get("loop_interval_seconds", 20) or 20))
            if not runtime.get("enabled", True):
                if stop_event.wait(interval):
                    break
                continue

            try:
                runtime["status"] = "researching"
                runtime["last_error"] = None
                runtime["last_run_at"] = datetime.now().isoformat()
                runtime["feedback_monitor"] = normalize_feedback_monitor_runtime(runtime.get("feedback_monitor"))

                samples = (
                    discover_javascript_research_samples(workspace)
                    if is_worker_enabled(workspace, "javascript_reverse")
                    else []
                )
                tenant_ids = tenant_manager.list_tenants() or ["default"]
                sample_state = runtime.get("samples", {})
                if not isinstance(sample_state, dict):
                    sample_state = {}

                for tenant_id in tenant_ids:
                    tenant_state = sample_state.get(tenant_id, {})
                    if not isinstance(tenant_state, dict):
                        tenant_state = {}
                    plugin_policy = tenant_manager.get_plugin_policy(tenant_id)

                    for sample in samples:
                        submitted = auto_submit_javascript_research_tasks(tenant_id, task_queue, sample)
                        diagnosis = diagnose_research_sample(
                            task_queue=task_queue,
                            tenant_id=tenant_id,
                            sample=sample,
                            plugin_policy=plugin_policy,
                        )
                        diagnosis["learning_plan"] = build_external_learning_plan(
                            tenant_manager=tenant_manager,
                            tenant_id=tenant_id,
                            diagnosis=diagnosis,
                        )
                        diagnosis["learning_task"] = refresh_learning_task(
                            workspace=workspace,
                            tenant_manager=tenant_manager,
                            learning_state=learning_state,
                            tenant_id=tenant_id,
                            sample=sample,
                            diagnosis=diagnosis,
                            learning_plan=diagnosis["learning_plan"],
                            task_queue=task_queue,
                        )
                        tenant_state[sample["source_dir"]] = {
                            "bundle_path": sample["bundle_path"],
                            "sample_signature": sample["sample_signature"],
                            "last_seen_at": datetime.now().isoformat(),
                            "submitted": submitted.get("submitted", []),
                            "diagnosis": diagnosis,
                        }

                    sample_state[tenant_id] = tenant_state
                    advance_background_research_for_tenant(
                        workspace=workspace,
                        tenant_id=tenant_id,
                        task_queue=task_queue,
                        plugin_summary=plugin_summary,
                        tenant_manager=tenant_manager,
                    )
                    auto_draft_stable_experience_skills(
                        workspace=workspace,
                        tenant_id=tenant_id,
                        safe_float=safe_float,
                        record_growth_event=record_growth_event,
                    )
                    advance_background_self_media_autonomy_for_tenant(
                        workspace=workspace,
                        tenant_id=tenant_id,
                        task_queue=task_queue,
                        runtime=runtime,
                        get_account_identity=get_account_identity,
                        get_git_export_status=get_git_export_status,
                        task_priority_normal=task_priority_normal,
                        pending_status=pending_status,
                        running_status=running_status,
                    )
                    advance_background_feedback_monitor_for_tenant(
                        workspace=workspace,
                        tenant_id=tenant_id,
                        task_queue=task_queue,
                        runtime=runtime,
                        normalize_feedback_monitor_runtime=normalize_feedback_monitor_runtime,
                        task_priority_normal=task_priority_normal,
                        pending_status=pending_status,
                        running_status=running_status,
                    )

                runtime = sync_training_review_state(
                    workspace,
                    runtime,
                    trigger="background_loop",
                )
                runtime["samples"] = sample_state
                runtime["status"] = "idle"
                save_autonomy_runtime(workspace, runtime)
                save_learning_tasks(workspace, learning_state)
            except Exception as exc:
                runtime["status"] = "error"
                runtime["last_error"] = str(exc)
                runtime["last_run_at"] = datetime.now().isoformat()
                save_autonomy_runtime(workspace, runtime)
                print(f"⚠️ background javascript research loop error: {exc}")

            if stop_event.wait(interval):
                break

    return {
        "background_javascript_research_loop": background_javascript_research_loop,
    }
