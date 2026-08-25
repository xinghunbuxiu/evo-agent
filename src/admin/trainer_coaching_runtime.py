"""育成师带教履历：在关键事件时写入育成官 experience_journal。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from admin.runtime_state import normalize_child_members_runtime
from admin.worker_route_runtime import resolve_work_type_id

TRAINER_MEMBER_ID = "talent_development_officer"

COACHING_EVENT_LABELS: dict[str, str] = {
    "task_approved_round": "完成一轮任务带教确认",
    "account_variant_clone": "同岗位复制扩产",
    "independence_handoff": "可独立运营放手",
    "knowledge_followup_closed": "补知识闭环完成",
    "commercial_intake_settled": "商业接单结算带教",
}


def find_trainer_member(runtime: dict) -> dict | None:
    child_members = normalize_child_members_runtime(
        runtime.get("child_members"),
        legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
    )
    items = child_members.get("items") if isinstance(child_members.get("items"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        member_id = str(item.get("member_id") or "").strip()
        role = str(item.get("primary_role") or "").strip()
        if member_id == TRAINER_MEMBER_ID or role == "talent_development":
            return item
    return None


def _upsert_trainer_in_runtime(runtime: dict, trainer: dict) -> None:
    child_members = normalize_child_members_runtime(
        runtime.get("child_members"),
        legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
    )
    items = child_members.get("items") if isinstance(child_members.get("items"), list) else []
    trainer_id = str(trainer.get("member_id") or TRAINER_MEMBER_ID).strip()
    next_items: list[dict] = []
    replaced = False
    for item in items:
        if not isinstance(item, dict):
            next_items.append(item)
            continue
        if str(item.get("member_id") or "").strip() == trainer_id:
            next_items.append(trainer)
            replaced = True
        else:
            next_items.append(item)
    if not replaced:
        next_items.append(trainer)
    child_members["items"] = next_items
    runtime["child_members"] = child_members


def append_trainer_coaching_record(
    runtime: dict,
    *,
    event_type: str,
    coached_member: dict,
    outcome: str,
    method_summary: str,
    next_coaching_focus: str | None = None,
    dedup_key: str | None = None,
    metadata: dict | None = None,
) -> dict | None:
    """向育成师 experience_journal 追加一条带教记录（按 signature 去重）。"""
    if not isinstance(coached_member, dict):
        return None
    trainer = find_trainer_member(runtime)
    if not trainer:
        return None

    coached_member_id = str(coached_member.get("member_id") or "").strip()
    coached_name = str(coached_member.get("name") or coached_member_id).strip() or coached_member_id
    if not coached_member_id or coached_member_id == TRAINER_MEMBER_ID:
        return None

    work_type_id = resolve_work_type_id(coached_member) or str(coached_member.get("primary_role") or "").strip()
    event_label = COACHING_EVENT_LABELS.get(event_type, event_type)
    organization = coached_member.get("organization") if isinstance(coached_member.get("organization"), dict) else {}
    department_label = str(organization.get("department_label") or organization.get("department_id") or "").strip()
    content_direction = ""
    content_profile = coached_member.get("content_profile") if isinstance(coached_member.get("content_profile"), dict) else {}
    content_direction = str(content_profile.get("content_direction") or "").strip()

    signature = f"trainer_coaching|{event_type}|{coached_member_id}|{dedup_key or int(datetime.now().timestamp())}"
    journal = trainer.get("experience_journal") if isinstance(trainer.get("experience_journal"), dict) else {}
    cards = journal.get("cards") if isinstance(journal.get("cards"), list) else []
    if any(isinstance(item, dict) and str(item.get("signature") or "") == signature for item in cards):
        return None

    now_iso = datetime.now().isoformat()
    card_id = f"coaching:{event_type}:{coached_member_id}:{int(datetime.now().timestamp() * 1000)}"
    evidence = [
        f"coached_member_id:{coached_member_id}",
        f"coached_member_name:{coached_name}",
        f"work_type_id:{work_type_id}",
        f"outcome:{outcome}",
    ]
    if department_label:
        evidence.append(f"department:{department_label}")
    if content_direction:
        evidence.append(f"content_direction:{content_direction}")
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            if value is None:
                continue
            evidence.append(f"{key}:{value}")

    new_card = {
        "card_id": card_id,
        "role": "talent_development",
        "job_id": work_type_id or "coaching",
        "stage": event_type,
        "status": "recorded",
        "title": f"【带教】{event_label} · {coached_name}",
        "summary": method_summary,
        "current_pattern": outcome,
        "professional_risk": None,
        "next_experiment": next_coaching_focus or "继续观察该员工下一轮真实任务表现",
        "signature": signature,
        "evidence": evidence[:12],
        "source_reflections": [],
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    next_cards = [new_card, *[item for item in cards if isinstance(item, dict)]][:24]
    trainer["experience_journal"] = {
        "last_compiled_at": now_iso,
        "latest_card_id": card_id,
        "cards": next_cards,
    }
    coaching_stats = trainer.get("coaching_stats") if isinstance(trainer.get("coaching_stats"), dict) else {}
    trainer["coaching_stats"] = {
        **coaching_stats,
        "total_records": int(coaching_stats.get("total_records") or 0) + 1,
        "last_record_at": now_iso,
        "last_coached_member_id": coached_member_id,
        "last_event_type": event_type,
    }
    _upsert_trainer_in_runtime(runtime, trainer)
    return new_card


def record_task_approved_coaching(
    runtime: dict,
    *,
    coached_member: dict,
    task: dict,
    independence: dict | None = None,
) -> dict | None:
    member_name = str(coached_member.get("name") or coached_member.get("member_id") or "员工").strip()
    task_title = str(task.get("title") or "正式任务").strip()
    reflection = str(task.get("reflection") or task.get("result_summary") or "").strip()
    outcome = f"{member_name} 完成并确认「{task_title}」"
    method_parts = [
        f"育成官确认本轮交付，任务状态 approved。",
    ]
    if reflection:
        method_parts.append(f"成员复盘摘要：{reflection[:200]}")
    if isinstance(independence, dict) and independence.get("ready_for_independence"):
        method_parts.append("系统判定已接近可独立运营，可考虑放手。")
    next_focus = "推动下一轮任务或评估是否进入放手阶段"
    if isinstance(independence, dict) and independence.get("ready_for_independence"):
        next_focus = "评估放手节奏并收缩逐步带教"
    return append_trainer_coaching_record(
        runtime,
        event_type="task_approved_round",
        coached_member=coached_member,
        outcome=outcome,
        method_summary=" ".join(method_parts).strip(),
        next_coaching_focus=next_focus,
        dedup_key=str(task.get("task_id") or "").strip() or None,
        metadata={
            "task_id": str(task.get("task_id") or "").strip() or None,
            "task_status": "approved",
        },
    )


def record_account_variant_clone_coaching(
    runtime: dict,
    *,
    source_member: dict,
    cloned_member: dict,
    content_direction: str,
) -> dict | None:
    source_name = str(source_member.get("name") or source_member.get("member_id") or "源员工").strip()
    cloned_name = str(cloned_member.get("name") or cloned_member.get("member_id") or "新员工").strip()
    direction = str(content_direction or "").strip() or "新方向"
    return append_trainer_coaching_record(
        runtime,
        event_type="account_variant_clone",
        coached_member=cloned_member,
        outcome=f"从 {source_name} 复制建档 {cloned_name}（同岗位新账号）",
        method_summary=(
            f"沿用 {source_name} 的岗位打法，为新账号 {cloned_name} 建立独立任务线；"
            f"内容方向：{direction}。未复制进行中任务与平台登录态。"
        ),
        next_coaching_focus="为新员工确认画像并分配首轮正式任务",
        dedup_key=str(cloned_member.get("member_id") or "").strip() or None,
        metadata={
            "cloned_from_member_id": str(source_member.get("member_id") or "").strip() or None,
            "content_direction": direction,
        },
    )


def record_commercial_intake_settled_coaching(
    runtime: dict,
    *,
    coached_member: dict,
    intake: dict,
    settled_amount: float | None = None,
) -> dict | None:
    member_name = str(coached_member.get("name") or coached_member.get("member_id") or "员工").strip()
    title = str(intake.get("title") or "商业接单").strip()
    amount = settled_amount if settled_amount is not None else intake.get("settled_amount")
    currency = str(intake.get("currency") or "CNY").strip() or "CNY"
    amount_label = f"{amount} {currency}" if amount is not None else "未标价"
    return append_trainer_coaching_record(
        runtime,
        event_type="commercial_intake_settled",
        coached_member=coached_member,
        outcome=f"{member_name} 完成商业接单「{title}」并结算（{amount_label}）",
        method_summary=(
            f"消费环闭环：接单交付后结算入账。"
            f"能力标签：{', '.join(str(x) for x in (intake.get('needed_capabilities') or [])[:4]) or '未标注'}。"
            "本轮计入员工商业交付成长，并作为可独立运营的实绩信号。"
        ),
        next_coaching_focus="复盘本轮商业交付方法，决定下一单是否扩权或补知识",
        dedup_key=str(intake.get("intake_id") or "").strip() or None,
        metadata={
            "intake_id": str(intake.get("intake_id") or "").strip() or None,
            "project_id": str(intake.get("project_id") or "").strip() or None,
            "settled_amount": amount,
            "loop": "consumption_to_supply",
        },
    )


def record_independence_handoff_coaching(
    runtime: dict,
    *,
    coached_member: dict,
    independence: dict | None = None,
) -> dict | None:
    member_name = str(coached_member.get("name") or coached_member.get("member_id") or "员工").strip()
    met = int((independence or {}).get("met_criteria_count") or 0)
    total = int((independence or {}).get("total_criteria") or 0)
    return append_trainer_coaching_record(
        runtime,
        event_type="independence_handoff",
        coached_member=coached_member,
        outcome=f"{member_name} 达到可独立运营候选（{met}/{total}）",
        method_summary=(
            f"系统判定 {member_name} 已满足独立运营主要标准。"
            "建议育成官收缩带教频率，扩大授权边界，由成员承担更多真实决策与复盘。"
        ),
        next_coaching_focus="制定放手计划：减少逐步确认，保留关键节点抽检",
        dedup_key="independence",
        metadata={
            "met_criteria_count": met,
            "total_criteria": total,
        },
    )


__all__ = [
    "TRAINER_MEMBER_ID",
    "COACHING_EVENT_LABELS",
    "append_trainer_coaching_record",
    "find_trainer_member",
    "record_account_variant_clone_coaching",
    "record_commercial_intake_settled_coaching",
    "record_independence_handoff_coaching",
    "record_task_approved_coaching",
]
