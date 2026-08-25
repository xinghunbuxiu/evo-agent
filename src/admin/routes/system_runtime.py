"""
系统运行态与工种注册相关接口。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from fastapi import Request
from core import ExperienceStore, GitProviderError
from admin.memory_hub_runtime import create_memory_hub_runtime_bindings
from admin.runtime_state import load_learning_tasks, save_learning_tasks
from admin.autonomy_learning_runtime import draft_learning_task_id
from admin.knowledge_learning_runtime import (
    sync_member_knowledge_learning_writeback,
    trigger_member_knowledge_learning_validation,
)
from admin.collaboration_runtime import (
    maybe_finalize_provider_collaboration,
    maybe_mark_provider_collaboration_submitted,
    normalize_collaboration_center,
)
from admin.formal_task_evolution_runtime import maybe_notify_independence_readiness
from admin.intake_runtime import mark_intake_delivered_from_task, mark_intake_in_progress_from_task
from admin.routes.collaboration_routes import register_collaboration_routes
from admin.routes.intake_routes import register_intake_routes
from admin.routes.work_nodes_routes import register_work_nodes_routes
from admin.worker_route_runtime import (
    build_generic_automation_job_runtime,
    build_operation_job_runtime,
    member_uses_operation_automation,
    resolve_primary_worker_id,
    resolve_work_type_id,
    worker_has_operation_tasks,
    worker_uses_self_media_tenant_bucket,
)


def register_system_runtime_routes(
    app,
    *,
    workspace: Path,
    tenant_manager,
    task_queue,
    plugin_summary,
    worker_runtime: dict,
    builtin_worker_manifests: Callable[..., dict[str, dict]],
    load_worker_registry_config: Callable[[Path], dict],
    save_worker_registry_config: Callable[[Path, dict], dict],
    load_autonomy_runtime: Callable[[Path], dict],
    create_employee_member_runtime: Callable[..., dict],
    normalize_parent_profile_runtime: Callable[[dict | None], dict],
    normalize_child_agent_runtime: Callable[[dict | None], dict],
    normalize_child_members_runtime: Callable[[object], dict],
    normalize_feedback_monitor_runtime: Callable[[dict | None], dict],
    save_autonomy_runtime: Callable[[Path, dict], None],
    refresh_runtime_learning_tasks: Callable[..., dict],
    build_historical_learning_tasks: Callable[[Path, str, object], list[dict]],
    trigger_learning_task_validation: Callable[..., dict],
    describe_toutiao_executor_registry: Callable[[Path], dict],
    get_toutiao_account_identity: Callable[[Path, str], dict],
    get_user_gitee_token: Callable[[Request], str | None],
    get_git_provider_instance: Callable[[object, dict | None], object],
    get_tenant_git_repo: Callable[[object, str, str, str, str], tuple[str, str]],
    config,
    load_mission_runs: Callable[[Path], dict],
    load_review_queue: Callable[[Path, str], list[dict]],
    list_platform_strategy_promotions: Callable[[Path, int], list[dict]],
    record_member_experience_journal: Callable[..., list[str]],
    build_evolution_overview: Callable[..., dict],
    success_response: Callable[[dict | None, str], dict],
    error_response: Callable[[str, int], object],
) -> None:
    memory_hub_runtime = create_memory_hub_runtime_bindings(
        build_historical_learning_tasks=build_historical_learning_tasks,
        list_platform_strategy_promotions=list_platform_strategy_promotions,
    )
    build_member_memory_hub = memory_hub_runtime["build_member_memory_hub"]
    sync_runtime_memory_hub = memory_hub_runtime["sync_runtime_memory_hub"]

    def append_relationship_message(
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

    def append_parent_inbox_message(relationship_center: dict, payload: dict) -> None:
        inbox = relationship_center.get("parent_inbox")
        if not isinstance(inbox, list):
            inbox = []
            relationship_center["parent_inbox"] = inbox
        inbox.append(payload)
        relationship_center["parent_inbox"] = inbox[-40:]

    def resolve_tenant_id(value: object | None = None) -> str:
        return str(value or "default").strip() or "default"

    def upsert_task(task_center: dict, payload: dict) -> dict:
        items = task_center.get("items")
        if not isinstance(items, list):
            items = []
            task_center["items"] = items
        task_id = str(payload.get("task_id") or "").strip()
        existing = next(
            (item for item in items if isinstance(item, dict) and str(item.get("task_id") or "").strip() == task_id),
            None,
        )
        if existing is None:
            existing = {}
            items.append(existing)
        existing.update(payload)
        task_center["items"] = items[-80:]
        return existing

    def upsert_task_recommendation(task_center: dict, payload: dict) -> dict:
        recommendations = task_center.get("recommendations")
        if not isinstance(recommendations, list):
            recommendations = []
            task_center["recommendations"] = recommendations
        recommendation_id = str(payload.get("recommendation_id") or "").strip()
        existing = next(
            (
                item for item in recommendations
                if isinstance(item, dict) and str(item.get("recommendation_id") or "").strip() == recommendation_id
            ),
            None,
        )
        if existing is None:
            existing = {}
            recommendations.append(existing)
        existing.update(payload)
        task_center["recommendations"] = recommendations[-80:]
        return existing

    def has_open_formal_task(task_center: dict, member_id: str, *, exclude_task_id: str | None = None) -> bool:
        items = task_center.get("items")
        if not isinstance(items, list):
            return False
        excluded = str(exclude_task_id or "").strip()
        normalized_member_id = str(member_id or "").strip()
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("member_id") or "").strip() != normalized_member_id:
                continue
            if excluded and str(item.get("task_id") or "").strip() == excluded:
                continue
            if str(item.get("status") or "").strip() != "approved":
                return True
        return False

    def build_task_completion_experience_card(member: dict, task: dict) -> dict:
        role = str(member.get("primary_role") or "autonomous_child_agent").strip() or "autonomous_child_agent"
        training_plan = member.get("training_plan", {}) if isinstance(member.get("training_plan"), dict) else {}
        current_jobs = member.get("current_jobs", []) if isinstance(member.get("current_jobs"), list) else []
        active_job = current_jobs[0] if current_jobs and isinstance(current_jobs[0], dict) else {}
        task_title = str(task.get("title") or "正式任务").strip() or "正式任务"
        task_objective = str(task.get("objective") or "").strip()
        result_summary = str(task.get("result_summary") or "").strip()
        reflection = str(task.get("reflection") or "").strip()
        review_note = str(task.get("review_note") or "").strip()
        deliverables = [
            str(item).strip()
            for item in (task.get("deliverables") if isinstance(task.get("deliverables"), list) else [])
            if str(item).strip()
        ]
        now_iso = datetime.now().isoformat()
        evidence = [
            *( [f"task:{str(task.get('task_id') or '').strip()}"] if str(task.get("task_id") or "").strip() else [] ),
            *( [f"title:{task_title}"] if task_title else [] ),
            *( [f"deliverables:{len(deliverables)}"] if deliverables else [] ),
            *( [f"objective:{task_objective}"] if task_objective else [] ),
        ]
        summary = result_summary or reflection or f"{task_title} 已完成，正在形成第一轮岗位经验。"
        current_pattern = (
            f"围绕 {task_title} 完成了一轮正式执行，并开始形成稳定的岗位闭环。"
        )
        professional_risk = (
            "下一轮仍需验证这次方法是否可复用、是否能稳定产出。"
        )
        next_experiment = (
            review_note
            or "基于本轮结果收缩变量，再推进下一轮更稳定的真实任务。"
        )
        return {
            "card_id": f"{str(active_job.get('job_id') or role).strip() or role}:{int(datetime.now().timestamp() * 1000)}",
            "role": role,
            "job_id": str(active_job.get("job_id") or role).strip() or role,
            "stage": str(training_plan.get("stage") or "stabilizing").strip() or "stabilizing",
            "status": "approved",
            "title": f"{task_title} 经验卡",
            "summary": summary,
            "current_pattern": current_pattern,
            "professional_risk": professional_risk,
            "next_experiment": next_experiment,
            "signature": "|".join([
                role,
                str(active_job.get("job_id") or role).strip() or role,
                task_title,
                result_summary,
                reflection,
            ]),
            "evidence": evidence[:8],
            "source_reflections": [item for item in [reflection, review_note] if item][:3],
            "created_at": now_iso,
            "updated_at": now_iso,
        }

    def build_trainer_auto_growth_followup(*, member: dict, task: dict, export_runtime: dict | None = None) -> tuple[str, dict]:
        member_name = str(member.get("name") or member.get("member_id") or "当前子女").strip() or "当前子女"
        role_label = str((member.get("persona", {}) if isinstance(member.get("persona"), dict) else {}).get("role_label") or member.get("primary_role") or "岗位子女").strip() or "岗位子女"
        result_summary = str(task.get("result_summary") or "").strip()
        reflection = str(task.get("reflection") or "").strip()
        export_runtime = export_runtime if isinstance(export_runtime, dict) else {}
        export_status = str(export_runtime.get("status") or "").strip()
        export_reason = str(export_runtime.get("reason") or "").strip()

        growth_gain = result_summary or reflection or "已经完成了一轮真实任务，并形成了新的岗位经验。"
        if export_status == "exported":
            next_move = "经验已经自动入库，下一轮要基于这次有效动作继续收缩变量，争取把方法做稳定。"
        elif export_status in {"failed", "blocked"}:
            next_move = f"经验入库这一步还没完全打通，先处理入库阻塞，再继续下一轮任务。{export_reason or ''}".strip()
        elif export_status == "ready":
            next_move = "环境已经具备自动入库条件，下一轮继续推进时重点观察是否能稳定形成连续经验。"
        else:
            next_move = "继续把这轮经验变成更稳定的岗位方法，再准备下一轮正式任务。"

        content = (
            f"育成官补充点评：{member_name} 这轮作为 {role_label} 已经真正拿到了一次可复盘结果。"
            f" 当前最有价值的成长收获是：{growth_gain}。"
            f" 下一轮建议：{next_move}"
        )
        return content, {
            "member_id": str(member.get("member_id") or "").strip() or None,
            "task_id": str(task.get("task_id") or "").strip() or None,
            "mission_status": "approved",
            "auto_followup": True,
            "export_status": export_status or None,
            "export_reason": export_reason or None,
        }

    def build_next_formal_task_recommendation(*, member: dict, task: dict, export_runtime: dict | None = None) -> dict:
        member_id = str(member.get("member_id") or "").strip() or "member"
        role = str(member.get("primary_role") or "").strip() or "autonomous_child_agent"
        member_name = str(member.get("name") or member_id).strip() or member_id
        result_summary = str(task.get("result_summary") or "").strip()
        reflection = str(task.get("reflection") or "").strip()
        export_runtime = export_runtime if isinstance(export_runtime, dict) else {}
        export_status = str(export_runtime.get("status") or "").strip()

        if member_uses_operation_automation(workspace, member):
            title = f"{member_name} 下一轮内容优化任务"
            objective = (
                "基于上一轮已经完成的内容实践与复盘，收缩一个最关键变量继续验证，"
                "让内容方法从‘做出来一次’走向‘可重复做出来’。"
            )
            deliverables = [
                "选择上一轮最值得继续验证的一个变量，例如选题、标题、表达结构或发布节奏",
                "产出一篇新的内容草案或改写版本",
                "说明这次与上一轮相比刻意调整了什么",
                "提交新结果，并判断方法是否更稳定",
            ]
            reason = (
                f"上一轮已经拿到了真实结果：{result_summary or reflection or '已形成首轮实践经验'}。"
                + (" 经验也已自动入库，可以开始做稳定性验证。" if export_status == "exported" else " 现在最值得做的是继续小步验证并增强稳定性。")
            )
        else:
            title = f"{member_name} 下一轮正式任务"
            objective = "基于上一轮经验继续推进下一轮真实任务，重点验证是否能把有效动作变成稳定方法。"
            deliverables = [
                "明确上一轮最值得继续验证的一点",
                "执行下一轮真实任务",
                "提交结果与变化说明",
                "继续沉淀可复用经验",
            ]
            reason = f"上一轮已完成，适合继续推进下一轮岗位稳定性验证。{result_summary or reflection or ''}".strip()

        memory_hub = member.get("memory_hub") if isinstance(member.get("memory_hub"), dict) else {}
        decision_state = memory_hub.get("decision_state") if isinstance(memory_hub.get("decision_state"), dict) else {}
        primary_plan = str(decision_state.get("primary_plan") or "").strip()
        verification_goal = str(decision_state.get("verification_goal") or "").strip()
        if primary_plan:
            reason = f"{reason} 系统思考：{primary_plan}".strip()
        if verification_goal and verification_goal not in objective:
            objective = f"{objective} 验证目标：{verification_goal}".strip()

        now_iso = datetime.now().isoformat()
        return {
            "recommendation_id": f"recommendation:{member_id}:{int(datetime.now().timestamp() * 1000)}",
            "member_id": member_id,
            "source_task_id": str(task.get("task_id") or "").strip() or None,
            "title": title,
            "objective": objective,
            "deliverables": deliverables,
            "reason": reason,
            "status": "suggested",
            "created_at": now_iso,
            "adopted_at": None,
            "metadata": {
                "role_scope": role,
                "export_status": export_status or None,
                "source": "trainer_auto_followup",
                "memory_decision_status": decision_state.get("status"),
            },
        }

    def evaluate_independence_readiness(*, member: dict, task_center: dict) -> dict:
        member_id = str(member.get("member_id") or "").strip()
        items = task_center.get("items") if isinstance(task_center.get("items"), list) else []
        approved_tasks = [
            item for item in items
            if isinstance(item, dict)
            and str(item.get("member_id") or "").strip() == member_id
            and str(item.get("status") or "").strip() == "approved"
        ]
        approved_count = len(approved_tasks)
        training_plan = member.get("training_plan") if isinstance(member.get("training_plan"), dict) else {}
        stage = str(training_plan.get("stage") or "").strip()
        journal = member.get("experience_journal") if isinstance(member.get("experience_journal"), dict) else {}
        cards = journal.get("cards") if isinstance(journal.get("cards"), list) else []
        card_count = len([item for item in cards if isinstance(item, dict)])
        criteria = [
            {"id": "has_approved_task", "label": "至少完成一轮正式任务", "met": approved_count >= 1},
            {"id": "has_reflection", "label": "已完成首轮复盘", "met": stage in {"first_reflection_done", "active_training", "independent_candidate"}},
            {"id": "has_experience_card", "label": "已沉淀经验卡", "met": card_count >= 1},
            {"id": "multi_round_validation", "label": "多轮稳定性验证", "met": approved_count >= 2},
        ]
        met_count = sum(1 for item in criteria if item.get("met"))
        ready = all(item.get("met") for item in criteria[:3]) and approved_count >= 2
        return {
            "ready_for_independence": ready,
            "met_criteria_count": met_count,
            "total_criteria": len(criteria),
            "approved_task_count": approved_count,
            "experience_card_count": card_count,
            "criteria": criteria,
            "evaluated_at": datetime.now().isoformat(),
        }

    def maybe_enqueue_member_knowledge_learning(
        *,
        normalized_tenant_id: str,
        member: dict,
        relationship_center: dict,
        trigger: str,
    ) -> dict | None:
        if not isinstance(member, dict):
            return None
        operating_contract = member.get("operating_contract") if isinstance(member.get("operating_contract"), dict) else {}
        if not bool(operating_contract.get("allow_external_learning", True)):
            return None
        memory_hub = member.get("memory_hub") if isinstance(member.get("memory_hub"), dict) else {}
        retrieval_state = memory_hub.get("retrieval_state") if isinstance(memory_hub.get("retrieval_state"), dict) else {}
        decision_state = memory_hub.get("decision_state") if isinstance(memory_hub.get("decision_state"), dict) else {}
        needs_external = (
            bool(retrieval_state.get("needs_external_learning"))
            or str(decision_state.get("status") or "").strip() == "needs_external_learning"
        )
        if not needs_external:
            return None

        member_id = str(member.get("member_id") or "").strip()
        if not member_id:
            return None
        work_type_id = resolve_work_type_id(member) or str(member.get("primary_role") or "").strip() or member_id
        learning_task_id = draft_learning_task_id(
            normalized_tenant_id,
            "autonomy_training",
            member_id,
            {"work_type_id": work_type_id, "member_id": member_id},
        )
        learning_state = load_learning_tasks(workspace)
        tasks = learning_state.get("tasks") if isinstance(learning_state.get("tasks"), dict) else {}
        existing = tasks.get(learning_task_id) if isinstance(tasks.get(learning_task_id), dict) else {}
        existing_status = str(existing.get("status") or "").strip()
        if existing and existing_status not in {"", "needs_learning", "researching"}:
            return existing

        escalation = str(
            decision_state.get("escalation_reason")
            or memory_hub.get("decision_intent")
            or "本地经验不足，需要补知识"
        ).strip()
        primary_plan = str(decision_state.get("primary_plan") or "").strip()
        member_name = str(member.get("name") or member_id).strip() or member_id
        now_iso = datetime.now().isoformat()
        queries = [
            item for item in [
                escalation,
                primary_plan,
                str(decision_state.get("verification_goal") or "").strip(),
            ] if item
        ][:3]
        if not queries:
            queries = [f"围绕 {member_name} 当前岗位任务补齐可执行知识"]

        preferred_sources = retrieval_state.get("preferred_sources") if isinstance(retrieval_state.get("preferred_sources"), list) else []
        if not preferred_sources:
            preferred_sources = ["local_memory", "enterprise_repo", "official_docs", "ai_assist"]

        created = {
            **existing,
            "task_id": learning_task_id,
            "tenant_id": normalized_tenant_id,
            "member_id": member_id,
            "goal": escalation,
            "mission_kind": "autonomy_training",
            "title": f"{member_name} · 补知识任务",
            "source": "memory_hub_auto",
            "work_type_id": work_type_id,
            "issue_category": "capability_gap",
            "gap_type": "knowledge_gap",
            "queries": queries,
            "preferred_sources": preferred_sources[:6],
            "validation_gate": "补知识后需形成可执行动作，并回到正式任务验证。",
            "status": "needs_learning",
            "created_at": existing.get("created_at") or now_iso,
            "updated_at": now_iso,
            "metadata": {
                "trigger": trigger,
                "memory_decision_status": decision_state.get("status"),
            },
        }
        tasks[learning_task_id] = created
        save_learning_tasks(workspace, {"tasks": tasks})
        refresh_runtime_learning_tasks(
            workspace=workspace,
            tenant_manager=tenant_manager,
            task_queue=task_queue,
            tenant_id=normalized_tenant_id,
        )

        training_plan = member.get("training_plan") if isinstance(member.get("training_plan"), dict) else {}
        member["training_plan"] = {
            **training_plan,
            "stage": training_plan.get("stage") or "knowledge_supplementing",
            "next_action": "系统已触发补知识任务，等待调研结果后再推进正式任务",
            "knowledge_learning_task_id": learning_task_id,
            "knowledge_learning_trigger": trigger,
        }
        append_relationship_message(
            relationship_center,
            thread_id=f"trainer:{member_id}",
            participants=["talent_development_officer", member_id],
            sender_member_id="talent_development_officer",
            sender_role="talent_development",
            message_type="training_update",
            content=f"系统检测到本地经验不足，已自动发起补知识任务：{created['title']}。{escalation}",
            metadata={
                "member_id": member_id,
                "learning_task_id": learning_task_id,
                "auto_knowledge_learning": True,
                "trigger": trigger,
            },
        )
        return created

    def apply_member_knowledge_learning_if_needed(
        *,
        runtime: dict,
        normalized_tenant_id: str,
        member_id: str,
        trigger: str,
    ) -> dict | None:
        members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        target_member = next(
            (
                item for item in members.get("items", [])
                if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id
            ),
            None,
        )
        if not isinstance(target_member, dict):
            return None
        relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}
        created = maybe_enqueue_member_knowledge_learning(
            normalized_tenant_id=normalized_tenant_id,
            member=target_member,
            relationship_center=relationship_center,
            trigger=trigger,
        )
        if created:
            runtime["relationship_center"] = relationship_center
            runtime["child_members"] = members
            runtime = sync_member_knowledge_learning_writeback(
                workspace=workspace,
                runtime=runtime,
                tenant_id=normalized_tenant_id,
                normalize_child_members_runtime=normalize_child_members_runtime,
            )
        return created

    def collect_child_experience_journals(runtime: dict) -> tuple[list[dict], dict]:
        child_members = runtime.get("child_members", {}) if isinstance(runtime.get("child_members"), dict) else {}
        items = child_members.get("items") if isinstance(child_members.get("items"), list) else []
        journals: list[dict] = []
        card_total = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            journal = item.get("experience_journal", {}) if isinstance(item.get("experience_journal"), dict) else {}
            cards = journal.get("cards") if isinstance(journal.get("cards"), list) else []
            normalized_cards = [card for card in cards if isinstance(card, dict)]
            if not normalized_cards:
                continue
            card_total += len(normalized_cards)
            journals.append({
                "member_id": str(item.get("member_id") or "").strip() or None,
                "name": str(item.get("name") or "").strip() or None,
                "primary_role": str(item.get("primary_role") or "").strip() or None,
                "last_compiled_at": journal.get("last_compiled_at"),
                "latest_card_id": journal.get("latest_card_id"),
                "card_count": len(normalized_cards),
                "cards": normalized_cards[:8],
            })
        journals.sort(key=lambda item: str(item.get("last_compiled_at") or ""), reverse=True)
        summary = {
            "member_count": len(journals),
            "card_total": card_total,
            "latest_compiled_at": journals[0].get("last_compiled_at") if journals else None,
        }
        return journals, summary

    async def auto_export_member_experience_to_git(
        *,
        request: Request,
        tenant_id: str,
        member: dict,
        runtime: dict,
        task: dict,
    ) -> dict:
        if str(member.get("primary_role") or "").strip() == "talent_development":
            return {
                "status": "skipped",
                "reason": "trainer_member",
                "token_available": False,
                "repo_key": "experiences",
                "target_repo": None,
                "target_url": None,
                "branch": None,
                "next_action": "育成师成员不导出一线岗位经验",
            }
        if not member_uses_operation_automation(workspace, member):
            return {
                "status": "skipped",
                "reason": "role_not_supported",
                "token_available": False,
                "repo_key": "experiences",
                "target_repo": None,
                "target_url": None,
                "branch": None,
                "next_action": "当前岗位工种未绑定可导出的 automation worker",
            }

        token = get_user_gitee_token(request) or os.getenv("GITEE_TOKEN")
        if not token or token == "your_real_token_here":
            return {
                "status": "blocked",
                "reason": "missing_gitee_token",
                "token_available": False,
                "repo_key": "experiences",
                "target_repo": None,
                "target_url": None,
                "branch": None,
                "next_action": "先绑定 Gitee 个人令牌，或配置服务端 GITEE_TOKEN",
            }

        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        provider = get_git_provider_instance(config, git_knowledge)
        target_repo, target_url = get_tenant_git_repo(
            tenant_manager,
            tenant_id,
            "experiences",
            config.experiences.full_name,
            config.experiences.url,
        )
        repos = git_knowledge.get("repos", {}) if isinstance(git_knowledge, dict) else {}
        branch = "master"
        if isinstance(repos, dict) and isinstance(repos.get("experiences"), dict):
            branch = str(repos.get("experiences", {}).get("branch") or "master").strip() or "master"
        if not target_repo:
            return {
                "status": "blocked",
                "reason": "missing_git_repo",
                "token_available": True,
                "repo_key": "experiences",
                "target_repo": None,
                "target_url": None,
                "branch": branch,
                "next_action": "先初始化租户 experiences 仓库，再继续自动经验入库",
            }

        store = ExperienceStore(workspace, tenant_id)
        child_experience_journals, journal_summary = collect_child_experience_journals(runtime)
        payload = {
            "tenant_id": tenant_id,
            "exported_at": datetime.now().isoformat(),
            "source": "formal_task_auto_export",
            "member_id": str(member.get("member_id") or "").strip() or None,
            "task_id": str(task.get("task_id") or "").strip() or None,
            "growth_events": [exp.to_dict() for exp in store.load_by_task("evolution", "growth_event", limit=30)],
            "replay_validations": [exp.to_dict() for exp in store.load_by_task("evolution", "replay_validation", limit=20)],
            "child_experience_journals": child_experience_journals,
            "journal_summary": journal_summary,
        }
        file_path = f"exports/experiences/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(member.get('member_id') or 'member').strip() or 'member'}.json"
        try:
            await provider.upsert_text_file(
                token=token,
                repo_full_name=target_repo,
                file_path=file_path,
                content=json.dumps(payload, indent=2, ensure_ascii=False),
                message=f"Auto export experiences for tenant {tenant_id}",
                branch=branch,
            )
        except GitProviderError as exc:
            return {
                "status": "failed",
                "reason": str(exc),
                "token_available": True,
                "repo_key": "experiences",
                "target_repo": target_repo,
                "target_url": target_url,
                "branch": branch,
                "next_action": "检查 experiences 仓配置、分支和令牌权限后重试",
            }

        return {
            "status": "exported",
            "reason": None,
            "token_available": True,
            "repo_key": "experiences",
            "target_repo": target_repo,
            "target_url": target_url,
            "branch": branch,
            "next_action": "经验已自动入库，可继续推进下一轮正式任务",
            "last_export": {
                "task_id": str(task.get("task_id") or "").strip() or None,
                "task_type": "formal_task_experience",
                "completed_at": datetime.now().isoformat(),
                "status": "exported",
                "reason": "formal_task_auto_export",
                "repo_key": "experiences",
                "repo_full_name": target_repo,
                "repo_url": target_url,
                "branch": branch,
                "files": [file_path],
            },
        }

    def build_trainer_reply(*, member: dict, content: str) -> tuple[str, dict]:
        normalized = str(content or "").strip()
        lower_content = normalized.lower()
        training_plan = member.get("training_plan", {}) if isinstance(member.get("training_plan"), dict) else {}
        stage = str(training_plan.get("stage") or "active_training").strip() or "active_training"
        next_action = str(training_plan.get("next_action") or "继续推进当前训练").strip() or "继续推进当前训练"
        role_label = str((member.get("persona", {}) if isinstance(member.get("persona"), dict) else {}).get("role_label") or member.get("primary_role") or "子女成员").strip() or "子女成员"
        trend_hint = "最近外部做法和训练反馈也值得你顺手关注一下，但专业判断仍以你自己的实践为主。"

        if any(keyword in normalized for keyword in ["卡", "失败", "不行", "报错"]) or any(keyword in lower_content for keyword in ["error", "fail", "blocked"]):
            return (
                f"收到。我先不替你做专业判断，你还是这个岗位的一线执行者。"
                f"你当前处在 {stage} 阶段，先把这次阻塞整理成一个清晰问题，再围绕训练主线继续推进：{next_action}。"
                f"{trend_hint}",
                {
                    "reply_policy": "growth_coach_unblock",
                    "training_stage": stage,
                    "boundary": "trainer_focuses_on_growth_not_domain_decision",
                },
            )
        if any(keyword in normalized for keyword in ["完成", "好了", "已完成", "搞定"]) or any(keyword in lower_content for keyword in ["done", "finished", "complete"]):
            return (
                f"做得好，{role_label} 这轮已经靠你自己的专业实践推进了。"
                f"我这边更关注你怎么把这次经验沉淀下来，再进入下一轮训练：{next_action}。",
                {
                    "reply_policy": "growth_coach_reinforce",
                    "training_stage": stage,
                    "boundary": "trainer_focuses_on_growth_not_domain_decision",
                },
            )
        if any(keyword in normalized for keyword in ["建议", "调整", "不适合", "换"]) or any(keyword in lower_content for keyword in ["suggest", "adjust", "change"]):
            return (
                f"你的判断我会认真看，但专业路线最终还是由你在一线实践里验证。"
                f"我这边先把它当成训练路径优化信号，不急着推翻主线，先小步试一个替代方案，同时保持当前训练重点：{next_action}。",
                {
                    "reply_policy": "growth_coach_reflect",
                    "training_stage": stage,
                    "boundary": "trainer_focuses_on_growth_not_domain_decision",
                },
            )
        return (
            f"我收到你的反馈了。你继续作为 {role_label} 的专业执行者往前做，"
            f"我主要帮你看成长节奏、训练重点和外部趋势。当前先保持这轮训练推进：{next_action}。",
            {
                "reply_policy": "growth_coach_steady",
                "training_stage": stage,
                "boundary": "trainer_focuses_on_growth_not_domain_decision",
            },
        )

    def _future_iso(hours: int) -> str:
        return (datetime.now() + timedelta(hours=max(1, hours))).isoformat()

    def derive_member_training_plan(member: dict, derived_state: dict, active_runtime: dict) -> tuple[dict, dict]:
        current_plan = member.get("training_plan", {}) if isinstance(member.get("training_plan"), dict) else {}
        current_jobs = member.get("current_jobs", []) if isinstance(member.get("current_jobs"), list) else []
        active_job = current_jobs[0] if current_jobs and isinstance(current_jobs[0], dict) else {}
        role_label = str((member.get("persona", {}) if isinstance(member.get("persona"), dict) else {}).get("role_label") or member.get("primary_role") or "子女成员").strip() or "子女成员"
        status = str(derived_state.get("status") or "").strip()
        blocked_reason = str(derived_state.get("blocked_reason") or "").strip()
        next_action = str(derived_state.get("next_action") or current_plan.get("next_action") or "").strip()
        issue_signals: list[str] = []
        rules: list[str] = []
        review_after = current_plan.get("review_after")

        if str(member.get("primary_role") or "") == "talent_development":
            return current_plan, {
                "auto_updated": False,
                "reason": "trainer_member",
                "applied_rules": [],
                "observations": [],
            }

        tenant_state = active_runtime.get("tenant_state", {}) if isinstance(active_runtime.get("tenant_state"), dict) else {}
        runtime_stage = str(tenant_state.get("stage") or status or "").strip()
        git_export = tenant_state.get("git_export", {}) if isinstance(tenant_state.get("git_export"), dict) else {}

        plan_stage = str(current_plan.get("stage") or "profile_initialized").strip() or "profile_initialized"
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
            plan_stage = plan_stage or "active_training"
            if plan_stage == "profile_initialized":
                plan_stage = "active_training"
                rules.append("default_progress_to_active_training")
            review_after = review_after or _future_iso(24)

        if git_export.get("status") == "exported":
            issue_signals.append("knowledge_exported")
        if tenant_state.get("last_article_title"):
            issue_signals.append("article_produced")
        if isinstance(tenant_state.get("analytics_completed_types"), list) and tenant_state.get("analytics_completed_types"):
            issue_signals.append("feedback_analytics_ready")

        goal_label = str(active_job.get("title") or role_label).strip() or role_label
        if not next_action:
            next_action = f"继续推进 {goal_label} 的下一轮训练与实践"

        adapted_plan = {
            **current_plan,
            "stage": plan_stage,
            "next_action": next_action,
            "review_after": review_after,
        }
        coaching_view = {
            "growth_diagnosis": (
                f"当前主要卡点是 {blocked_reason}" if blocked_reason
                else f"当前处在 {plan_stage} 阶段，说明还在沿着训练路径持续推进"
            ),
            "training_suggestion": (
                f"下一轮训练建议先围绕这一步做小范围推进：{next_action}"
            ),
            "trend_watch": (
                "留意外部近期是否出现更高效的做法，但专业决策仍由岗位子女自己在实践里验证"
            ),
        }
        autopilot = {
            "auto_updated": bool(rules),
            "reason": (
                blocked_reason
                or runtime_stage
                or status
                or "profile_initialized"
            ),
            "applied_rules": rules,
            "observations": issue_signals,
            "coaching_view": coaching_view,
        }
        return adapted_plan, autopilot

    def build_professional_view(member: dict, active_runtime: dict, relationship_center: dict | None = None) -> dict:
        def summarize_recent_reflections(
            *,
            reflections: list[str],
            evidence: list[str],
            fallback_focus: str,
            blocked_reason: str = "",
            default_pattern: str = "",
            default_summary: str = "",
        ) -> dict:
            normalized_reflections = [str(item).strip() for item in reflections if str(item).strip()]
            evidence_list = [str(item).strip() for item in evidence if str(item).strip()]
            joined_text = " ".join(normalized_reflections).lower()
            joined_evidence = " ".join(evidence_list).lower()
            haystack = f"{joined_text} {joined_evidence}".strip()

            blocked_keywords = [
                "blocked", "error", "fail", "失败", "报错", "卡住", "卡了", "登录", "login", "publish",
                "发布", "环境", "missing", "丢失", "权限", "token", "审核",
            ]
            iteration_keywords = [
                "测试", "尝试", "优化", "调整", "实验", "复盘", "improve", "optimize", "retry", "experiment",
                "validate", "compare",
            ]
            output_keywords = [
                "完成", "done", "发布", "article", "draft", "产出", "交付", "导出", "export", "analytics",
            ]

            summary = default_summary or "最近的岗位反馈还不够多，先继续积累一线实践。"
            current_pattern = default_pattern or "当前还在形成稳定的岗位工作节奏。"
            professional_risk = "当前主要风险仍需更多岗位反馈才能稳定判断。"
            next_experiment = fallback_focus or "继续推进当前岗位的下一轮专业实验。"

            if blocked_reason:
                summary = "最近的岗位反馈说明一线实践被环境或入口问题持续牵制。"
                current_pattern = "你会先尝试推进任务，但一遇到关键入口阻塞就被迫回到恢复链路。"
                professional_risk = f"如果 {blocked_reason} 不能尽快解除，岗位成长会被基础环境长期拖慢。"
                next_experiment = (
                    f"把 {blocked_reason} 拆成一个最小可验证问题，先完成一次可复现的恢复实验，再回到主任务。"
                )
            elif any(keyword in haystack for keyword in blocked_keywords):
                summary = "最近的岗位反馈里，恢复环境和打通关键入口仍然占了很大比重。"
                current_pattern = "你的专业动作已经开始出现，但节奏会频繁被账号、发布或依赖问题打断。"
                professional_risk = "如果长期把精力消耗在入口恢复，岗位方法论会积累得很慢。"
                next_experiment = "先把最容易复发的入口问题做成一次标准化排查，再继续当前岗位实验。"
            elif any(keyword in haystack for keyword in output_keywords) and any(keyword in haystack for keyword in iteration_keywords):
                summary = "最近的岗位反馈已经形成“有产出、有复盘、再优化”的专业闭环。"
                current_pattern = "你不是只在执行任务，而是在边做边总结有效表达与交付方式。"
                professional_risk = "当前风险不是没有动作，而是可能还缺少把经验沉淀成稳定方法的整理动作。"
                next_experiment = "挑一条刚完成的产出链路，复做一次并记录哪些步骤真正带来效果提升。"
            elif any(keyword in haystack for keyword in iteration_keywords):
                summary = "最近的岗位反馈说明你已经进入连续试验和自我修正阶段。"
                current_pattern = "你会主动比较不同做法，并尝试从结果里抽出更稳的工作套路。"
                professional_risk = "如果只有局部试验而没有阶段总结，经验会分散在单次案例里。"
                next_experiment = "把最近三次尝试整理成一张小结，只保留最值得继续验证的一条路线。"
            elif normalized_reflections:
                summary = "最近已经有岗位反馈产生，但还需要更多样本来形成清晰方法。"
                current_pattern = "你开始对外部结果有感知，也会用自己的话描述进展。"
                professional_risk = "当前最大风险是反馈样本太少，容易因为单次结果就下结论。"
                next_experiment = fallback_focus or "继续补足样本量，至少完成下一轮岗位实践再做判断。"

            return {
                "reflection_summary": summary,
                "current_pattern": current_pattern,
                "professional_risk": professional_risk,
                "next_experiment": next_experiment,
            }

        role_label = str((member.get("persona", {}) if isinstance(member.get("persona"), dict) else {}).get("role_label") or member.get("primary_role") or "子女成员").strip() or "子女成员"
        relationship_center = relationship_center if isinstance(relationship_center, dict) else {}
        thread_id = f"trainer:{str(member.get('member_id') or '').strip()}"
        recent_reflections: list[str] = []
        recent_thread = next(
            (
                item for item in (relationship_center.get("conversation_threads") if isinstance(relationship_center.get("conversation_threads"), list) else [])
                if isinstance(item, dict) and str(item.get("thread_id") or "") == thread_id
            ),
            None,
        )
        if isinstance(recent_thread, dict):
            messages = recent_thread.get("messages") if isinstance(recent_thread.get("messages"), list) else []
            for message in reversed(messages):
                if not isinstance(message, dict):
                    continue
                if str(message.get("sender_member_id") or "") != str(member.get("member_id") or ""):
                    continue
                text = str(message.get("content") or "").strip()
                if text:
                    recent_reflections.append(text)
                if len(recent_reflections) >= 3:
                    break
        if str(member.get("primary_role") or "") == "talent_development":
            reflection_summary = summarize_recent_reflections(
                reflections=recent_reflections,
                evidence=[],
                fallback_focus="继续优化培养方法与训练编排。",
                default_pattern="我主要通过观察、诊断和训练编排来支持其他子女成长。",
                default_summary="最近的反馈仍然围绕培养观察与训练支持展开。",
            )
            return {
                "owner": "trainer",
                "summary": "我是培养与发展岗位，不承担一线专业执行判断。",
                "current_judgement": "当前重点是观察子女成长、训练路径与外部趋势。",
                "next_professional_focus": "继续优化培养方法与训练编排。",
                "evidence": [],
                "recent_reflections": recent_reflections,
                **reflection_summary,
            }

        tenant_state = active_runtime.get("tenant_state", {}) if isinstance(active_runtime.get("tenant_state"), dict) else {}
        git_export = tenant_state.get("git_export", {}) if isinstance(tenant_state.get("git_export"), dict) else {}
        job_id = str(active_runtime.get("job_id") or "").strip()
        worker_id = resolve_primary_worker_id(workspace, member=member, work_type_id=job_id or None)
        if worker_id and worker_uses_self_media_tenant_bucket(worker_id):
            article_title = str(tenant_state.get("last_article_title") or "").strip()
            analytics = tenant_state.get("analytics_completed_types") if isinstance(tenant_state.get("analytics_completed_types"), list) else []
            login_status = str(tenant_state.get("login_status") or active_runtime.get("status") or "").strip() or "unknown"
            summary = "我从一线运行态判断当前自媒体链路还在持续推进。"
            current_judgement = (
                "当前首要专业问题是先恢复登录与发布入口。"
                if login_status in {"login_required", "waiting_login", "pending"}
                else "当前应继续围绕选题、发文和反馈数据形成下一轮专业判断。"
            )
            next_focus = (
                "先把账号环境与发布链路稳定住，再继续内容实验。"
                if login_status in {"login_required", "waiting_login", "pending"}
                else "结合这轮内容结果继续优化选题表达和反馈响应。"
            )
            evidence: list[str] = []
            if article_title:
                evidence.append(f"article:{article_title}")
            if analytics:
                evidence.append(f"analytics:{','.join(str(item) for item in analytics)}")
            if git_export.get("status"):
                evidence.append(f"export:{git_export.get('status')}")
            evidence.append(f"login:{login_status}")
            reflection_summary = summarize_recent_reflections(
                reflections=recent_reflections,
                evidence=evidence,
                fallback_focus=next_focus,
                blocked_reason="登录与发布入口未稳定" if login_status in {"login_required", "waiting_login", "pending"} else "",
                default_pattern="我持续围绕选题、发文、反馈和分发结果做专业判断。",
                default_summary="最近的一线反馈主要来自自媒体运营链路。",
            )
            return {
                "owner": "child_domain_expert",
                "summary": summary,
                "current_judgement": current_judgement,
                "next_professional_focus": next_focus,
                "evidence": evidence,
                "recent_reflections": recent_reflections,
                **reflection_summary,
            }

        status = str(active_runtime.get("status") or member.get("derived_state", {}).get("status") or "active").strip() or "active"
        blocked_reason = str(active_runtime.get("blocked_reason") or member.get("derived_state", {}).get("blocked_reason") or "").strip()
        next_action = str(active_runtime.get("next_action") or member.get("derived_state", {}).get("next_action") or "").strip()
        evidence = [signal for signal in (active_runtime.get("signals") if isinstance(active_runtime.get("signals"), list) else []) if isinstance(signal, str)]
        reflection_summary = summarize_recent_reflections(
            reflections=recent_reflections,
            evidence=evidence[:8],
            fallback_focus=next_action or "继续推进当前岗位的下一轮专业实践。",
            blocked_reason=blocked_reason,
            default_pattern=f"我正以 {role_label} 的岗位视角持续积累自己的做事方法。",
            default_summary=f"最近的岗位反馈主要围绕 {role_label} 的一线实践。",
        )
        return {
            "owner": "child_domain_expert",
            "summary": f"我是 {role_label}，当前专业判断仍以岗位实践现场为主。",
            "current_judgement": (
                f"当前主要专业阻塞是 {blocked_reason}。" if blocked_reason
                else f"当前专业状态为 {status}，可以继续沿着现有实践推进。"
            ),
            "next_professional_focus": next_action or "继续推进当前岗位的下一轮专业实践。",
            "evidence": evidence[:8],
            "recent_reflections": recent_reflections,
            **reflection_summary,
        }

    def build_member_experience_journal(member: dict, professional_view: dict, derived_state: dict, active_runtime: dict) -> dict:
        current_journal = member.get("experience_journal", {}) if isinstance(member.get("experience_journal"), dict) else {}
        cards = current_journal.get("cards") if isinstance(current_journal.get("cards"), list) else []
        normalized_cards = [item for item in cards if isinstance(item, dict)]
        if not bool((member.get("operating_contract", {}) if isinstance(member.get("operating_contract"), dict) else {}).get("must_record_experience", True)):
            return {
                "last_compiled_at": current_journal.get("last_compiled_at"),
                "latest_card_id": current_journal.get("latest_card_id"),
                "cards": normalized_cards[-24:],
            }

        role = str(member.get("primary_role") or "").strip() or "autonomous_child_agent"
        job_id = str(derived_state.get("active_job_id") or role).strip() or role
        stage = str((member.get("training_plan", {}) if isinstance(member.get("training_plan"), dict) else {}).get("stage") or "").strip() or "active_training"
        status = str(derived_state.get("status") or "").strip() or "active"
        summary = str(professional_view.get("reflection_summary") or "").strip()
        current_pattern = str(professional_view.get("current_pattern") or "").strip()
        professional_risk = str(professional_view.get("professional_risk") or "").strip()
        next_experiment = str(professional_view.get("next_experiment") or "").strip()
        evidence = [str(item).strip() for item in (professional_view.get("evidence") if isinstance(professional_view.get("evidence"), list) else []) if str(item).strip()]
        reflections = [str(item).strip() for item in (professional_view.get("recent_reflections") if isinstance(professional_view.get("recent_reflections"), list) else []) if str(item).strip()]

        if not any([summary, current_pattern, professional_risk, next_experiment, evidence, reflections]):
            return {
                "last_compiled_at": current_journal.get("last_compiled_at"),
                "latest_card_id": current_journal.get("latest_card_id"),
                "cards": normalized_cards[-24:],
            }

        card_title = (
            f"{job_id} {stage} 经验卡"
            if role != "talent_development"
            else f"{job_id} 培养观察卡"
        )
        signature = "|".join([
            role,
            job_id,
            stage,
            status,
            summary,
            next_experiment,
            ",".join(evidence[:4]),
        ])
        now_iso = datetime.now().isoformat()
        new_card = {
            "card_id": f"{job_id}:{int(datetime.now().timestamp() * 1000)}",
            "role": role,
            "job_id": job_id,
            "stage": stage,
            "status": status,
            "title": card_title,
            "summary": summary or str(professional_view.get("summary") or "").strip() or "岗位经验正在形成中。",
            "current_pattern": current_pattern or str(professional_view.get("current_judgement") or "").strip(),
            "professional_risk": professional_risk or (str(derived_state.get("blocked_reason") or "").strip() or "继续观察下一轮实践风险。"),
            "next_experiment": next_experiment or str(professional_view.get("next_professional_focus") or "").strip() or "继续推进下一轮专业实验。",
            "signature": signature,
            "evidence": evidence[:8],
            "source_reflections": reflections[:3],
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        next_cards = list(normalized_cards)
        if next_cards and str(next_cards[0].get("signature") or "") == signature:
            existing_card = next_cards[0]
            if (
                str(existing_card.get("summary") or "") == str(new_card.get("summary") or "")
                and str(existing_card.get("current_pattern") or "") == str(new_card.get("current_pattern") or "")
                and str(existing_card.get("professional_risk") or "") == str(new_card.get("professional_risk") or "")
                and str(existing_card.get("next_experiment") or "") == str(new_card.get("next_experiment") or "")
                and list(existing_card.get("evidence") or []) == list(new_card.get("evidence") or [])
                and list(existing_card.get("source_reflections") or []) == list(new_card.get("source_reflections") or [])
            ):
                return {
                    "last_compiled_at": current_journal.get("last_compiled_at"),
                    "latest_card_id": current_journal.get("latest_card_id"),
                    "cards": normalized_cards[-24:],
                }
            merged = {
                **existing_card,
                **new_card,
                "card_id": existing_card.get("card_id") or new_card["card_id"],
                "created_at": existing_card.get("created_at") or now_iso,
                "updated_at": now_iso,
            }
            next_cards[0] = merged
            latest_card_id = str(merged.get("card_id") or "")
        else:
            next_cards.insert(0, new_card)
            latest_card_id = new_card["card_id"]

        return {
            "last_compiled_at": now_iso,
            "latest_card_id": latest_card_id,
            "cards": next_cards[:24],
        }

    def build_self_media_job_runtime(job: dict, autonomy: dict, *, member: dict | None = None) -> dict:
        account_id = str(job.get("account_id") or "default").strip() or "default"
        account_state = get_toutiao_account_identity(workspace, account_id)
        executor_registry = describe_toutiao_executor_registry(workspace)
        self_media_runtime = autonomy.get("self_media", {}) if isinstance(autonomy.get("self_media"), dict) else {}
        tenant_states = self_media_runtime.get("tenants", {}) if isinstance(self_media_runtime.get("tenants"), dict) else {}
        member_id = str((member or {}).get("member_id") or "default").strip() or "default"
        tenant_state = tenant_states.get(member_id, {}) if isinstance(tenant_states.get(member_id), dict) else {}
        if not tenant_state:
            tenant_state = tenant_states.get("default", {}) if isinstance(tenant_states.get("default"), dict) else {}
        selected_executor = executor_registry.get("selected") if isinstance(executor_registry, dict) else None
        if not isinstance(selected_executor, dict) or not selected_executor.get("available"):
            return {
                "job_id": job.get("job_id"),
                "account_id": account_id,
                "status": "executor_missing",
                "blocked_reason": "toutiao_executor_missing",
                "next_action": "配置可用的 Toutiao Executor，恢复发布链路",
                "signals": ["executor unavailable"],
                "account": account_state,
            }
        if not account_state.get("logged_in"):
            profile = account_state.get("profile", {}) if isinstance(account_state.get("profile"), dict) else {}
            return {
                "job_id": job.get("job_id"),
                "account_id": account_id,
                "status": "waiting_login",
                "blocked_reason": str(profile.get("login_status") or "login_required"),
                "next_action": "完成头条账号登录接管，让子女智脑获得真实发布入口",
                "signals": [
                    f"account:{account_id}",
                    f"login_status:{str(profile.get('login_status') or 'pending')}",
                ],
                "account": account_state,
                "tenant_state": tenant_state,
            }
        if str(tenant_state.get("stage") or "").strip():
            git_export = tenant_state.get("git_export", {}) if isinstance(tenant_state.get("git_export"), dict) else {}
            stage = str(tenant_state.get("stage") or "ready_to_publish").strip() or "ready_to_publish"
            blocked_reason = tenant_state.get("blocked_reason")
            next_action = tenant_state.get("next_action") or "继续自主运营"
            if stage == "waiting_login" or str(blocked_reason or "").strip() in {"pending", "login_required", "waiting_login"}:
                stage = "ready_to_execute"
                blocked_reason = None
                next_action = "开始生成首篇内容草稿并进入反馈循环"
            return {
                "job_id": job.get("job_id"),
                "account_id": account_id,
                "status": stage,
                "blocked_reason": blocked_reason,
                "next_action": next_action,
                "signals": [
                    f"account:{account_id}",
                    *( [f"git:{git_export.get('status')}"] if git_export.get("status") else [] ),
                    *( [f"repo:{git_export.get('repo_key')}"] if git_export.get("repo_key") else [] ),
                    *( [f"article:{tenant_state.get('last_article_title')}"] if tenant_state.get("last_article_title") else [] ),
                    *( [f"analytics:{','.join(tenant_state.get('analytics_completed_types', []))}"] if isinstance(tenant_state.get("analytics_completed_types"), list) and tenant_state.get("analytics_completed_types") else [] ),
                ],
                "account": account_state,
                "tenant_state": tenant_state,
            }
        profile = account_state.get("profile", {}) if isinstance(account_state.get("profile"), dict) else {}
        return {
            "job_id": job.get("job_id"),
            "account_id": account_id,
            "status": "ready_to_publish",
            "blocked_reason": None,
            "next_action": "继续生成选题、起草内容、观察反馈并进入下一轮复盘",
            "signals": [
                f"account:{account_id}",
                f"display_name:{str(account_state.get('display_name') or '--')}",
                f"login_status:{str(profile.get('login_status') or 'ready')}",
            ],
            "account": account_state,
            "tenant_state": tenant_state,
        }

    def enrich_autonomy_runtime(runtime: dict) -> dict:
        autonomy = dict(runtime if isinstance(runtime, dict) else {})
        child_members = normalize_child_members_runtime(
            autonomy.get("child_members"),
            legacy_child_agent=autonomy.get("child_agent") if isinstance(autonomy.get("child_agent"), dict) else None,
        )
        normalized_items = [
            item for item in child_members.get("items", [])
            if isinstance(item, dict)
        ]
        selected_member_id = str(
            autonomy.get("primary_child_member_id")
            or child_members.get("selected_member_id")
            or ""
        ).strip() or child_members.get("selected_member_id")

        member_assignment_map: dict[str, list[dict]] = {}
        for candidate in normalized_items:
            if str(candidate.get("status") or "active").strip() == "archived":
                continue
            onboarding = candidate.get("onboarding", {}) if isinstance(candidate.get("onboarding"), dict) else {}
            owner_id = str(onboarding.get("training_owner_member_id") or "").strip()
            if not owner_id:
                continue
            member_assignment_map.setdefault(owner_id, []).append(candidate)

        derived_members: list[dict] = []
        selected_member: dict | None = None
        for member in normalized_items:
            if str(member.get("status") or "active").strip() == "archived":
                derived_members.append({
                    **member,
                    "derived_state": {
                        "status": "archived",
                        "blocked_reason": "member_archived",
                        "next_action": "已归档",
                        "signals": ["archived"],
                    },
                })
                continue
            growth_state = member.get("growth_state", {}) if isinstance(member.get("growth_state"), dict) else {}
            world_observation = member.get("world_observation", {}) if isinstance(member.get("world_observation"), dict) else {}
            training_plan = member.get("training_plan", {}) if isinstance(member.get("training_plan"), dict) else {}
            current_jobs = member.get("current_jobs", []) if isinstance(member.get("current_jobs"), list) else []
            derived_jobs: list[dict] = []
            active_job: dict | None = None
            for item in current_jobs:
                if not isinstance(item, dict):
                    continue
                runtime_state = None
                job_id = str(item.get("job_id") or "").strip()
                worker_id = resolve_primary_worker_id(workspace, member=member, work_type_id=job_id or None)
                runtime_state = build_operation_job_runtime(
                    workspace,
                    item,
                    autonomy,
                    member=member,
                    build_self_media_job_runtime=build_self_media_job_runtime,
                )
                derived_job = {
                    **item,
                    "runtime_state": runtime_state,
                }
                derived_jobs.append(derived_job)
                if active_job is None:
                    active_job = derived_job

            assigned_members = member_assignment_map.get(str(member.get("member_id") or "").strip(), [])
            training_stage_counts: dict[str, int] = {}
            for assigned_member in assigned_members:
                assigned_plan = assigned_member.get("training_plan", {}) if isinstance(assigned_member.get("training_plan"), dict) else {}
                stage = str(assigned_plan.get("stage") or assigned_member.get("onboarding", {}).get("status") or "profile_initialized").strip() or "profile_initialized"
                training_stage_counts[stage] = training_stage_counts.get(stage, 0) + 1
            next_training_target = next(
                (
                    {
                        "member_id": item.get("member_id"),
                        "name": item.get("name"),
                        "primary_role": item.get("primary_role"),
                        "stage": (item.get("training_plan", {}) if isinstance(item.get("training_plan"), dict) else {}).get("stage"),
                        "next_action": (item.get("training_plan", {}) if isinstance(item.get("training_plan"), dict) else {}).get("next_action"),
                    }
                    for item in assigned_members
                    if isinstance(item, dict)
                ),
                None,
            )
            self_development = None

            active_runtime = active_job.get("runtime_state") if isinstance(active_job, dict) and isinstance(active_job.get("runtime_state"), dict) else {}
            derived_status = active_runtime.get("status") or growth_state.get("phase") or autonomy.get("status") or "idle"
            derived_next_action = active_runtime.get("next_action") or growth_state.get("next_goal")
            derived_signals = active_runtime.get("signals") or []
            if str(member.get("primary_role") or "") == "talent_development":
                if len(assigned_members) >= 4:
                    development_level = "orchestration"
                elif len(assigned_members) >= 2:
                    development_level = "coaching"
                else:
                    development_level = "foundation"
                completed_cycle_count = sum(
                    count for stage, count in training_stage_counts.items()
                    if stage in {"active_training", "delivering", "stabilizing", "stable"}
                )
                self_development = {
                    "level": development_level,
                    "focus": [
                        "岗位画像建模",
                        "训练路径设计",
                        "成长纠偏复盘",
                    ],
                    "current_objective": str(growth_state.get("next_goal") or training_plan.get("next_action") or "持续提升培养质量"),
                    "next_milestone": (
                        "让至少一个子女稳定完成从建档到经验沉淀的完整周期"
                        if completed_cycle_count <= 0
                        else "把培养流程抽象成可复用模板并推动更多子女稳定成长"
                    ),
                    "growth_signals": [
                        f"assigned_children:{len(assigned_members)}",
                        f"training_cycles:{completed_cycle_count}",
                        f"active_stages:{len(training_stage_counts)}",
                    ],
                    "missing_capabilities": (
                        ["跨岗位培养样本不足", "自动纠偏策略仍需沉淀"]
                        if len(assigned_members) < 2
                        else ["批量培养编排能力仍需增强"]
                    ),
                }
                if assigned_members:
                    derived_status = "training_children"
                    derived_next_action = str(training_plan.get("next_action") or "继续跟进已接管子女的训练进度")
                    derived_signals = [
                        f"assigned_children:{len(assigned_members)}",
                        *[f"{key}:{value}" for key, value in sorted(training_stage_counts.items())],
                    ]
                else:
                    derived_status = "awaiting_assignment"
                    derived_next_action = str(training_plan.get("next_action") or "等待新的子女画像建立请求")
                    derived_signals = ["assigned_children:0"]
            derived_state = {
                "active_job_id": active_job.get("job_id") if isinstance(active_job, dict) else None,
                "active_job_title": active_job.get("title") if isinstance(active_job, dict) else None,
                "status": derived_status,
                "blocked_reason": active_runtime.get("blocked_reason") or growth_state.get("blocked_reason"),
                "next_action": derived_next_action,
                "signals": derived_signals,
            }
            adapted_training_plan, training_autopilot = derive_member_training_plan(member, derived_state, active_runtime)
            professional_view = build_professional_view(member, active_runtime, autonomy.get("relationship_center"))
            experience_journal = build_member_experience_journal(member, professional_view, derived_state, active_runtime)
            memory_hub = build_member_memory_hub(
                workspace=workspace,
                tenant_manager=tenant_manager,
                task_queue=task_queue,
                tenant_id=resolve_tenant_id(autonomy.get("tenant_id")),
                runtime=autonomy,
                member={
                    **member,
                    "current_jobs": derived_jobs,
                    "growth_state": {
                        **growth_state,
                        "blocked_reason": derived_state.get("blocked_reason") or growth_state.get("blocked_reason"),
                    },
                    "training_plan": adapted_training_plan,
                    "experience_journal": experience_journal,
                    "professional_view": professional_view,
                    "derived_state": derived_state,
                },
                trigger="status_refresh",
            )

            enriched_member = {
                **member,
                "growth_state": {
                    **growth_state,
                    "blocked_reason": derived_state.get("blocked_reason") or growth_state.get("blocked_reason"),
                },
                "current_jobs": derived_jobs,
                "world_observation": {
                    **world_observation,
                    "blocked_by": derived_state.get("signals") or world_observation.get("blocked_by") or [],
                },
                "training_plan": adapted_training_plan,
                "training_autopilot": training_autopilot,
                "professional_view": professional_view,
                "experience_journal": experience_journal,
                "training_overview": {
                    "assigned_children_count": len(assigned_members),
                    "stage_counts": training_stage_counts,
                    "next_target": next_training_target,
                    "owned_member_ids": [
                        str(item.get("member_id") or "")
                        for item in assigned_members
                        if isinstance(item, dict) and str(item.get("member_id") or "").strip()
                    ],
                },
                "self_development": self_development,
                "derived_state": derived_state,
                "memory_hub": memory_hub,
                "decision_state": memory_hub.get("decision_state", {}),
                "retrieval_state": memory_hub.get("retrieval_state", {}),
                "active_case_id": memory_hub.get("active_case_id"),
                "last_decision_snapshot": memory_hub.get("last_decision_snapshot"),
                "decision_history": (
                    memory_hub.get("decision_history", [])
                    if isinstance(memory_hub.get("decision_history"), list)
                    else []
                ),
            }
            derived_members.append(enriched_member)
            if selected_member is None and str(enriched_member.get("member_id") or "") == str(selected_member_id or ""):
                selected_member = enriched_member

        if selected_member is None and derived_members:
            selected_member = derived_members[0]
            selected_member_id = str(selected_member.get("member_id") or "")

        autonomy["child_members"] = {
            "selected_member_id": selected_member_id,
            "items": derived_members,
        }
        autonomy["primary_child_member_id"] = selected_member_id
        autonomy["child_agent"] = normalize_child_agent_runtime(selected_member if isinstance(selected_member, dict) else {})
        from admin.intake_runtime import build_intake_funnel, normalize_intake_center

        intake_center = normalize_intake_center(autonomy.get("intake_center"))
        autonomy["intake_center"] = intake_center
        autonomy["intake_funnel"] = build_intake_funnel(intake_center)
        return autonomy

    def persist_autonomy_training_updates(runtime: dict, *, trigger: str = "system", force_persist: bool = False) -> tuple[dict, dict]:
        enriched = enrich_autonomy_runtime(runtime)
        runtime_tenant_id = resolve_tenant_id(enriched.get("tenant_id") or runtime.get("tenant_id"))
        current_members = (
            runtime.get("child_members", {}).get("items", [])
            if isinstance(runtime.get("child_members"), dict)
            else []
        )
        next_members = (
            enriched.get("child_members", {}).get("items", [])
            if isinstance(enriched.get("child_members"), dict)
            else []
        )
        current_map = {
            str(item.get("member_id") or ""): item
            for item in current_members
            if isinstance(item, dict) and str(item.get("member_id") or "").strip()
        }
        changed_members: list[dict] = []
        training_changed_count = 0
        experience_changed_count = 0
        for item in next_members:
            if not isinstance(item, dict):
                continue
            member_id = str(item.get("member_id") or "").strip()
            if not member_id:
                continue
            current_item = current_map.get(member_id, {})
            current_plan = current_item.get("training_plan", {}) if isinstance(current_item.get("training_plan"), dict) else {}
            next_plan = item.get("training_plan", {}) if isinstance(item.get("training_plan"), dict) else {}
            current_growth = current_item.get("growth_state", {}) if isinstance(current_item.get("growth_state"), dict) else {}
            next_growth = item.get("growth_state", {}) if isinstance(item.get("growth_state"), dict) else {}
            current_journal = current_item.get("experience_journal", {}) if isinstance(current_item.get("experience_journal"), dict) else {}
            next_journal = item.get("experience_journal", {}) if isinstance(item.get("experience_journal"), dict) else {}
            plan_or_growth_changed = current_plan != next_plan or current_growth.get("blocked_reason") != next_growth.get("blocked_reason")
            journal_changed = current_journal != next_journal
            if current_journal != next_journal:
                record_member_experience_journal(
                    workspace,
                    runtime_tenant_id,
                    member=item,
                    journal=next_journal,
                    source=f"system_runtime:{trigger}",
                )
            if plan_or_growth_changed:
                training_changed_count += 1
            if journal_changed:
                experience_changed_count += 1
            if plan_or_growth_changed or journal_changed:
                changed_members.append({
                    "member_id": member_id,
                    "name": item.get("name"),
                    "primary_role": item.get("primary_role"),
                    "training_stage": next_plan.get("stage"),
                    "next_action": next_plan.get("next_action"),
                    "latest_experience_card_id": next_journal.get("latest_card_id"),
                    "training_updated": plan_or_growth_changed,
                    "experience_updated": journal_changed,
                })
        if training_changed_count and experience_changed_count:
            review_message = f"育成官已更新 {training_changed_count} 个子女的训练状态，并沉淀 {experience_changed_count} 份岗位经验"
        elif training_changed_count:
            review_message = f"育成官已更新 {training_changed_count} 个子女的训练计划"
        elif experience_changed_count:
            review_message = f"育成官已沉淀 {experience_changed_count} 份新的岗位经验"
        else:
            review_message = "育成官巡检完成，当前没有新的训练或经验变化"
        enriched["training_review"] = {
            "last_review_at": datetime.now().isoformat(),
            "last_trigger": trigger,
            "changed_count": len(changed_members),
            "changed_members": changed_members[:20],
            "last_message": review_message,
        }
        should_save = bool(changed_members) or force_persist
        if should_save:
            save_autonomy_runtime(workspace, enriched, runtime_tenant_id)
            enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, runtime_tenant_id))
        return enriched, {
            "saved": should_save,
            "changed_members": changed_members,
            "changed_count": len(changed_members),
            "message": review_message,
        }

    @app.get("/api/autonomy/status")
    async def get_autonomy_status(tenant_id: str = "default"):
        normalized_tenant_id = resolve_tenant_id(tenant_id)
        enriched, _ = persist_autonomy_training_updates(
            load_autonomy_runtime(workspace, normalized_tenant_id),
            trigger="status_refresh",
        )
        return success_response(enriched)

    @app.get("/api/autonomy/memory-hub/status")
    async def get_autonomy_memory_hub_status(tenant_id: str = "default", member_id: str | None = None):
        normalized_tenant_id = resolve_tenant_id(tenant_id)
        enriched, _ = persist_autonomy_training_updates(
            load_autonomy_runtime(workspace, normalized_tenant_id),
            trigger="memory_hub_status",
        )
        members = (
            enriched.get("child_members", {}).get("items", [])
            if isinstance(enriched.get("child_members"), dict)
            else []
        )
        preferred_member_id = str(member_id or "").strip()
        if not preferred_member_id:
            preferred_member = next(
                (
                    item for item in members
                    if isinstance(item, dict) and str(item.get("primary_role") or "").strip() != "talent_development"
                ),
                None,
            )
            preferred_member_id = str(
                (preferred_member or {}).get("member_id")
                or enriched.get("primary_child_member_id")
                or ""
            ).strip()
        target_member = next(
            (
                item for item in members
                if isinstance(item, dict)
                and str(item.get("member_id") or "").strip() == preferred_member_id
            ),
            members[0] if members else None,
        )
        return success_response({
            "tenant_id": normalized_tenant_id,
            "member_id": str((target_member or {}).get("member_id") or "").strip() or None,
            "memory_hub": (target_member or {}).get("memory_hub") if isinstance(target_member, dict) else None,
            "last_decision_snapshot": (target_member or {}).get("last_decision_snapshot") if isinstance(target_member, dict) else None,
            "decision_history": (target_member or {}).get("decision_history", []) if isinstance(target_member, dict) else [],
        })

    @app.post("/api/autonomy/memory-hub/run")
    async def run_autonomy_memory_hub(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        member_id = str(payload.get("member_id") or "").strip()
        trigger = str(payload.get("trigger") or "manual_run").strip() or "manual_run"
        if not member_id:
            return error_response("member_id 必填", 400)
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        current_members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        if not any(
            isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id
            for item in current_members.get("items", [])
        ):
            return error_response("目标员工不存在", 404)
        runtime = sync_runtime_memory_hub(
            workspace=workspace,
            tenant_manager=tenant_manager,
            task_queue=task_queue,
            tenant_id=normalized_tenant_id,
            runtime=runtime,
            target_member_id=member_id,
            trigger=trigger,
            append_history=True,
        )
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        apply_member_knowledge_learning_if_needed(
            runtime=runtime,
            normalized_tenant_id=normalized_tenant_id,
            member_id=member_id,
            trigger=trigger,
        )
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, normalized_tenant_id))
        target_member = next(
            (
                item for item in (
                    enriched.get("child_members", {}).get("items", [])
                    if isinstance(enriched.get("child_members"), dict)
                    else []
                )
                if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id
            ),
            None,
        )
        return success_response({
            "autonomy": enriched,
            "memory_hub": target_member.get("memory_hub") if isinstance(target_member, dict) else None,
            "last_decision_snapshot": target_member.get("last_decision_snapshot") if isinstance(target_member, dict) else None,
        }, "员工记忆中枢已刷新")

    @app.post("/api/autonomy/memory-hub/replay")
    async def replay_autonomy_memory_hub(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        member_id = str(payload.get("member_id") or "").strip()
        case_id = str(payload.get("case_id") or "").strip()
        if not member_id:
            return error_response("member_id 必填", 400)
        if not case_id:
            return error_response("case_id 必填", 400)
        enriched, _ = persist_autonomy_training_updates(
            load_autonomy_runtime(workspace, normalized_tenant_id),
            trigger="memory_hub_replay",
        )
        members = (
            enriched.get("child_members", {}).get("items", [])
            if isinstance(enriched.get("child_members"), dict)
            else []
        )
        target_member = next(
            (
                item for item in members
                if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id
            ),
            None,
        )
        if not isinstance(target_member, dict):
            return error_response("目标员工不存在", 404)
        history = target_member.get("decision_history", []) if isinstance(target_member.get("decision_history"), list) else []
        snapshot = next(
            (
                item for item in history
                if isinstance(item, dict) and str(item.get("case_id") or "").strip() == case_id
            ),
            None,
        )
        if snapshot is None:
            current = target_member.get("last_decision_snapshot", {}) if isinstance(target_member.get("last_decision_snapshot"), dict) else {}
            if str(current.get("case_id") or "").strip() == case_id:
                snapshot = current
        if not isinstance(snapshot, dict):
            return error_response("目标决策快照不存在", 404)
        return success_response({
            "tenant_id": normalized_tenant_id,
            "member_id": member_id,
            "snapshot": snapshot,
        }, "已返回指定决策快照")

    @app.post("/api/autonomy/training-review")
    async def run_autonomy_training_review(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        enriched, review_summary = persist_autonomy_training_updates(
            load_autonomy_runtime(workspace, normalized_tenant_id),
            trigger="manual_review",
            force_persist=True,
        )
        changed_count = int(review_summary.get("changed_count", 0) or 0)
        message = review_summary.get("message") if changed_count or review_summary.get("message") else "育成官巡检完成"
        return success_response({
            "autonomy": enriched,
            "review_summary": review_summary,
        }, message)

    @app.post("/api/autonomy/relationship/parent-message")
    async def post_parent_message(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        target_member_id = str(payload.get("target_member_id") or "").strip()
        content = str(payload.get("content") or "").strip()
        title = str(payload.get("title") or "").strip()
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        if not target_member_id:
            return error_response("target_member_id 必填", 400)
        if not content:
            return error_response("content 必填", 400)
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        target_member = next(
            (
                item for item in members.get("items", [])
                if isinstance(item, dict) and str(item.get("member_id") or "").strip() == target_member_id
            ),
            None,
        )
        if not isinstance(target_member, dict):
            return error_response("目标子女不存在", 404)
        relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}
        training_plan = target_member.get("training_plan", {}) if isinstance(target_member.get("training_plan"), dict) else {}
        growth_state = target_member.get("growth_state", {}) if isinstance(target_member.get("growth_state"), dict) else {}
        onboarding = target_member.get("onboarding", {}) if isinstance(target_member.get("onboarding"), dict) else {}
        directive_snapshot = {
            "member_name": str(target_member.get("name") or target_member_id),
            "primary_role": str(target_member.get("primary_role") or ""),
            "training_stage": str(training_plan.get("stage") or onboarding.get("status") or ""),
            "next_action": str(training_plan.get("next_action") or ""),
            "current_focus": str(growth_state.get("current_focus") or ""),
        }
        append_relationship_message(
            relationship_center,
            thread_id=f"parent:{target_member_id}",
            participants=["parent_node", target_member_id],
            sender_member_id="parent_node",
            sender_role="parent",
            message_type="parent_guidance",
            content=content,
            metadata={
                "target_member_id": target_member_id,
                "directive_snapshot": directive_snapshot,
                **metadata,
            },
        )
        append_parent_inbox_message(relationship_center, {
            "message_id": f"parent-outbound:{int(datetime.now().timestamp() * 1000)}",
            "sender_member_id": "parent_node",
            "sender_role": "parent",
            "message_type": "parent_guidance",
            "title": title or f"父节点留言给 {target_member.get('name') or target_member_id}",
            "content": content,
            "created_at": datetime.now().isoformat(),
            "metadata": {
                "target_member_id": target_member_id,
                "directive_snapshot": directive_snapshot,
                **metadata,
            },
        })
        relationship_center["last_delivery_at"] = datetime.now().isoformat()
        runtime["relationship_center"] = relationship_center
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, normalized_tenant_id))
        return success_response(enriched, "父节点留言已送达内部关系层")

    @app.post("/api/autonomy/relationship/child-reply")
    async def post_child_reply(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        member_id = str(payload.get("member_id") or "").strip()
        content = str(payload.get("content") or "").strip()
        if not member_id:
            return error_response("member_id 必填", 400)
        if not content:
            return error_response("content 必填", 400)
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        target_member = next(
            (
                item for item in members.get("items", [])
                if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id
            ),
            None,
        )
        if not isinstance(target_member, dict):
            return error_response("目标子女不存在", 404)
        relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}
        append_relationship_message(
            relationship_center,
            thread_id=f"trainer:{member_id}",
            participants=["talent_development_officer", member_id],
            sender_member_id=member_id,
            sender_role=str(target_member.get("primary_role") or "child_agent"),
            message_type="child_reply",
            content=content,
            metadata={"member_id": member_id},
        )
        append_parent_inbox_message(relationship_center, {
            "message_id": f"child-reply:{int(datetime.now().timestamp() * 1000)}",
            "sender_member_id": member_id,
            "sender_role": str(target_member.get("primary_role") or "child_agent"),
            "message_type": "child_reply",
            "title": f"{target_member.get('name') or member_id} 的反馈",
            "content": content,
            "created_at": datetime.now().isoformat(),
            "metadata": {"member_id": member_id},
        })
        trainer_reply, trainer_reply_metadata = build_trainer_reply(
            member=target_member,
            content=content,
        )
        append_relationship_message(
            relationship_center,
            thread_id=f"trainer:{member_id}",
            participants=["talent_development_officer", member_id],
            sender_member_id="talent_development_officer",
            sender_role="talent_development",
            message_type="trainer_reply",
            content=trainer_reply,
            metadata=trainer_reply_metadata,
        )
        append_parent_inbox_message(relationship_center, {
            "message_id": f"trainer-reply:{int(datetime.now().timestamp() * 1000)}",
            "sender_member_id": "talent_development_officer",
            "sender_role": "talent_development",
            "message_type": "trainer_reply",
            "title": f"育成官回复 {target_member.get('name') or member_id}",
            "content": trainer_reply,
            "created_at": datetime.now().isoformat(),
            "metadata": {
                "member_id": member_id,
                **trainer_reply_metadata,
            },
        })
        relationship_center["last_delivery_at"] = datetime.now().isoformat()
        runtime["relationship_center"] = relationship_center
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, normalized_tenant_id))
        return success_response(enriched, "子女反馈已写入关系层")

    @app.post("/api/autonomy/relationship/trainer-action")
    async def post_trainer_action(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        member_id = str(payload.get("member_id") or "").strip()
        content = str(payload.get("content") or "").strip()
        action_type = str(payload.get("action_type") or "").strip() or "trainer_action"
        title = str(payload.get("title") or "").strip()
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        if not member_id:
            return error_response("member_id 必填", 400)
        if not content:
            return error_response("content 必填", 400)
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        target_member = next(
            (
                item for item in members.get("items", [])
                if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id
            ),
            None,
        )
        if not isinstance(target_member, dict):
            return error_response("目标子女不存在", 404)
        relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}
        append_relationship_message(
            relationship_center,
            thread_id=f"trainer:{member_id}",
            participants=["talent_development_officer", member_id],
            sender_member_id="talent_development_officer",
            sender_role="talent_development",
            message_type="training_update",
            content=content,
            metadata={
                "member_id": member_id,
                "action_type": action_type,
                **metadata,
            },
        )
        append_parent_inbox_message(relationship_center, {
            "message_id": f"trainer-action:{int(datetime.now().timestamp() * 1000)}",
            "sender_member_id": "talent_development_officer",
            "sender_role": "talent_development",
            "message_type": "training_update",
            "title": title or f"育成官处理 {target_member.get('name') or member_id}",
            "content": content,
            "created_at": datetime.now().isoformat(),
            "metadata": {
                "member_id": member_id,
                "action_type": action_type,
                **metadata,
            },
        })
        relationship_center["last_delivery_at"] = datetime.now().isoformat()
        runtime["relationship_center"] = relationship_center
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, normalized_tenant_id))
        return success_response(enriched, "育成官处理动作已写入关系层")

    @app.post("/api/autonomy/tasks/assign")
    async def assign_autonomy_task(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        member_id = str(payload.get("member_id") or "").strip()
        recommendation_id = str(payload.get("recommendation_id") or "").strip()
        title = str(payload.get("title") or "").strip()
        objective = str(payload.get("objective") or "").strip()
        deliverables = payload.get("deliverables")
        deliverable_items = [str(item).strip() for item in (deliverables if isinstance(deliverables, list) else []) if str(item).strip()]
        if not member_id:
            return error_response("member_id 必填", 400)
        if not title:
            return error_response("title 必填", 400)
        if not objective:
            return error_response("objective 必填", 400)
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        members = normalize_child_members_runtime(runtime.get("child_members"))
        target_member = next(
            (item for item in members.get("items", []) if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id),
            None,
        )
        if not isinstance(target_member, dict):
            return error_response("目标子女不存在", 404)
        task_center = runtime.get("task_center", {}) if isinstance(runtime.get("task_center"), dict) else {}
        recommendations = task_center.get("recommendations") if isinstance(task_center.get("recommendations"), list) else []
        selected_recommendation = next(
            (
                item for item in recommendations
                if isinstance(item, dict) and str(item.get("recommendation_id") or "").strip() == recommendation_id
            ),
            None,
        ) if recommendation_id else None
        now_iso = datetime.now().isoformat()
        task_id = f"task:{member_id}:{int(datetime.now().timestamp() * 1000)}"
        task = upsert_task(task_center, {
            "task_id": task_id,
            "member_id": member_id,
            "assigned_by_member_id": "talent_development_officer",
            "title": title,
            "objective": objective,
            "deliverables": deliverable_items,
            "status": "assigned",
            "assigned_at": now_iso,
            "started_at": None,
            "submitted_at": None,
            "approved_at": None,
            "result_summary": None,
            "reflection": None,
            "review_note": None,
            "metadata": {
                **(payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}),
                **({"recommendation_id": recommendation_id} if recommendation_id else {}),
            },
        })
        if isinstance(selected_recommendation, dict):
            selected_recommendation["status"] = "adopted"
            selected_recommendation["adopted_at"] = now_iso
        relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}
        append_relationship_message(
            relationship_center,
            thread_id=f"trainer:{member_id}",
            participants=["talent_development_officer", member_id],
            sender_member_id="talent_development_officer",
            sender_role="talent_development",
            message_type="task_assignment",
            content=f"已为你分配正式任务：{title}。目标是：{objective}",
            metadata={
                "member_id": member_id,
                "task_id": task_id,
                "deliverables": deliverable_items,
                **({"recommendation_id": recommendation_id} if recommendation_id else {}),
            },
        )
        runtime["task_center"] = task_center
        runtime["relationship_center"] = relationship_center
        runtime = sync_runtime_memory_hub(
            workspace=workspace,
            tenant_manager=tenant_manager,
            task_queue=task_queue,
            tenant_id=normalized_tenant_id,
            runtime=runtime,
            target_member_id=member_id,
            trigger="task_assigned",
            append_history=True,
        )
        apply_member_knowledge_learning_if_needed(
            runtime=runtime,
            normalized_tenant_id=normalized_tenant_id,
            member_id=member_id,
            trigger="task_assigned",
        )
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        enriched, _ = persist_autonomy_training_updates(
            load_autonomy_runtime(workspace, normalized_tenant_id),
            trigger="task_assigned",
            force_persist=False,
        )
        return success_response({"autonomy": enriched, "task": task}, "育成官已分配首轮正式任务")

    @app.post("/api/autonomy/tasks/submit")
    async def submit_autonomy_task(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        task_id = str(payload.get("task_id") or "").strip()
        result_summary = str(payload.get("result_summary") or "").strip()
        reflection = str(payload.get("reflection") or "").strip()
        if not task_id:
            return error_response("task_id 必填", 400)
        if not result_summary:
            return error_response("result_summary 必填", 400)
        if not reflection:
            return error_response("reflection 必填", 400)
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        task_center = runtime.get("task_center", {}) if isinstance(runtime.get("task_center"), dict) else {}
        items = task_center.get("items") if isinstance(task_center.get("items"), list) else []
        task = next((item for item in items if isinstance(item, dict) and str(item.get("task_id") or "").strip() == task_id), None)
        if not isinstance(task, dict):
            return error_response("任务不存在", 404)
        member_id = str(task.get("member_id") or "").strip()
        now_iso = datetime.now().isoformat()
        task["status"] = "submitted"
        task["started_at"] = task.get("started_at") or now_iso
        task["submitted_at"] = now_iso
        task["result_summary"] = result_summary
        task["reflection"] = reflection
        relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}
        append_relationship_message(
            relationship_center,
            thread_id=f"trainer:{member_id}",
            participants=["talent_development_officer", member_id],
            sender_member_id=member_id,
            sender_role="child_agent",
            message_type="mission_reflection",
            content=f"任务结果：{result_summary}\n复盘：{reflection}",
            metadata={"member_id": member_id, "task_id": task_id, "mission_status": "submitted"},
        )
        runtime["task_center"] = task_center
        runtime["relationship_center"] = relationship_center
        runtime = sync_runtime_memory_hub(
            workspace=workspace,
            tenant_manager=tenant_manager,
            task_queue=task_queue,
            tenant_id=normalized_tenant_id,
            runtime=runtime,
            target_member_id=member_id,
            trigger="task_submitted",
            append_history=True,
        )
        apply_member_knowledge_learning_if_needed(
            runtime=runtime,
            normalized_tenant_id=normalized_tenant_id,
            member_id=member_id,
            trigger="task_submitted",
        )
        maybe_mark_provider_collaboration_submitted(runtime=runtime, task=task)
        mark_intake_in_progress_from_task(runtime=runtime, task=task)
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        enriched, _ = persist_autonomy_training_updates(
            load_autonomy_runtime(workspace, normalized_tenant_id),
            trigger="task_submitted",
            force_persist=False,
        )
        return success_response({"autonomy": enriched, "task": task}, "子女已提交任务结果与复盘")

    @app.post("/api/autonomy/tasks/approve")
    async def approve_autonomy_task(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        task_id = str(payload.get("task_id") or "").strip()
        review_note = str(payload.get("review_note") or "").strip()
        if not task_id:
            return error_response("task_id 必填", 400)
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        task_center = runtime.get("task_center", {}) if isinstance(runtime.get("task_center"), dict) else {}
        items = task_center.get("items") if isinstance(task_center.get("items"), list) else []
        task = next((item for item in items if isinstance(item, dict) and str(item.get("task_id") or "").strip() == task_id), None)
        if not isinstance(task, dict):
            return error_response("任务不存在", 404)
        member_id = str(task.get("member_id") or "").strip()
        members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        target_member = next(
            (item for item in members.get("items", []) if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id),
            None,
        )
        task["status"] = "approved"
        task["approved_at"] = datetime.now().isoformat()
        task["review_note"] = review_note or "育成官确认本轮任务完成，可以进入下一轮成长。"
        _collaboration_finalized = maybe_finalize_provider_collaboration(
            workspace=workspace,
            runtime=runtime,
            task=task,
            append_relationship_message=append_relationship_message,
        )
        mark_intake_delivered_from_task(runtime=runtime, task=task)
        relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}
        append_relationship_message(
            relationship_center,
            thread_id=f"trainer:{member_id}",
            participants=["talent_development_officer", member_id],
            sender_member_id="talent_development_officer",
            sender_role="talent_development",
            message_type="trainer_growth_comment",
            content=task["review_note"],
            metadata={"member_id": member_id, "task_id": task_id, "mission_status": "approved"},
        )
        if isinstance(target_member, dict):
            current_journal = target_member.get("experience_journal", {}) if isinstance(target_member.get("experience_journal"), dict) else {}
            cards = current_journal.get("cards") if isinstance(current_journal.get("cards"), list) else []
            completion_card = build_task_completion_experience_card(target_member, task)
            next_cards = [completion_card] + [
                item for item in cards
                if isinstance(item, dict) and str(item.get("signature") or "") != str(completion_card.get("signature") or "")
            ]
            target_member["experience_journal"] = {
                "last_compiled_at": completion_card["updated_at"],
                "latest_card_id": completion_card["card_id"],
                "cards": next_cards[:24],
            }
            target_member["growth_state"] = {
                **(target_member.get("growth_state") if isinstance(target_member.get("growth_state"), dict) else {}),
                "current_focus": "沉淀本轮经验并准备下一轮任务",
                "next_goal": "把本轮有效动作转成更稳定的岗位方法",
                "last_reflection_at": completion_card["updated_at"],
            }
            target_member["training_plan"] = {
                **(target_member.get("training_plan") if isinstance(target_member.get("training_plan"), dict) else {}),
                "stage": "first_reflection_done",
                "next_action": "导出本轮经验并准备下一轮正式任务",
                "review_after": None,
            }
            target_member["onboarding"] = {
                **(target_member.get("onboarding") if isinstance(target_member.get("onboarding"), dict) else {}),
                "status": "first_reflection_done",
                "notes": f"{str((target_member.get('onboarding') if isinstance(target_member.get('onboarding'), dict) else {}).get('notes') or '').strip()} 首轮正式任务已确认完成，并生成经验卡。".strip(),
            }
            member_jobs = target_member.get("current_jobs") if isinstance(target_member.get("current_jobs"), list) else []
            if member_jobs and isinstance(member_jobs[0], dict):
                member_jobs[0] = {
                    **member_jobs[0],
                    "status": "first_case_reflected",
                }
                target_member["current_jobs"] = member_jobs
            active_job = member_jobs[0] if member_jobs and isinstance(member_jobs[0], dict) else {}
            worker_id = resolve_primary_worker_id(workspace, member=target_member)
            if worker_id and worker_uses_self_media_tenant_bucket(worker_id):
                self_media_runtime = runtime.get("self_media", {}) if isinstance(runtime.get("self_media"), dict) else {}
                tenant_states = self_media_runtime.get("tenants", {}) if isinstance(self_media_runtime.get("tenants"), dict) else {}
                member_state = tenant_states.get(member_id, {}) if isinstance(tenant_states.get(member_id), dict) else {}
                member_state = {
                    **member_state,
                    "account_id": str(active_job.get("account_id") or member_state.get("account_id") or "default").strip() or "default",
                    "topic": str(task.get("title") or member_state.get("topic") or "").strip() or None,
                    "target_outcome": str(task.get("objective") or active_job.get("target_outcome") or member_state.get("target_outcome") or "").strip() or None,
                    "stage": "first_reflection_done",
                    "blocked_reason": None,
                    "next_action": "继续准备下一轮正式任务，并让经验持续入库",
                    "last_draft_summary": str(task.get("result_summary") or member_state.get("last_draft_summary") or "").strip() or None,
                    "last_feedback_summary": {
                        "result_summary": str(task.get("result_summary") or "").strip() or None,
                        "reflection": str(task.get("reflection") or "").strip() or None,
                        "review_note": str(task.get("review_note") or "").strip() or None,
                    },
                    "last_task_id": str(task.get("task_id") or "").strip() or None,
                    "last_task_status": "approved",
                    "last_decision_at": datetime.now().isoformat(),
                }
                tenant_states[member_id] = member_state
                self_media_runtime["tenants"] = tenant_states
                runtime["self_media"] = self_media_runtime
            runtime["child_members"] = members
        runtime["task_center"] = task_center
        runtime["relationship_center"] = relationship_center
        runtime = sync_runtime_memory_hub(
            workspace=workspace,
            tenant_manager=tenant_manager,
            task_queue=task_queue,
            tenant_id=normalized_tenant_id,
            runtime=runtime,
            target_member_id=member_id,
            trigger="task_approved",
            append_history=True,
        )
        apply_member_knowledge_learning_if_needed(
            runtime=runtime,
            normalized_tenant_id=normalized_tenant_id,
            member_id=member_id,
            trigger="task_approved",
        )
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        evolution_summary: dict = {}
        review_summary: dict = {}
        if isinstance(target_member, dict):
            record_member_experience_journal(
                workspace,
                normalized_tenant_id,
                member=target_member,
                journal=target_member.get("experience_journal", {}),
                source="system_runtime:task_approved",
            )
            export_runtime: dict = {}
            if member_uses_operation_automation(workspace, target_member):
                export_runtime = await auto_export_member_experience_to_git(
                    request=request,
                    tenant_id=normalized_tenant_id,
                    member=target_member,
                    runtime=runtime,
                    task=task,
                )
                self_media_runtime = runtime.get("self_media", {}) if isinstance(runtime.get("self_media"), dict) else {}
                tenant_states = self_media_runtime.get("tenants", {}) if isinstance(self_media_runtime.get("tenants"), dict) else {}
                member_state = tenant_states.get(member_id, {}) if isinstance(tenant_states.get(member_id), dict) else {}
                member_state["git_export"] = export_runtime
                if export_runtime.get("status") == "failed":
                    member_state["blocked_reason"] = str(export_runtime.get("reason") or "git_export_failed").strip() or "git_export_failed"
                    member_state["next_action"] = str(export_runtime.get("next_action") or "检查经验仓导出失败原因").strip() or "检查经验仓导出失败原因"
                tenant_states[member_id] = member_state
                self_media_runtime["tenants"] = tenant_states
                runtime["self_media"] = self_media_runtime
                save_autonomy_runtime(workspace, runtime, normalized_tenant_id)

            auto_followup_content, auto_followup_metadata = build_trainer_auto_growth_followup(
                member=target_member,
                task=task,
                export_runtime=export_runtime,
            )
            next_recommendation = build_next_formal_task_recommendation(
                member=target_member,
                task=task,
                export_runtime=export_runtime if export_runtime else None,
            )
            upsert_task_recommendation(task_center, next_recommendation)
            append_relationship_message(
                relationship_center,
                thread_id=f"trainer:{member_id}",
                participants=["talent_development_officer", member_id],
                sender_member_id="talent_development_officer",
                sender_role="talent_development",
                message_type="trainer_growth_comment",
                content=auto_followup_content,
                metadata=auto_followup_metadata,
            )
            memory_hub = target_member.get("memory_hub") if isinstance(target_member.get("memory_hub"), dict) else {}
            decision_state = memory_hub.get("decision_state") if isinstance(memory_hub.get("decision_state"), dict) else {}
            independence = evaluate_independence_readiness(member=target_member, task_center=task_center)
            existing_training_plan = target_member.get("training_plan") if isinstance(target_member.get("training_plan"), dict) else {}
            next_stage = existing_training_plan.get("stage") or "first_reflection_done"
            if independence.get("ready_for_independence"):
                next_stage = "independent_candidate"
            target_member["training_plan"] = {
                **existing_training_plan,
                "stage": next_stage,
                "independence_readiness": independence,
            }
            maybe_notify_independence_readiness(runtime=runtime, member=target_member)
            from admin.trainer_coaching_runtime import record_task_approved_coaching

            record_task_approved_coaching(
                runtime,
                coached_member=target_member,
                task=task,
                independence=independence,
            )
            from admin.work_nodes_runtime import archive_work_node_to_storage, attach_archive_to_task

            archive_result = await archive_work_node_to_storage(
                workspace=workspace,
                tenant_id=normalized_tenant_id,
                runtime=runtime,
                task_id=task_id,
                get_user_gitee_token=get_user_gitee_token,
                tenant_manager=tenant_manager,
                config=config,
                get_git_provider_instance=get_git_provider_instance,
                get_tenant_git_repo=get_tenant_git_repo,
                request=request,
            )
            if attach_archive_to_task(runtime, task_id, archive_result):
                task["work_node_archive"] = archive_result
                runtime["task_center"] = task_center
                save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
            evolution_summary = {
                "next_recommendation_id": next_recommendation.get("recommendation_id"),
                "next_task_title": next_recommendation.get("title"),
                "next_task_objective": next_recommendation.get("objective"),
                "memory_decision_status": decision_state.get("status"),
                "memory_primary_plan": decision_state.get("primary_plan"),
                "memory_verification_goal": decision_state.get("verification_goal"),
                "independence_ready": independence.get("ready_for_independence"),
                "independence_met_count": independence.get("met_criteria_count"),
                "work_node_archive": archive_result if isinstance(archive_result, dict) else None,
            }
            runtime["task_center"] = task_center
            runtime["relationship_center"] = relationship_center
            runtime["child_members"] = members
            save_autonomy_runtime(workspace, runtime, normalized_tenant_id)

            if member_uses_operation_automation(workspace, target_member):
                operating_contract = target_member.get("operating_contract", {}) if isinstance(target_member.get("operating_contract"), dict) else {}
                autonomy_mode = str(operating_contract.get("autonomy_mode") or "").strip() or "observe_plan_act_reflect"
                should_auto_progress = (
                    autonomy_mode == "observe_plan_act_reflect"
                    and str(export_runtime.get("status") or "").strip() == "exported"
                    and not has_open_formal_task(task_center, member_id, exclude_task_id=task_id)
                )
                if should_auto_progress:
                    auto_assigned_task = upsert_task(task_center, {
                        "task_id": f"task:{member_id}:{int(datetime.now().timestamp() * 1000)}:autonext",
                        "member_id": member_id,
                        "assigned_by_member_id": "talent_development_officer",
                        "title": next_recommendation.get("title"),
                        "objective": next_recommendation.get("objective"),
                        "deliverables": next_recommendation.get("deliverables", []),
                        "status": "assigned",
                        "assigned_at": datetime.now().isoformat(),
                        "started_at": None,
                        "submitted_at": None,
                        "approved_at": None,
                        "result_summary": None,
                        "reflection": None,
                        "review_note": None,
                        "metadata": {
                            "source": "auto_progression_after_export",
                            "recommendation_id": next_recommendation.get("recommendation_id"),
                            "auto_assigned": True,
                            "previous_task_id": task_id,
                        },
                    })
                    next_recommendation["status"] = "adopted"
                    next_recommendation["adopted_at"] = datetime.now().isoformat()
                    append_relationship_message(
                        relationship_center,
                        thread_id=f"trainer:{member_id}",
                        participants=["talent_development_officer", member_id],
                        sender_member_id="talent_development_officer",
                        sender_role="talent_development",
                        message_type="task_assignment",
                        content=f"系统已按成长闭环自动进入下一轮正式任务：{str(auto_assigned_task.get('title') or '').strip() or '下一轮任务'}。",
                        metadata={
                            "member_id": member_id,
                            "task_id": auto_assigned_task.get("task_id"),
                            "recommendation_id": next_recommendation.get("recommendation_id"),
                            "auto_progressed": True,
                            "previous_task_id": task_id,
                        },
                    )
                    target_member["training_plan"] = {
                        **(target_member.get("training_plan") if isinstance(target_member.get("training_plan"), dict) else {}),
                        "stage": "active_training",
                        "next_action": str(next_recommendation.get("objective") or "继续推进下一轮正式任务").strip() or "继续推进下一轮正式任务",
                    }
                    target_member["growth_state"] = {
                        **(target_member.get("growth_state") if isinstance(target_member.get("growth_state"), dict) else {}),
                        "current_focus": str(next_recommendation.get("title") or "下一轮正式任务").strip() or "下一轮正式任务",
                        "next_goal": "继续验证并稳定岗位方法",
                    }
                    member_jobs = target_member.get("current_jobs") if isinstance(target_member.get("current_jobs"), list) else []
                    if member_jobs and isinstance(member_jobs[0], dict):
                        member_jobs[0] = {
                            **member_jobs[0],
                            "status": "ready_for_next_case",
                            "target_outcome": str(next_recommendation.get("objective") or member_jobs[0].get("target_outcome") or "").strip() or member_jobs[0].get("target_outcome"),
                        }
                        target_member["current_jobs"] = member_jobs
                    self_media_runtime = runtime.get("self_media", {}) if isinstance(runtime.get("self_media"), dict) else {}
                    tenant_states = self_media_runtime.get("tenants", {}) if isinstance(self_media_runtime.get("tenants"), dict) else {}
                    member_state = tenant_states.get(member_id, {}) if isinstance(tenant_states.get(member_id), dict) else {}
                    member_state["stage"] = "ready_for_next_case"
                    member_state["blocked_reason"] = None
                    member_state["next_action"] = str(next_recommendation.get("objective") or "继续推进下一轮正式任务").strip() or "继续推进下一轮正式任务"
                    member_state["last_task_id"] = str(auto_assigned_task.get("task_id") or "").strip() or member_state.get("last_task_id")
                    member_state["last_task_status"] = "assigned"
                    tenant_states[member_id] = member_state
                    self_media_runtime["tenants"] = tenant_states
                    runtime["self_media"] = self_media_runtime
                    runtime["child_members"] = members
                    runtime["task_center"] = task_center
                    runtime["relationship_center"] = relationship_center
                    save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
                    evolution_summary["auto_progressed"] = True
                    evolution_summary["auto_assigned_task_id"] = auto_assigned_task.get("task_id")
        enriched, review_summary = persist_autonomy_training_updates(
            load_autonomy_runtime(workspace, normalized_tenant_id),
            trigger="task_approved_evolution",
            force_persist=True,
        )
        response_message = "育成官已确认本轮任务完成"
        if evolution_summary.get("next_task_title"):
            response_message = f"{response_message}；系统已生成下一轮建议「{evolution_summary.get('next_task_title')}」"
        if evolution_summary.get("memory_primary_plan"):
            response_message = f"{response_message}。思考结论：{str(evolution_summary.get('memory_primary_plan') or '')[:120]}"
        return success_response(
            {"autonomy": enriched, "task": task, "evolution_summary": evolution_summary, "review_summary": review_summary},
            response_message,
        )

    @app.put("/api/autonomy/identity")
    async def update_autonomy_identity(request: Request):
        data = await request.json()
        patch = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(patch.get("tenant_id"))
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        runtime["parent_profile"] = normalize_parent_profile_runtime({
            **(runtime.get("parent_profile") if isinstance(runtime.get("parent_profile"), dict) else {}),
            **(patch.get("parent_profile") if isinstance(patch.get("parent_profile"), dict) else {}),
        })
        current_members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        selected_member_id = str(
            patch.get("primary_child_member_id")
            or patch.get("selected_member_id")
            or runtime.get("primary_child_member_id")
            or current_members.get("selected_member_id")
            or ""
        ).strip() or current_members.get("selected_member_id")
        patch_members = patch.get("child_members")
        if patch_members is not None:
            next_members = normalize_child_members_runtime(
                patch_members,
                legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
            )
        else:
            next_items: list[dict] = []
            for item in current_members.get("items", []):
                if not isinstance(item, dict):
                    continue
                merged_item = dict(item)
                if str(item.get("member_id") or "") == str(selected_member_id or "") and isinstance(patch.get("child_agent"), dict):
                    merged_item = {
                        **merged_item,
                        **patch.get("child_agent"),
                        "identity": {
                            **(merged_item.get("identity") if isinstance(merged_item.get("identity"), dict) else {}),
                            **(patch.get("child_agent", {}).get("identity") if isinstance(patch.get("child_agent", {}).get("identity"), dict) else {}),
                        },
                        "role_memory": {
                            **(merged_item.get("role_memory") if isinstance(merged_item.get("role_memory"), dict) else {}),
                            **(patch.get("child_agent", {}).get("role_memory") if isinstance(patch.get("child_agent", {}).get("role_memory"), dict) else {}),
                        },
                        "growth_state": {
                            **(merged_item.get("growth_state") if isinstance(merged_item.get("growth_state"), dict) else {}),
                            **(patch.get("child_agent", {}).get("growth_state") if isinstance(patch.get("child_agent", {}).get("growth_state"), dict) else {}),
                        },
                        "persona": {
                            **(merged_item.get("persona") if isinstance(merged_item.get("persona"), dict) else {}),
                            **{
                                "self_description": patch.get("child_agent", {}).get("identity", {}).get("self_description"),
                                "tone": patch.get("child_agent", {}).get("identity", {}).get("tone"),
                            },
                        },
                    }
                next_items.append(merged_item)
            next_members = normalize_child_members_runtime({
                "selected_member_id": selected_member_id,
                "items": next_items,
            })

        runtime["child_members"] = next_members
        runtime["primary_child_member_id"] = next_members.get("selected_member_id")
        selected_member = next(
            (item for item in next_members.get("items", []) if item.get("member_id") == next_members.get("selected_member_id")),
            next_members.get("items", [None])[0] if next_members.get("items") else None,
        )
        runtime["child_agent"] = normalize_child_agent_runtime(selected_member if isinstance(selected_member, dict) else {})
        runtime["tenant_id"] = normalized_tenant_id
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        return success_response(enrich_autonomy_runtime(runtime), "父节点与子女成员身份已更新")

    async def _create_autonomy_member(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        child_members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        name = str(payload.get("name") or "").strip() or "新员工"
        role_label = str(payload.get("role_label") or payload.get("job_title") or "").strip() or "岗位员工"
        role_key = str(payload.get("role_key") or payload.get("primary_role") or role_label).strip() or role_label
        trainer_member_id = str(payload.get("trainer_member_id") or "talent_development_officer").strip() or "talent_development_officer"
        work_type_id = str(payload.get("work_type_id") or "").strip() or None
        work_type_title = None
        work_type_default_goal = None
        if work_type_id:
            from work_types import load_work_types

            work_types_payload = load_work_types(workspace)
            items = work_types_payload.get("items", []) if isinstance(work_types_payload, dict) else []
            matched = next(
                (
                    item for item in items
                    if isinstance(item, dict)
                    and str(item.get("work_type_id") or "").strip() == work_type_id
                ),
                None,
            )
            if not matched:
                return error_response(f"工种 {work_type_id} 不存在，请先在公司空间添加工种", 400)
            work_type_title = str(matched.get("title") or work_type_id).strip()
            goal_schema = matched.get("goal_schema") if isinstance(matched.get("goal_schema"), dict) else {}
            work_type_default_goal = str(goal_schema.get("default_goal") or "").strip() or None
            role_label = work_type_title or role_label
            role_key = work_type_id
            from admin.member_clone_runtime import resolve_department_from_work_type

            department_id, department_label = resolve_department_from_work_type(matched)
        else:
            department_id = None
            department_label = None
        if not work_type_id:
            return error_response("创建员工必须指定已登记的工种。请先在育成师建档或公司设置添加工种。", 400)
        employee = create_employee_member_runtime(
            tenant_id=normalized_tenant_id,
            name=name,
            role_label=role_label,
            role_key=role_key,
            self_description=str(payload.get("self_description") or "").strip(),
            long_term_goal=str(payload.get("long_term_goal") or "").strip(),
            created_by_member_id=str(payload.get("created_by_member_id") or trainer_member_id).strip() or trainer_member_id,
            training_owner_member_id=trainer_member_id,
            work_type_id=work_type_id,
            work_type_title=work_type_title,
            work_type_default_goal=work_type_default_goal,
            account_id=str(payload.get("account_id") or "").strip() or None,
            department_id=department_id,
            department_label=department_label,
            content_direction=str(payload.get("content_direction") or "").strip() or None,
        )
        existing_ids = {
            str(item.get("member_id") or "").strip()
            for item in child_members.get("items", [])
            if isinstance(item, dict)
        }
        if str(employee.get("member_id") or "").strip() in existing_ids:
            return error_response("同名员工实例已存在，请修改名称或角色标识", 400)

        instance_runtime = employee.get("instance_runtime", {}) if isinstance(employee.get("instance_runtime"), dict) else {}
        for key in ("workspace_root", "memory_root", "artifacts_root", "learning_materials_root"):
            relative_path = str(instance_runtime.get(key) or "").strip()
            if not relative_path:
                continue
            (workspace / relative_path).mkdir(parents=True, exist_ok=True)

        child_members["items"] = [*child_members.get("items", []), employee]
        child_members["selected_member_id"] = str(employee.get("member_id") or "").strip() or child_members.get("selected_member_id")
        runtime["tenant_id"] = normalized_tenant_id
        runtime["child_members"] = child_members
        runtime["primary_child_member_id"] = child_members.get("selected_member_id")
        runtime["child_agent"] = normalize_child_agent_runtime(employee)
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, normalized_tenant_id))
        return success_response({
            "employee": employee,
            "member": employee,
            "autonomy": enriched,
        }, "员工实例已创建，后续由育成师继续建立画像与边界")

    @app.post("/api/autonomy/members")
    async def create_autonomy_member(request: Request):
        return await _create_autonomy_member(request)

    @app.post("/api/autonomy/employees")
    async def create_autonomy_employee(request: Request):
        return await _create_autonomy_member(request)

    @app.post("/api/autonomy/members/clone")
    async def clone_autonomy_member(request: Request):
        from admin.member_clone_runtime import clone_account_variant_member

        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        child_members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        source_member_id = str(payload.get("source_member_id") or "").strip()
        clone_mode = str(payload.get("clone_mode") or "account_variant").strip() or "account_variant"
        if clone_mode != "account_variant":
            return error_response("当前仅支持 clone_mode=account_variant（同岗位换账号）", 400)
        trainer_member_id = str(payload.get("trainer_member_id") or "talent_development_officer").strip() or "talent_development_officer"
        prefill_first_task = payload.get("prefill_first_task", True) is not False
        try:
            employee, clone_meta = clone_account_variant_member(
                workspace=workspace,
                runtime=runtime,
                source_member_id=source_member_id,
                name=str(payload.get("name") or "").strip(),
                account_id=str(payload.get("account_id") or "").strip(),
                content_direction=str(payload.get("content_direction") or "").strip(),
                tenant_id=normalized_tenant_id,
                trainer_member_id=trainer_member_id,
                prefill_first_task=prefill_first_task,
            )
        except ValueError as exc:
            return error_response(str(exc), 400)

        existing_ids = {
            str(item.get("member_id") or "").strip()
            for item in child_members.get("items", [])
            if isinstance(item, dict)
        }
        if str(employee.get("member_id") or "").strip() in existing_ids:
            return error_response("同名员工实例已存在，请修改名称", 400)

        instance_runtime = employee.get("instance_runtime", {}) if isinstance(employee.get("instance_runtime"), dict) else {}
        for key in ("workspace_root", "memory_root", "artifacts_root", "learning_materials_root"):
            relative_path = str(instance_runtime.get(key) or "").strip()
            if not relative_path:
                continue
            (workspace / relative_path).mkdir(parents=True, exist_ok=True)

        child_members["items"] = [*child_members.get("items", []), employee]
        child_members["selected_member_id"] = str(employee.get("member_id") or "").strip() or child_members.get("selected_member_id")
        runtime["tenant_id"] = normalized_tenant_id
        runtime["child_members"] = child_members
        runtime["primary_child_member_id"] = child_members.get("selected_member_id")
        runtime["child_agent"] = normalize_child_agent_runtime(employee)
        source_member = next(
            (
                item for item in child_members.get("items", [])
                if isinstance(item, dict) and str(item.get("member_id") or "").strip() == source_member_id
            ),
            None,
        )
        if isinstance(source_member, dict):
            from admin.trainer_coaching_runtime import record_account_variant_clone_coaching

            record_account_variant_clone_coaching(
                runtime,
                source_member=source_member,
                cloned_member=employee,
                content_direction=str(payload.get("content_direction") or "").strip(),
            )
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        enriched = enrich_autonomy_runtime(load_autonomy_runtime(workspace, normalized_tenant_id))
        return success_response({
            "employee": employee,
            "member": employee,
            "clone": clone_meta,
            "autonomy": enriched,
        }, "同岗位复制建档成功，新员工已就绪")

    @app.get("/api/workers/registry")
    async def get_worker_registry():
        return success_response({
            "mode": "compatibility_fallback",
            "message": "worker registry 仅作为历史兼容执行层保留，正式主线应优先通过员工实例 -> 决策中枢 -> 能力包。",
            "manifests": builtin_worker_manifests(workspace),
            "config": load_worker_registry_config(workspace),
            "runtime": worker_runtime,
            "self_media": {
                "executor_registry": describe_toutiao_executor_registry(workspace),
            },
        })

    @app.put("/api/workers/registry")
    async def update_worker_registry(request: Request):
        data = await request.json()
        saved = save_worker_registry_config(workspace, data if isinstance(data, dict) else {})
        return success_response(saved, "工种注册配置已更新，重启后将按新配置注册")

    @app.put("/api/autonomy/feedback-monitor")
    async def update_autonomy_feedback_monitor(request: Request):
        data = await request.json()
        patch = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(patch.get("tenant_id"))
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        current = normalize_feedback_monitor_runtime(runtime.get("feedback_monitor"))
        merged = {
            **current,
            **{
                key: value
                for key, value in patch.items()
                if key in {"enabled", "interval_seconds", "max_comments", "auto_reply_feedback", "reply_limit", "auto_draft_from_followup", "tenants"}
            },
        }
        runtime["feedback_monitor"] = normalize_feedback_monitor_runtime(merged)
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        return success_response(runtime["feedback_monitor"], "反馈轮询配置已更新")

    @app.put("/api/self-media/executor")
    async def update_self_media_executor(request: Request):
        data = await request.json()
        payload = data if isinstance(data, dict) else {}
        normalized_tenant_id = resolve_tenant_id(payload.get("tenant_id"))
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        current = runtime.get("self_media", {}) if isinstance(runtime.get("self_media"), dict) else {}
        current_executor = current.get("executor", {}) if isinstance(current.get("executor"), dict) else {}
        next_preferred_mode = str(
            payload.get("preferred_mode")
            or payload.get("executor_mode")
            or current_executor.get("preferred_mode")
            or "evo"
        ).strip().lower() or "evo"
        if next_preferred_mode not in {"auto", "evo"}:
            return error_response("preferred_mode 非法", 400)
        runtime["self_media"] = {
            "executor": {
                "preferred_mode": next_preferred_mode,
                "executor_dir": None,
                "executor_name": str(payload.get("executor_name") or current_executor.get("executor_name") or "toutiao_executor").strip() or "toutiao_executor",
                "executor_adapter": "evo_local",
                "login_target_url": str(payload.get("login_target_url") or current_executor.get("login_target_url") or "").strip() or None,
            },
            "tenants": current.get("tenants", {}) if isinstance(current.get("tenants"), dict) else {},
        }
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        return success_response({
            "self_media": runtime["self_media"],
            "executor_registry": describe_toutiao_executor_registry(workspace),
        }, "自媒体执行器默认路由已更新")

    @app.get("/api/autonomy/learning-tasks")
    async def get_autonomy_learning_tasks(tenant_id: str | None = None, status: str | None = None):
        learning_state = refresh_runtime_learning_tasks(
            workspace=workspace,
            tenant_manager=tenant_manager,
            task_queue=task_queue,
            tenant_id=tenant_id,
        )
        tasks = learning_state.get("tasks", {}) if isinstance(learning_state, dict) else {}
        items: list[dict] = []
        for task_id, payload in tasks.items():
            if not isinstance(payload, dict):
                continue
            if tenant_id and payload.get("tenant_id") != tenant_id:
                continue
            if status and payload.get("status") != status:
                continue
            items.append({
                "task_id": task_id,
                **payload,
            })
        tenant_scope = [tenant_id] if tenant_id else (tenant_manager.list_tenants() or ["default"])
        for scoped_tenant_id in tenant_scope:
            for payload in build_historical_learning_tasks(workspace, scoped_tenant_id, task_queue):
                if status and payload.get("status") != status:
                    continue
                if any(existing.get("task_id") == payload.get("task_id") for existing in items):
                    continue
                items.append(payload)
        items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        runtime = load_autonomy_runtime(workspace, resolve_tenant_id(tenant_id))
        runtime = sync_member_knowledge_learning_writeback(
            workspace=workspace,
            runtime=runtime,
            tenant_id=resolve_tenant_id(tenant_id),
            normalize_child_members_runtime=normalize_child_members_runtime,
        )
        save_autonomy_runtime(workspace, runtime, resolve_tenant_id(tenant_id))
        return success_response({
            "updated_at": learning_state.get("updated_at"),
            "items": items,
        })

    @app.post("/api/autonomy/learning-tasks/{task_id}/validate")
    async def validate_autonomy_learning_task(task_id: str, request: Request):
        data = await request.json()
        tenant_id = data.get("tenant_id", "default")
        normalized_tenant_id = resolve_tenant_id(tenant_id)
        try:
            knowledge_result = trigger_member_knowledge_learning_validation(
                workspace=workspace,
                tenant_id=normalized_tenant_id,
                task_id=task_id,
                refresh_runtime_learning_tasks=refresh_runtime_learning_tasks,
                tenant_manager=tenant_manager,
                task_queue=task_queue,
            )
            if knowledge_result is not None:
                result = knowledge_result
            else:
                result = trigger_learning_task_validation(
                    workspace=workspace,
                    tenant_id=normalized_tenant_id,
                    task_id=task_id,
                    task_queue=task_queue,
                )
        except ValueError as exc:
            return error_response(str(exc), 400)
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        runtime = sync_member_knowledge_learning_writeback(
            workspace=workspace,
            runtime=runtime,
            tenant_id=normalized_tenant_id,
            normalize_child_members_runtime=normalize_child_members_runtime,
        )
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
        return success_response(result, result.get("message", "学习任务验证已启动"))

    @app.get("/api/autonomy/brain-overview")
    async def get_autonomy_brain_overview(tenant_id: str = "default"):
        autonomy = enrich_autonomy_runtime(load_autonomy_runtime(workspace, resolve_tenant_id(tenant_id)))
        registry_config = load_worker_registry_config(workspace)
        manifests = builtin_worker_manifests(workspace)
        evolution = build_evolution_overview(
            workspace=workspace,
            tenant_id=tenant_id,
            task_queue=task_queue,
            plugin_summary=plugin_summary,
            tenant_manager=tenant_manager,
        )

        mission_state = load_mission_runs(workspace)
        mission_items = mission_state.get("items", []) if isinstance(mission_state, dict) else []
        tenant_mission_runs = [
            item for item in mission_items
            if isinstance(item, dict) and item.get("tenant_id") == tenant_id
        ]
        tenant_mission_runs.sort(key=lambda item: item.get("created_at") or "", reverse=True)

        learning_state = refresh_runtime_learning_tasks(
            workspace=workspace,
            tenant_manager=tenant_manager,
            task_queue=task_queue,
            tenant_id=tenant_id,
        )
        runtime_tasks = learning_state.get("tasks", {}) if isinstance(learning_state, dict) else {}
        learning_items: list[dict] = []
        for task_id, payload in runtime_tasks.items():
            if not isinstance(payload, dict):
                continue
            if payload.get("tenant_id") != tenant_id:
                continue
            learning_items.append({"task_id": task_id, **payload})
        for payload in build_historical_learning_tasks(workspace, tenant_id, task_queue):
            if any(existing.get("task_id") == payload.get("task_id") for existing in learning_items):
                continue
            learning_items.append(payload)
        learning_items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)

        review_queue = load_review_queue(workspace, tenant_id)
        promotions = list_platform_strategy_promotions(workspace, 12)
        tenant_promotions = [
            item for item in promotions
            if isinstance(item, dict) and item.get("tenant_id") == tenant_id
        ]

        workers = worker_runtime.get("workers", {}) if isinstance(worker_runtime, dict) else {}
        available_workers = []
        for worker_id, manifest in manifests.items():
            runtime_item = workers.get(worker_id, {}) if isinstance(workers, dict) else {}
            config_item = (
                registry_config.get("workers", {}).get(worker_id, {})
                if isinstance(registry_config.get("workers"), dict)
                else {}
            )
            available_workers.append({
                "worker_id": worker_id,
                "title": manifest.get("title") or worker_id,
                "enabled": bool(runtime_item.get("enabled", config_item.get("enabled", manifest.get("default_enabled", True)))),
                "handler_count": int(runtime_item.get("handler_count", 0) or 0),
                "capability_type": manifest.get("capability_type"),
                "runtime_role": "compatibility_fallback",
            })

        recent_runs = []
        for item in tenant_mission_runs[:5]:
            recent_runs.append({
                "mission_run_id": item.get("mission_run_id"),
                "title": item.get("title"),
                "goal": item.get("goal"),
                "status": item.get("status"),
                "mission_kind": item.get("mission_kind"),
                "updated_at": item.get("updated_at") or item.get("created_at"),
                "autonomy_session_id": item.get("autonomy_session_id"),
            })

        recent_learning_tasks = []
        for item in learning_items[:5]:
            recent_learning_tasks.append({
                "task_id": item.get("task_id"),
                "title": item.get("title"),
                "status": item.get("status"),
                "issue_category": item.get("issue_category"),
                "updated_at": item.get("updated_at") or item.get("created_at"),
            })

        recent_reviews = []
        for item in review_queue[:5]:
            if not isinstance(item, dict):
                continue
            recent_reviews.append({
                "id": item.get("id"),
                "strategy_id": item.get("strategy_id"),
                "status": item.get("status"),
                "reason": item.get("reason"),
                "alert_reason": item.get("alert_reason"),
                "updated_at": item.get("last_run_at") or item.get("created_at"),
            })

        summary = {
            "workers_total": len(available_workers),
            "workers_enabled": len([item for item in available_workers if item.get("enabled")]),
            "mission_runs_total": len(tenant_mission_runs),
            "mission_running": len([item for item in tenant_mission_runs if item.get("status") in {"running", "queued"}]),
            "learning_tasks_total": len(learning_items),
            "learning_pending": len([item for item in learning_items if item.get("status") not in {"resolved", "validated_improved", "validated_unchanged"}]),
            "review_queue_total": len([item for item in review_queue if isinstance(item, dict)]),
            "platform_promotions_total": len(tenant_promotions),
            "autonomy_enabled": bool(autonomy.get("enabled")),
            "autonomy_status": autonomy.get("status"),
        }

        return success_response({
            "tenant_id": tenant_id,
            "summary": summary,
            "autonomy": autonomy,
            "workers": available_workers,
            "recent_mission_runs": recent_runs,
            "recent_learning_tasks": recent_learning_tasks,
            "recent_reviews": recent_reviews,
            "platform_promotions": tenant_promotions[:5],
            "evolution_summary": (
                evolution.get("summary", {})
                if isinstance(evolution, dict)
                else {}
            ),
        })

    register_collaboration_routes(
        app,
        workspace=workspace,
        load_autonomy_runtime=load_autonomy_runtime,
        save_autonomy_runtime=save_autonomy_runtime,
        resolve_tenant_id=resolve_tenant_id,
        enrich_autonomy_runtime=enrich_autonomy_runtime,
        append_relationship_message=append_relationship_message,
        success_response=success_response,
        error_response=error_response,
    )

    from core.task_queue import TaskPriority

    register_intake_routes(
        app,
        workspace=workspace,
        load_autonomy_runtime=load_autonomy_runtime,
        save_autonomy_runtime=save_autonomy_runtime,
        resolve_tenant_id=resolve_tenant_id,
        enrich_autonomy_runtime=enrich_autonomy_runtime,
        append_relationship_message=append_relationship_message,
        success_response=success_response,
        error_response=error_response,
        task_queue=task_queue,
        task_priority_normal=TaskPriority.NORMAL,
    )

    register_work_nodes_routes(
        app,
        workspace=workspace,
        load_autonomy_runtime=load_autonomy_runtime,
        save_autonomy_runtime=save_autonomy_runtime,
        resolve_tenant_id=resolve_tenant_id,
        enrich_autonomy_runtime=enrich_autonomy_runtime,
        success_response=success_response,
        error_response=error_response,
        get_user_gitee_token=get_user_gitee_token,
        tenant_manager=tenant_manager,
        config=config,
        get_git_provider_instance=get_git_provider_instance,
        get_tenant_git_repo=get_tenant_git_repo,
    )
