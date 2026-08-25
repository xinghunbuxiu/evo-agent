"""
正式任务确认后的进化闭环：下一轮建议、独立运营判定等。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from admin.memory_hub_runtime import create_memory_hub_runtime_bindings
from admin.task_center_runtime import has_open_formal_task, has_suggested_recommendation, upsert_task_recommendation
from admin.worker_route_runtime import member_uses_operation_automation

KNOWLEDGE_COMPLETE_STATUSES = {
    "candidate_found",
    "validated_improved",
    "validated_unchanged",
    "resolved",
}


def _trim(text: object | None, limit: int = 180) -> str:
    raw = str(text or "").strip()
    return raw[:limit]


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
    if not isinstance(thread, dict):
        thread = {"thread_id": thread_id, "participants": participants, "messages": []}
        threads.append(thread)
    messages = thread.get("messages") if isinstance(thread.get("messages"), list) else []
    messages.append({
        "message_id": f"msg:{int(datetime.now().timestamp() * 1000)}",
        "sender_member_id": sender_member_id,
        "sender_role": sender_role,
        "message_type": message_type,
        "content": content,
        "created_at": datetime.now().isoformat(),
        "metadata": metadata or {},
    })
    thread["messages"] = messages[-80:]
    relationship_center["last_delivery_at"] = datetime.now().isoformat()


def _append_parent_inbox_message(relationship_center: dict, payload: dict) -> None:
    inbox = relationship_center.get("parent_inbox")
    if not isinstance(inbox, list):
        inbox = []
    inbox.append(payload)
    relationship_center["parent_inbox"] = inbox[-40:]


def build_knowledge_followup_formal_task_recommendation(
    *,
    workspace: Path,
    member: dict,
    learning_task: dict,
    learning_task_id: str,
) -> dict:
    member_id = str(member.get("member_id") or "").strip() or "member"
    member_name = str(member.get("name") or member_id).strip() or member_id
    role = str(member.get("primary_role") or "").strip() or "autonomous_child_agent"
    status = str(learning_task.get("status") or "").strip()
    approaches = learning_task.get("candidate_approaches") if isinstance(learning_task.get("candidate_approaches"), list) else []
    summary = _trim(learning_task.get("goal") or learning_task.get("title"), 160)
    if approaches and isinstance(approaches[0], dict):
        summary = _trim(approaches[0].get("summary") or approaches[0].get("title"), 160) or summary
    next_steps = []
    if approaches and isinstance(approaches[0], dict):
        next_steps = [
            str(item).strip()
            for item in (approaches[0].get("next_steps") if isinstance(approaches[0].get("next_steps"), list) else [])
            if str(item).strip()
        ]
    title = f"{member_name} 补知识后验证任务"
    objective = f"带着补知识结论回到岗位，执行一轮最小可验证正式任务。{_trim(summary, 120)}".strip()
    deliverables = next_steps[:4] or [
        "明确这次要验证的补知识结论",
        "执行一轮真实岗位动作",
        "提交结果，并说明与补知识前相比改变了什么",
        "继续沉淀可复用经验",
    ]
    reason = f"补知识任务已完成整理（{status}），系统建议立即回到正式任务验证：{summary}".strip()
    memory_hub = member.get("memory_hub") if isinstance(member.get("memory_hub"), dict) else {}
    decision_state = memory_hub.get("decision_state") if isinstance(memory_hub.get("decision_state"), dict) else {}
    primary_plan = str(decision_state.get("primary_plan") or "").strip()
    if primary_plan:
        reason = f"{reason} 系统思考：{primary_plan}".strip()
    now_iso = datetime.now().isoformat()
    return {
        "recommendation_id": f"recommendation:{member_id}:{int(datetime.now().timestamp() * 1000)}:knowledge",
        "member_id": member_id,
        "source_task_id": None,
        "title": title,
        "objective": objective,
        "deliverables": deliverables,
        "reason": reason,
        "status": "suggested",
        "created_at": now_iso,
        "adopted_at": None,
        "metadata": {
            "role_scope": role,
            "source": "knowledge_learning_followup",
            "learning_task_id": learning_task_id,
            "learning_status": status,
            "operation_automation": member_uses_operation_automation(workspace, member),
        },
    }


def maybe_recommend_formal_task_after_knowledge(
    *,
    workspace: Path,
    runtime: dict,
    member: dict,
    learning_task: dict,
    learning_task_id: str,
    previous_status: str,
) -> dict | None:
    if not isinstance(member, dict):
        return None
    member_id = str(member.get("member_id") or "").strip()
    if not member_id:
        return None
    status = str(learning_task.get("status") or "").strip()
    prev = str(previous_status or "").strip()
    if status not in KNOWLEDGE_COMPLETE_STATUSES:
        return None
    if prev in KNOWLEDGE_COMPLETE_STATUSES:
        return None

    training_plan = member.get("training_plan") if isinstance(member.get("training_plan"), dict) else {}
    if str(training_plan.get("knowledge_followup_recommendation_id") or "").strip():
        return None

    task_center = runtime.get("task_center", {}) if isinstance(runtime.get("task_center"), dict) else {}
    if has_open_formal_task(task_center, member_id):
        return None
    if has_suggested_recommendation(
        task_center,
        member_id,
        sources={"knowledge_learning_followup", "trainer_auto_followup"},
    ):
        return None

    recommendation = build_knowledge_followup_formal_task_recommendation(
        workspace=workspace,
        member=member,
        learning_task=learning_task,
        learning_task_id=learning_task_id,
    )
    upsert_task_recommendation(task_center, recommendation)
    runtime["task_center"] = task_center

    member_name = str(member.get("name") or member_id).strip() or member_id
    relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}
    _append_relationship_message(
        relationship_center,
        thread_id=f"trainer:{member_id}",
        participants=["talent_development_officer", member_id],
        sender_member_id="talent_development_officer",
        sender_role="talent_development",
        message_type="trainer_growth_comment",
        content=(
            f"补知识已完成，系统已为 {member_name} 生成下一轮正式任务建议："
            f"{recommendation.get('title')}。请考虑在派任务页采纳并下发。"
        ),
        metadata={
            "member_id": member_id,
            "recommendation_id": recommendation.get("recommendation_id"),
            "learning_task_id": learning_task_id,
            "auto_knowledge_followup": True,
        },
    )
    runtime["relationship_center"] = relationship_center

    member["training_plan"] = {
        **training_plan,
        "knowledge_followup_recommendation_id": recommendation.get("recommendation_id"),
        "next_action": "补知识已完成，请采纳系统生成的下一轮正式任务建议",
    }
    return recommendation


def maybe_notify_independence_readiness(*, runtime: dict, member: dict) -> dict | None:
    if not isinstance(member, dict):
        return None
    member_id = str(member.get("member_id") or "").strip()
    if not member_id or str(member.get("primary_role") or "").strip() == "talent_development":
        return None

    training_plan = member.get("training_plan") if isinstance(member.get("training_plan"), dict) else {}
    independence = training_plan.get("independence_readiness") if isinstance(training_plan.get("independence_readiness"), dict) else {}
    if not independence.get("ready_for_independence"):
        return None
    if str(training_plan.get("independence_notified_at") or "").strip():
        return None

    member_name = str(member.get("name") or member_id).strip() or member_id
    met_count = int(independence.get("met_criteria_count") or 0)
    total = int(independence.get("total_criteria") or 0)
    now_iso = datetime.now().isoformat()
    trainer_content = (
        f"系统判定 {member_name} 已接近可独立运营（{met_count}/{total} 项达标）。"
        "建议育成官开始放手：减少逐步带教，扩大授权边界，让成员承担更多真实决策与复盘责任。"
    )
    parent_content = (
        f"【系统提示】{member_name} 已达到可独立运营候选标准。"
        "你可以考虑让育成官收缩介入频率，把更多真实经营动作交给该岗位成员。"
    )

    relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}
    _append_relationship_message(
        relationship_center,
        thread_id=f"trainer:{member_id}",
        participants=["talent_development_officer", member_id],
        sender_member_id="talent_development_officer",
        sender_role="talent_development",
        message_type="independence_handoff",
        content=trainer_content,
        metadata={
            "member_id": member_id,
            "independence_ready": True,
            "met_criteria_count": met_count,
            "total_criteria": total,
        },
    )
    _append_parent_inbox_message(relationship_center, {
        "message_id": f"independence:{member_id}:{int(datetime.now().timestamp() * 1000)}",
        "sender_member_id": "system",
        "sender_role": "system",
        "message_type": "independence_handoff",
        "title": f"{member_name} 可独立运营候选",
        "content": parent_content,
        "created_at": now_iso,
        "metadata": {
            "member_id": member_id,
            "independence_ready": True,
            "met_criteria_count": met_count,
            "total_criteria": total,
        },
    })
    runtime["relationship_center"] = relationship_center

    member["training_plan"] = {
        **training_plan,
        "stage": "independent_candidate",
        "independence_notified_at": now_iso,
        "next_action": "已达标可独立运营候选，育成官可考虑放手并收缩带教频率",
        "independence_handoff": {
            "notified_at": now_iso,
            "met_criteria_count": met_count,
            "total_criteria": total,
        },
    }
    from admin.trainer_coaching_runtime import record_independence_handoff_coaching

    record_independence_handoff_coaching(
        runtime,
        coached_member=member,
        independence=independence,
    )
    return {
        "member_id": member_id,
        "independence_notified_at": now_iso,
        "met_criteria_count": met_count,
        "total_criteria": total,
    }


def build_next_formal_task_recommendation(
    *,
    workspace: Path,
    member: dict,
    task: dict,
    export_runtime: dict | None = None,
) -> dict:
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
    knowledge_status = str(training_plan.get("knowledge_learning_status") or "").strip()
    knowledge_validated = knowledge_status in {
        "candidate_found",
        "ready_for_validation",
        "validated_improved",
        "validated_unchanged",
        "resolved",
    }
    learning_cards = [
        item for item in cards
        if isinstance(item, dict)
        and (
            str(item.get("source") or "") == "knowledge_learning"
            or str(item.get("signature") or "").startswith("knowledge_learning:")
        )
    ]
    has_reflection = stage in {
        "first_reflection_done",
        "active_training",
        "independent_candidate",
        "commercial_delivery_done",
        "knowledge_supplementing",
    } or knowledge_validated or bool(learning_cards)
    # 1 formal approve + validated knowledge can substitute a second formal round
    multi_round = approved_count >= 2 or (approved_count >= 1 and knowledge_validated and bool(learning_cards))
    criteria = [
        {"id": "has_approved_task", "label": "至少完成一轮正式任务", "met": approved_count >= 1},
        {"id": "has_reflection", "label": "已完成首轮复盘或补知识沉淀", "met": has_reflection},
        {"id": "has_experience_card", "label": "已沉淀经验卡", "met": card_count >= 1},
        {
            "id": "multi_round_validation",
            "label": "多轮稳定性验证（正式任务或任务+补知识）",
            "met": multi_round,
        },
    ]
    met_count = sum(1 for item in criteria if item.get("met"))
    ready = all(bool(item.get("met")) for item in criteria)
    return {
        "ready_for_independence": ready,
        "met_criteria_count": met_count,
        "total_criteria": len(criteria),
        "approved_task_count": approved_count,
        "experience_card_count": card_count,
        "knowledge_validated": knowledge_validated,
        "criteria": criteria,
        "evaluated_at": datetime.now().isoformat(),
    }


def apply_approved_task_evolution(
    *,
    workspace: Path,
    runtime: dict,
    tenant_id: str,
    member_id: str,
    task: dict,
    tenant_manager=None,
    task_queue=None,
    include_training_review: bool = True,
) -> tuple[dict, dict]:
    from admin.runtime_state import normalize_child_members_runtime

    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
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
    task_center = runtime.get("task_center", {}) if isinstance(runtime.get("task_center"), dict) else {}
    relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}

    if tenant_manager is None:
        from core.tenant import TenantManager
        tenant_manager = TenantManager(workspace)
    if task_queue is None:
        from core.task_queue import get_task_queue
        task_queue = get_task_queue(workspace, max_workers=1)

    memory_hub_runtime = create_memory_hub_runtime_bindings(
        build_historical_learning_tasks=lambda *args, **kwargs: [],
        list_platform_strategy_promotions=lambda *args, **kwargs: [],
    )
    sync_runtime_memory_hub = memory_hub_runtime["sync_runtime_memory_hub"]

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

    evolution_summary: dict = {}
    if isinstance(target_member, dict):
        next_recommendation = build_next_formal_task_recommendation(
            workspace=workspace,
            member=target_member,
            task=task,
            export_runtime=None,
        )
        upsert_task_recommendation(task_center, next_recommendation)
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
        evolution_summary = {
            "next_recommendation_id": next_recommendation.get("recommendation_id"),
            "next_task_title": next_recommendation.get("title"),
            "next_task_objective": next_recommendation.get("objective"),
            "memory_decision_status": decision_state.get("status"),
            "memory_primary_plan": decision_state.get("primary_plan"),
            "memory_verification_goal": decision_state.get("verification_goal"),
            "independence_ready": independence.get("ready_for_independence"),
            "independence_met_count": independence.get("met_criteria_count"),
        }
        runtime["child_members"] = members

    runtime["task_center"] = task_center
    runtime["relationship_center"] = relationship_center

    if include_training_review:
        pass

    return runtime, evolution_summary
