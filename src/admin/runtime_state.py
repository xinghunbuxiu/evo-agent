"""
后台运行时状态读写：自治运行态、学习任务状态。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


def autonomy_runtime_file(workspace: Path, tenant_id: str | None = None) -> Path:
    normalized_tenant_id = str(tenant_id or "").strip()
    if normalized_tenant_id:
        path = workspace / ".tenants" / normalized_tenant_id / "autonomy_runtime.json"
    else:
        path = workspace / ".admin" / "autonomy_runtime.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def normalize_feedback_monitor_runtime(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    return {
        "enabled": bool(payload.get("enabled", True)),
        "interval_seconds": max(300, int(payload.get("interval_seconds", int(os.getenv("EVO_FEEDBACK_MONITOR_INTERVAL_SECONDS", "1800") or 1800)) or 1800)),
        "max_comments": max(1, min(int(payload.get("max_comments", 6) or 6), 20)),
        "auto_reply_feedback": bool(payload.get("auto_reply_feedback", False)),
        "reply_limit": max(0, min(int(payload.get("reply_limit", 2) or 2), 5)),
        "auto_draft_from_followup": bool(payload.get("auto_draft_from_followup", True)),
        "tenants": payload.get("tenants", {}) if isinstance(payload.get("tenants"), dict) else {},
    }


def normalize_self_media_runtime(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    executor = payload.get("executor", {}) if isinstance(payload.get("executor"), dict) else {}
    preferred_mode = str(
        executor.get("preferred_mode")
        or payload.get("preferred_mode")
        or "evo"
    ).strip().lower() or "evo"
    if preferred_mode not in {"auto", "evo"}:
        preferred_mode = "evo"
    return {
        "executor": {
            "preferred_mode": preferred_mode,
            "executor_dir": None,
            "executor_name": str(executor.get("executor_name") or payload.get("executor_name") or "").strip() or "toutiao_executor",
            "executor_adapter": "evo_local",
            "login_target_url": str(executor.get("login_target_url") or payload.get("login_target_url") or "").strip() or None,
        },
        "tenants": payload.get("tenants", {}) if isinstance(payload.get("tenants"), dict) else {},
    }


def _string_list(value: object, *, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items or list(fallback)


def normalize_parent_profile_runtime(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    return {
        "display_name": str(payload.get("display_name") or "Parent Node").strip() or "Parent Node",
        "role_label": str(payload.get("role_label") or "父节点").strip() or "父节点",
        "relationship_to_child": str(payload.get("relationship_to_child") or "guardian").strip() or "guardian",
        "description": str(payload.get("description") or "负责提供方向、资源与边界，陪伴子女智脑成长。").strip() or "负责提供方向、资源与边界，陪伴子女智脑成长。",
    }


def normalize_finance_runtime(payload: dict | None) -> dict:
    """内置财务职能：只读汇总用户项目的经营数据，不执行业务工种任务。"""
    payload = payload if isinstance(payload, dict) else {}
    return {
        "node_id": "finance",
        "system_managed": True,
        "enabled": bool(payload.get("enabled", True)),
        "label": str(payload.get("label") or "财务").strip() or "财务",
        "role_label": str(payload.get("role_label") or "经营结算与资源分配").strip() or "经营结算与资源分配",
        "description": str(
            payload.get("description")
            or "负责公司经营闭环，汇总各用户创建项目/工种的收益与成本。"
        ).strip() or "负责公司经营闭环，汇总各用户创建项目/工种的收益与成本。",
    }


def _is_trainer_member(member: dict) -> bool:
    return str(member.get("primary_role") or "").strip() == "talent_development"


def _is_preset_demo_member(member: dict) -> bool:
    member_id = str(member.get("member_id") or "").strip()
    if member_id in {"self_media_child", "legacy_child_agent"}:
        return True
    if member_id.startswith("self_media_"):
        return True
    return False


def _user_operational_members(members: list[dict]) -> list[dict]:
    return [
        item for item in members
        if isinstance(item, dict)
        and str(item.get("status") or "active").strip() != "archived"
        and not _is_trainer_member(item)
        and not _is_preset_demo_member(item)
    ]


def normalize_training_review_runtime(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    changed_members_payload = payload.get("changed_members")
    changed_members = changed_members_payload if isinstance(changed_members_payload, list) else []
    filtered_members = [
        item for item in changed_members
        if isinstance(item, dict) and not _is_preset_demo_member(item)
    ]
    last_message = str(payload.get("last_message") or "").strip() or None
    if filtered_members != changed_members and last_message and "self_media_child" in last_message.lower():
        last_message = None
    return {
        "last_review_at": payload.get("last_review_at"),
        "last_trigger": str(payload.get("last_trigger") or "system").strip() or "system",
        "changed_count": len(filtered_members),
        "changed_members": filtered_members[:20],
        "last_message": last_message,
    }


def normalize_relationship_runtime(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    parent_inbox_payload = payload.get("parent_inbox")
    parent_inbox_items = parent_inbox_payload if isinstance(parent_inbox_payload, list) else []
    threads_payload = payload.get("conversation_threads")
    threads = threads_payload if isinstance(threads_payload, list) else []
    return {
        "last_delivery_at": payload.get("last_delivery_at"),
        "parent_inbox": [
            item for item in parent_inbox_items
            if isinstance(item, dict)
        ][-40:],
        "conversation_threads": [
            {
                "thread_id": str(item.get("thread_id") or "").strip() or None,
                "participants": item.get("participants", []) if isinstance(item.get("participants"), list) else [],
                "messages": [msg for msg in (item.get("messages", []) if isinstance(item.get("messages"), list) else []) if isinstance(msg, dict)][-40:],
            }
            for item in threads
            if isinstance(item, dict)
        ][-40:],
    }


def normalize_task_center_runtime(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    items_payload = payload.get("items")
    items = items_payload if isinstance(items_payload, list) else []
    recommendations_payload = payload.get("recommendations")
    recommendations = recommendations_payload if isinstance(recommendations_payload, list) else []
    normalized_items: list[dict] = []
    normalized_recommendations: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized_items.append({
            "task_id": str(item.get("task_id") or "").strip() or None,
            "member_id": str(item.get("member_id") or "").strip() or None,
            "assigned_by_member_id": str(item.get("assigned_by_member_id") or "talent_development_officer").strip() or "talent_development_officer",
            "title": str(item.get("title") or "").strip() or None,
            "objective": str(item.get("objective") or "").strip() or None,
            "deliverables": _string_list(item.get("deliverables"), fallback=[]),
            "status": str(item.get("status") or "assigned").strip() or "assigned",
            "assigned_at": item.get("assigned_at"),
            "started_at": item.get("started_at"),
            "submitted_at": item.get("submitted_at"),
            "approved_at": item.get("approved_at"),
            "result_summary": str(item.get("result_summary") or "").strip() or None,
            "reflection": str(item.get("reflection") or "").strip() or None,
            "review_note": str(item.get("review_note") or "").strip() or None,
            "metadata": item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {},
        })
    for item in recommendations:
        if not isinstance(item, dict):
            continue
        normalized_recommendations.append({
            "recommendation_id": str(item.get("recommendation_id") or "").strip() or None,
            "member_id": str(item.get("member_id") or "").strip() or None,
            "source_task_id": str(item.get("source_task_id") or "").strip() or None,
            "title": str(item.get("title") or "").strip() or None,
            "objective": str(item.get("objective") or "").strip() or None,
            "deliverables": _string_list(item.get("deliverables"), fallback=[]),
            "reason": str(item.get("reason") or "").strip() or None,
            "status": str(item.get("status") or "suggested").strip() or "suggested",
            "created_at": item.get("created_at"),
            "adopted_at": item.get("adopted_at"),
            "metadata": item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {},
        })
    return {
        "items": normalized_items[-80:],
        "recommendations": normalized_recommendations[-80:],
    }


def normalize_member_experience_journal(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    cards_payload = payload.get("cards")
    cards = cards_payload if isinstance(cards_payload, list) else []
    normalized_cards: list[dict] = []
    for item in cards:
        if not isinstance(item, dict):
            continue
        normalized_cards.append({
            "card_id": str(item.get("card_id") or "").strip() or None,
            "role": str(item.get("role") or "").strip() or None,
            "job_id": str(item.get("job_id") or "").strip() or None,
            "stage": str(item.get("stage") or "").strip() or None,
            "status": str(item.get("status") or "").strip() or None,
            "title": str(item.get("title") or "").strip() or None,
            "summary": str(item.get("summary") or "").strip() or None,
            "current_pattern": str(item.get("current_pattern") or "").strip() or None,
            "professional_risk": str(item.get("professional_risk") or "").strip() or None,
            "next_experiment": str(item.get("next_experiment") or "").strip() or None,
            "signature": str(item.get("signature") or "").strip() or None,
            "source": str(item.get("source") or "").strip() or None,
            "learning_task_id": str(item.get("learning_task_id") or "").strip() or None,
            "member_id": str(item.get("member_id") or "").strip() or None,
            "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            "evidence": _string_list(item.get("evidence"), fallback=[]),
            "source_reflections": _string_list(item.get("source_reflections"), fallback=[]),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        })
    return {
        "last_compiled_at": payload.get("last_compiled_at"),
        "latest_card_id": str(payload.get("latest_card_id") or "").strip() or None,
        "card_count": len(normalized_cards[-24:]),
        "cards": normalized_cards[-24:],
    }


def normalize_member_memory_hub_runtime(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    retrieval_plan_payload = payload.get("retrieval_plan")
    retrieval_hits_payload = payload.get("retrieval_hits")
    decision_history_payload = payload.get("decision_history")
    decision_summary = payload.get("decision_summary", {}) if isinstance(payload.get("decision_summary"), dict) else {}
    decision_state = payload.get("decision_state", {}) if isinstance(payload.get("decision_state"), dict) else {}
    retrieval_state = payload.get("retrieval_state", {}) if isinstance(payload.get("retrieval_state"), dict) else {}
    last_snapshot = payload.get("last_decision_snapshot", {}) if isinstance(payload.get("last_decision_snapshot"), dict) else {}
    retrieval_plan = retrieval_plan_payload if isinstance(retrieval_plan_payload, list) else []
    retrieval_hits = retrieval_hits_payload if isinstance(retrieval_hits_payload, list) else []
    decision_history = decision_history_payload if isinstance(decision_history_payload, list) else []
    return {
        "active_case_id": str(payload.get("active_case_id") or "").strip() or None,
        "decision_intent": str(payload.get("decision_intent") or "").strip() or None,
        "task_context": payload.get("task_context", {}) if isinstance(payload.get("task_context"), dict) else {},
        "retrieval_plan": [
            {
                "source": str(item.get("source") or "").strip() or None,
                "status": str(item.get("status") or "").strip() or None,
                "query": str(item.get("query") or "").strip() or None,
                "confidence": float(item.get("confidence", 0.0) or 0.0),
                "reason": str(item.get("reason") or "").strip() or None,
            }
            for item in retrieval_plan
            if isinstance(item, dict)
        ][:12],
        "retrieval_hits": [
            {
                "source": str(item.get("source") or "").strip() or None,
                "status": str(item.get("status") or "").strip() or None,
                "query": str(item.get("query") or "").strip() or None,
                "hits": max(0, int(item.get("hits", 0) or 0)),
                "best_match_summary": str(item.get("best_match_summary") or "").strip() or None,
                "confidence": float(item.get("confidence", 0.0) or 0.0),
                "evidence": _string_list(item.get("evidence"), fallback=[]),
                "recommended_action": str(item.get("recommended_action") or "").strip() or None,
            }
            for item in retrieval_hits
            if isinstance(item, dict)
        ][:12],
        "decision_summary": {
            "summary": str(decision_summary.get("summary") or "").strip() or None,
            "used_sources": _string_list(decision_summary.get("used_sources"), fallback=[]),
            "primary_plan": str(decision_summary.get("primary_plan") or "").strip() or None,
            "fallback_plan": str(decision_summary.get("fallback_plan") or "").strip() or None,
            "stop_reason": str(decision_summary.get("stop_reason") or "").strip() or None,
            "escalation_reason": str(decision_summary.get("escalation_reason") or "").strip() or None,
            "verification_goal": str(decision_summary.get("verification_goal") or "").strip() or None,
            "expected_output": str(decision_summary.get("expected_output") or "").strip() or None,
            "external_learning_required": bool(decision_summary.get("external_learning_required", False)),
        },
        "decision_confidence": float(payload.get("decision_confidence", 0.0) or 0.0),
        "fallback_strategy": str(payload.get("fallback_strategy") or "").strip() or None,
        "next_action": str(payload.get("next_action") or "").strip() or None,
        "writeback_targets": _string_list(payload.get("writeback_targets"), fallback=[]),
        "last_run_at": payload.get("last_run_at"),
        "last_trigger": str(payload.get("last_trigger") or "").strip() or None,
        "preferred_sources": _string_list(payload.get("preferred_sources"), fallback=[]),
        "decision_state": {
            "status": str(decision_state.get("status") or "").strip() or None,
            "primary_plan": str(decision_state.get("primary_plan") or "").strip() or None,
            "fallback_plan": str(decision_state.get("fallback_plan") or "").strip() or None,
            "stop_reason": str(decision_state.get("stop_reason") or "").strip() or None,
            "escalation_reason": str(decision_state.get("escalation_reason") or "").strip() or None,
            "verification_goal": str(decision_state.get("verification_goal") or "").strip() or None,
            "expected_output": str(decision_state.get("expected_output") or "").strip() or None,
        },
        "retrieval_state": {
            "preferred_sources": _string_list(retrieval_state.get("preferred_sources"), fallback=[]),
            "local_strength": float(retrieval_state.get("local_strength", 0.0) or 0.0),
            "needs_external_learning": bool(retrieval_state.get("needs_external_learning", False)),
        },
        "last_decision_snapshot": {
            "case_id": str(last_snapshot.get("case_id") or "").strip() or None,
            "member_id": str(last_snapshot.get("member_id") or "").strip() or None,
            "trigger": str(last_snapshot.get("trigger") or "").strip() or None,
            "decision_intent": str(last_snapshot.get("decision_intent") or "").strip() or None,
            "decision_confidence": float(last_snapshot.get("decision_confidence", 0.0) or 0.0),
            "created_at": last_snapshot.get("created_at"),
            "decision_summary": last_snapshot.get("decision_summary", {}) if isinstance(last_snapshot.get("decision_summary"), dict) else {},
            "decision_state": last_snapshot.get("decision_state", {}) if isinstance(last_snapshot.get("decision_state"), dict) else {},
            "retrieval_state": last_snapshot.get("retrieval_state", {}) if isinstance(last_snapshot.get("retrieval_state"), dict) else {},
        },
        "decision_history": [
            item for item in decision_history
            if isinstance(item, dict)
        ][-20:],
    }


def normalize_child_job_runtime(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    job_id = str(payload.get("job_id") or payload.get("work_type_id") or payload.get("role_key") or "autonomous_child_agent").strip() or "autonomous_child_agent"
    return {
        "job_id": job_id,
        "title": str(payload.get("title") or payload.get("label") or job_id).strip() or job_id,
        "status": str(payload.get("status") or "planned").strip() or "planned",
        "priority": str(payload.get("priority") or "high").strip() or "high",
        "target_outcome": str(payload.get("target_outcome") or "").strip() or None,
        "account_id": str(payload.get("account_id") or "default").strip() or "default",
        "notes": str(payload.get("notes") or "").strip() or None,
    }


def _default_training_plan(primary_role: str, role_label: str, training_owner_member_id: str) -> dict:
    training_owner = training_owner_member_id or "talent_development_officer"
    role = primary_role or "autonomous_child_agent"
    label = role_label or role or "子女岗位"

    if role == "talent_development":
        return {
            "stage": "active_training",
            "owner_member_id": training_owner,
            "goals": [
                "稳定建立新子女岗位画像",
                "为每个子女生成可执行的成长路径",
                "持续复盘培养质量并纠偏",
            ],
            "curriculum": [
                "岗位画像建模",
                "训练计划设计",
                "培养结果复盘",
            ],
            "milestones": [
                "完成系统默认育成官初始化",
                "成功接管至少一个新子女培养过程",
                "沉淀可复用的培养经验",
            ],
            "next_action": "继续观察新子女画像需求并优化培养方法",
            "review_after": None,
        }
    defaults = {
        "goals": [
            f"理解 {label} 的核心职责与目标",
            "找到该岗位第一轮可执行案例",
            "沉淀稳定可复用的经验闭环",
        ],
        "curriculum": [
            "岗位认知建立",
            "真实案例实践",
            "复盘与经验入库",
        ],
        "milestones": [
            "完成岗位画像初始化",
            "完成首个真实案例",
            "形成首轮经验卡片",
        ],
        "next_action": f"由育成官继续细化 {label} 的实践训练路径",
    }
    return {
        "stage": "profile_initialized",
        "owner_member_id": training_owner,
        "goals": defaults["goals"],
        "curriculum": defaults["curriculum"],
        "milestones": defaults["milestones"],
        "next_action": defaults["next_action"],
        "review_after": None,
    }


def _slug_text(value: object, fallback: str) -> str:
    text = "".join(ch.lower() if str(ch).isalnum() else "_" for ch in str(value or "").strip())
    while "__" in text:
        text = text.replace("__", "_")
    text = text.strip("_")
    return text or fallback


def _member_instance_paths(tenant_id: str | None, member_id: str) -> dict:
    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
    normalized_member_id = str(member_id or "").strip() or "member"
    base = f".tenants/{normalized_tenant_id}/members/{normalized_member_id}"
    return {
        "tenant_id": normalized_tenant_id,
        "member_root": base,
        "workspace_root": f"{base}/workspace",
        "memory_root": f"{base}/memory",
        "artifacts_root": f"{base}/artifacts",
        "learning_materials_root": f"{base}/learning_materials",
    }


def normalize_child_member_runtime(payload: dict | None, *, index: int = 0) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    identity = payload.get("identity", {}) if isinstance(payload.get("identity"), dict) else {}
    role_memory = payload.get("role_memory", {}) if isinstance(payload.get("role_memory"), dict) else {}
    growth_state = payload.get("growth_state", {}) if isinstance(payload.get("growth_state"), dict) else {}
    world_observation = payload.get("world_observation", {}) if isinstance(payload.get("world_observation"), dict) else {}
    tentative_role = str(
        payload.get("primary_role")
        or role_memory.get("primary_identity")
        or payload.get("role_key")
        or ""
    ).strip() or "autonomous_child_agent"
    current_jobs_payload = payload.get("current_jobs")
    if isinstance(current_jobs_payload, list):
        current_jobs = [normalize_child_job_runtime(item) for item in current_jobs_payload if isinstance(item, dict)]
    else:
        current_jobs = []
    if not current_jobs:
        current_jobs = [
            normalize_child_job_runtime({
                "job_id": tentative_role,
                "title": payload.get("role_label") or tentative_role or "待分配岗位",
                "status": "profile_initialized",
                "priority": "high",
                "target_outcome": payload.get("next_goal") or "完成首轮真实案例并形成稳定经验",
                "account_id": payload.get("account_id") or "default",
            }),
        ]
    default_name = str(identity.get("name") or payload.get("name") or ("Evo" if index == 0 else f"Child {index + 1}")).strip() or ("Evo" if index == 0 else f"Child {index + 1}")
    member_id = str(payload.get("member_id") or identity.get("agent_id") or "").strip() or f"child_{_slug_text(default_name, str(index + 1))}"
    primary_role = str(payload.get("primary_role") or current_jobs[0].get("job_id") or "autonomous_child_agent").strip() or "autonomous_child_agent"
    persona = payload.get("persona", {}) if isinstance(payload.get("persona"), dict) else {}
    operating_contract = payload.get("operating_contract", {}) if isinstance(payload.get("operating_contract"), dict) else {}
    onboarding = payload.get("onboarding", {}) if isinstance(payload.get("onboarding"), dict) else {}
    organization = payload.get("organization", {}) if isinstance(payload.get("organization"), dict) else {}
    content_profile = payload.get("content_profile", {}) if isinstance(payload.get("content_profile"), dict) else {}
    training_plan = payload.get("training_plan", {}) if isinstance(payload.get("training_plan"), dict) else {}
    experience_journal = payload.get("experience_journal", {}) if isinstance(payload.get("experience_journal"), dict) else {}
    training_owner_member_id = str(onboarding.get("training_owner_member_id") or "talent_development_officer").strip() or "talent_development_officer"
    role_label = str(persona.get("role_label") or payload.get("role_label") or "子女智脑").strip() or "子女智脑"
    default_training_plan = _default_training_plan(primary_role, role_label, training_owner_member_id)
    memory_hub = normalize_member_memory_hub_runtime(payload.get("memory_hub"))
    instance_runtime = payload.get("instance_runtime", {}) if isinstance(payload.get("instance_runtime"), dict) else {}
    runtime_paths = _member_instance_paths(payload.get("tenant_id"), member_id)
    return {
        "member_id": member_id,
        "name": default_name,
        "status": str(payload.get("status") or "active").strip() or "active",
        "archived_at": payload.get("archived_at"),
        "system_managed": bool(payload.get("system_managed", False)),
        "identity_type": str(payload.get("identity_type") or "child_agent").strip() or "child_agent",
        "primary_role": primary_role,
        "role_key": str(payload.get("role_key") or primary_role).strip() or primary_role,
        "persona": {
            "role_label": role_label,
            "tone": str(persona.get("tone") or identity.get("tone") or "curious_steady").strip() or "curious_steady",
            "speaking_style": str(persona.get("speaking_style") or payload.get("speaking_style") or "clear_supportive").strip() or "clear_supportive",
            "interaction_style": str(persona.get("interaction_style") or payload.get("interaction_style") or "friendly_observant").strip() or "friendly_observant",
            "self_description": str(persona.get("self_description") or identity.get("self_description") or "我是正在成长中的子女智脑，会持续观察、行动、复盘并沉淀经验。").strip() or "我是正在成长中的子女智脑，会持续观察、行动、复盘并沉淀经验。",
        },
        "identity": {
            "agent_id": str(identity.get("agent_id") or member_id).strip() or member_id,
            "name": default_name,
            "self_description": str(identity.get("self_description") or persona.get("self_description") or "我是正在成长中的子女智脑，会持续观察、行动、复盘并沉淀经验。").strip() or "我是正在成长中的子女智脑，会持续观察、行动、复盘并沉淀经验。",
            "tone": str(identity.get("tone") or persona.get("tone") or "curious_steady").strip() or "curious_steady",
        },
        "role_memory": {
            "primary_identity": str(role_memory.get("primary_identity") or primary_role or "autonomous_child_agent").strip() or "autonomous_child_agent",
            "long_term_goal": str(role_memory.get("long_term_goal") or payload.get("long_term_goal") or "持续成长为能独立理解目标、执行任务、复盘经验并帮助他人的智脑个体。").strip() or "持续成长为能独立理解目标、执行任务、复盘经验并帮助他人的智脑个体。",
            "strengths": _string_list(role_memory.get("strengths"), fallback=["自主研究", "智能分析", "复盘成长"]),
            "shortcomings": _string_list(role_memory.get("shortcomings"), fallback=["真实经验不足", "需要更多案例训练"]),
            "preferred_domains": _string_list(role_memory.get("preferred_domains"), fallback=[primary_role]),
        },
        "growth_state": {
            "phase": str(growth_state.get("phase") or "bootstrapping").strip() or "bootstrapping",
            "current_focus": str(growth_state.get("current_focus") or primary_role).strip() or primary_role,
            "blocked_reason": str(growth_state.get("blocked_reason") or "").strip() or None,
            "next_goal": str(growth_state.get("next_goal") or "跑通真实案例并形成可复用经验").strip() or "跑通真实案例并形成可复用经验",
            "last_reflection_at": growth_state.get("last_reflection_at"),
            # 消费环结算回写（供给环商业实绩）
            "last_commercial_settled_at": growth_state.get("last_commercial_settled_at"),
            "commercial_settled_count": growth_state.get("commercial_settled_count"),
            "commercial_settled_revenue": growth_state.get("commercial_settled_revenue"),
            "last_commercial_intake_id": str(growth_state.get("last_commercial_intake_id") or "").strip() or None,
            "pending_git_export": bool(growth_state.get("pending_git_export")),
            "pending_git_export_reason": str(growth_state.get("pending_git_export_reason") or "").strip() or None,
            "last_git_export_at": growth_state.get("last_git_export_at"),
            "last_git_export_status": str(growth_state.get("last_git_export_status") or "").strip() or None,
            "last_git_export_path": str(growth_state.get("last_git_export_path") or "").strip() or None,
            "last_git_export_root": str(growth_state.get("last_git_export_root") or "").strip() or None,
        },
        "operating_contract": {
            "autonomy_mode": str(operating_contract.get("autonomy_mode") or "observe_plan_act_reflect").strip() or "observe_plan_act_reflect",
            "learning_strategy": str(operating_contract.get("learning_strategy") or "case_first_iterative_growth").strip() or "case_first_iterative_growth",
            "allow_external_learning": bool(operating_contract.get("allow_external_learning", True)),
            "allow_shared_knowledge": bool(operating_contract.get("allow_shared_knowledge", False)),
            "must_record_experience": bool(operating_contract.get("must_record_experience", True)),
        },
        "onboarding": {
            "created_by_member_id": str(onboarding.get("created_by_member_id") or "talent_development_officer").strip() or "talent_development_officer",
            "training_owner_member_id": training_owner_member_id,
            "status": str(onboarding.get("status") or "profile_initialized").strip() or "profile_initialized",
            "created_at": onboarding.get("created_at"),
            "notes": str(onboarding.get("notes") or "").strip() or None,
            "cloned_from_member_id": str(onboarding.get("cloned_from_member_id") or "").strip() or None,
            "clone_mode": str(onboarding.get("clone_mode") or "").strip() or None,
        },
        "organization": {
            "department_id": str(organization.get("department_id") or "").strip() or None,
            "department_label": str(organization.get("department_label") or "").strip() or None,
        },
        "content_profile": {
            "content_direction": str(content_profile.get("content_direction") or "").strip() or None,
        },
        "training_plan": {
            "stage": str(training_plan.get("stage") or default_training_plan.get("stage") or "profile_initialized").strip() or "profile_initialized",
            "owner_member_id": str(training_plan.get("owner_member_id") or default_training_plan.get("owner_member_id") or training_owner_member_id).strip() or training_owner_member_id,
            "goals": _string_list(training_plan.get("goals"), fallback=default_training_plan.get("goals", [])),
            "curriculum": _string_list(training_plan.get("curriculum"), fallback=default_training_plan.get("curriculum", [])),
            "milestones": _string_list(training_plan.get("milestones"), fallback=default_training_plan.get("milestones", [])),
            "next_action": str(training_plan.get("next_action") or default_training_plan.get("next_action") or "等待育成官制定下一步训练动作").strip() or "等待育成官制定下一步训练动作",
            "review_after": training_plan.get("review_after"),
        },
        "experience_journal": normalize_member_experience_journal(experience_journal),
        "coaching_stats": payload.get("coaching_stats", {}) if isinstance(payload.get("coaching_stats"), dict) else {},
        "memory_hub": memory_hub,
        "decision_state": payload.get("decision_state", {}) if isinstance(payload.get("decision_state"), dict) else memory_hub.get("decision_state", {}),
        "retrieval_state": payload.get("retrieval_state", {}) if isinstance(payload.get("retrieval_state"), dict) else memory_hub.get("retrieval_state", {}),
        "active_case_id": str(payload.get("active_case_id") or memory_hub.get("active_case_id") or "").strip() or None,
        "last_decision_snapshot": payload.get("last_decision_snapshot", {}) if isinstance(payload.get("last_decision_snapshot"), dict) else memory_hub.get("last_decision_snapshot", {}),
        "decision_history": payload.get("decision_history", []) if isinstance(payload.get("decision_history"), list) else memory_hub.get("decision_history", []),
        "instance_runtime": {
            "instance_id": str(instance_runtime.get("instance_id") or member_id).strip() or member_id,
            "execution_mode": str(instance_runtime.get("execution_mode") or "employee_instance").strip() or "employee_instance",
            "workspace_root": str(instance_runtime.get("workspace_root") or runtime_paths["workspace_root"]).strip() or runtime_paths["workspace_root"],
            "memory_root": str(instance_runtime.get("memory_root") or runtime_paths["memory_root"]).strip() or runtime_paths["memory_root"],
            "artifacts_root": str(instance_runtime.get("artifacts_root") or runtime_paths["artifacts_root"]).strip() or runtime_paths["artifacts_root"],
            "learning_materials_root": str(instance_runtime.get("learning_materials_root") or runtime_paths["learning_materials_root"]).strip() or runtime_paths["learning_materials_root"],
            "official_work_policy": str(instance_runtime.get("official_work_policy") or "employee_self_execution_only").strip() or "employee_self_execution_only",
            "external_project_policy": str(instance_runtime.get("external_project_policy") or "learning_material_only").strip() or "learning_material_only",
        },
        "current_jobs": current_jobs,
        "world_observation": {
            "last_signal": str(world_observation.get("last_signal") or "").strip() or None,
            "blocked_by": _string_list(world_observation.get("blocked_by"), fallback=[]),
            "active_feedback_channels": _string_list(world_observation.get("active_feedback_channels"), fallback=["platform_comments", "mission_results", "runtime_errors"]),
        },
    }


def _default_talent_development_member() -> dict:
    return normalize_child_member_runtime({
        "member_id": "talent_development_officer",
        "name": "Talent Development Officer",
        "system_managed": True,
        "identity_type": "child_agent",
        "primary_role": "talent_development",
        "persona": {
            "role_label": "育成官子女",
            "tone": "steady_supportive",
            "speaking_style": "structured_patient",
            "interaction_style": "coach_like",
            "self_description": "我是系统默认的育成官子女，负责为新子女建立画像、安排初始培训，并持续推动其他孩子成长。",
        },
        "identity": {
            "agent_id": "talent_development_officer",
            "name": "Talent Development Officer",
            "self_description": "我是系统默认的育成官子女，负责为新子女建立画像、安排初始培训，并持续推动其他孩子成长。",
            "tone": "steady_supportive",
        },
        "role_memory": {
            "primary_identity": "talent_development",
            "long_term_goal": "成长为能够稳定建立岗位画像、设计成长路径、纠偏培养过程并提升整体子女质量的育成官。",
            "strengths": ["画像建模", "培训设计", "成长纠偏"],
            "shortcomings": ["岗位实践样本仍需增加", "跨岗位培养经验还在累积"],
            "preferred_domains": ["talent_development", "persona_design", "training_management"],
        },
        "growth_state": {
            "phase": "active_training",
            "current_focus": "talent_development",
            "next_goal": "完善子女画像、训练路径与复盘机制，稳定推动其他孩子成长",
        },
        "operating_contract": {
            "autonomy_mode": "observe_plan_act_reflect",
            "learning_strategy": "profile_train_review_improve",
            "allow_external_learning": True,
            "allow_shared_knowledge": False,
            "must_record_experience": True,
        },
        "onboarding": {
            "created_by_member_id": "system",
            "training_owner_member_id": "talent_development_officer",
            "status": "active_trainer",
            "created_at": datetime.now().isoformat(),
            "notes": "系统默认育成官，负责其他子女的画像与培训。",
        },
        "current_jobs": [{
            "job_id": "talent_development",
            "title": "子女人格塑造与培训",
            "status": "active",
            "priority": "high",
            "target_outcome": "为新子女建立稳定画像、训练计划与成长纠偏闭环",
            "account_id": "default",
        }],
        "world_observation": {
            "last_signal": None,
            "blocked_by": [],
            "active_feedback_channels": ["member_profiles", "training_feedback", "runtime_errors"],
        },
    }, index=0)


def normalize_child_members_runtime(payload: object, *, legacy_child_agent: dict | None = None) -> dict:
    items_payload = []
    selected_member_id = None
    if isinstance(payload, dict):
        items_payload = payload.get("items", []) if isinstance(payload.get("items"), list) else []
        selected_member_id = str(payload.get("selected_member_id") or "").strip() or None
    elif isinstance(payload, list):
        items_payload = payload

    members = [
        normalize_child_member_runtime(item, index=index)
        for index, item in enumerate(items_payload)
        if isinstance(item, dict) and not _is_preset_demo_member(item)
    ]

    if not members and isinstance(legacy_child_agent, dict) and legacy_child_agent:
        legacy_identity = legacy_child_agent.get("identity", {}) if isinstance(legacy_child_agent.get("identity"), dict) else {}
        legacy_member_id = str(legacy_child_agent.get("member_id") or legacy_identity.get("agent_id") or "").strip()
        if legacy_member_id and not _is_preset_demo_member({"member_id": legacy_member_id}):
            members = [
                normalize_child_member_runtime({
                    "member_id": legacy_member_id or "legacy_child_agent",
                    "name": str(legacy_identity.get("name") or "Legacy Child Agent").strip() or "Legacy Child Agent",
                    "primary_role": str(
                        legacy_child_agent.get("primary_role")
                        or (legacy_child_agent.get("role_memory", {}) if isinstance(legacy_child_agent.get("role_memory"), dict) else {}).get("primary_identity")
                        or "autonomous_child_agent"
                    ).strip() or "autonomous_child_agent",
                    "persona": {
                        "role_label": str((legacy_child_agent.get("persona", {}) if isinstance(legacy_child_agent.get("persona"), dict) else {}).get("role_label") or "岗位子女").strip() or "岗位子女",
                        "self_description": legacy_identity.get("self_description"),
                        "tone": legacy_identity.get("tone"),
                    },
                    **legacy_child_agent,
                }, index=0)
            ]

    if not any(_is_trainer_member(item) for item in members):
        members.insert(0, _default_talent_development_member())

    user_members = _user_operational_members(members)
    normalized_selected = selected_member_id
    if normalized_selected and not any(item.get("member_id") == normalized_selected for item in user_members):
        normalized_selected = None
    if not normalized_selected and user_members:
        normalized_selected = str(user_members[0].get("member_id") or "").strip() or None

    return {
        "selected_member_id": normalized_selected,
        "items": members,
    }


def normalize_child_agent_runtime(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    member = normalize_child_member_runtime(payload, index=0)
    return {
        "identity": member.get("identity", {}),
        "role_memory": member.get("role_memory", {}),
        "growth_state": member.get("growth_state", {}),
        "training_plan": member.get("training_plan", {}),
        "instance_runtime": member.get("instance_runtime", {}),
        "current_jobs": member.get("current_jobs", []),
        "world_observation": member.get("world_observation", {}),
    }


def create_employee_member_runtime(
    *,
    tenant_id: str,
    name: str,
    role_label: str,
    role_key: str,
    self_description: str,
    long_term_goal: str,
    created_by_member_id: str = "talent_development_officer",
    training_owner_member_id: str = "talent_development_officer",
    work_type_id: str | None = None,
    work_type_title: str | None = None,
    work_type_default_goal: str | None = None,
    account_id: str | None = None,
    department_id: str | None = None,
    department_label: str | None = None,
    content_direction: str | None = None,
    cloned_from_member_id: str | None = None,
    clone_mode: str | None = None,
    persona_overrides: dict | None = None,
    role_memory_overrides: dict | None = None,
    operating_contract_overrides: dict | None = None,
    training_plan_overrides: dict | None = None,
) -> dict:
    normalized_name = str(name or "").strip() or "New Employee"
    normalized_work_type_id = str(work_type_id or "").strip() or None
    normalized_work_type_title = str(work_type_title or "").strip() or None
    normalized_work_type_goal = str(work_type_default_goal or "").strip() or None
    normalized_role_label = str(role_label or role_key or "岗位员工").strip() or "岗位员工"
    if normalized_work_type_id:
        normalized_role_label = normalized_work_type_title or normalized_role_label or normalized_work_type_id
        normalized_role_key = _slug_text(normalized_work_type_id, "autonomous_child_agent")
    else:
        normalized_role_key = _slug_text(role_key or normalized_role_label or normalized_name, "autonomous_child_agent")
    member_id = f"employee_{_slug_text(normalized_name, normalized_role_key)}"
    description = str(
        self_description
        or f"我是 {normalized_role_label}，会围绕岗位目标持续学习、行动、复盘并成长。"
    ).strip()
    goal = str(
        normalized_work_type_goal
        or long_term_goal
        or f"成长为能够独立承担 {normalized_role_label} 岗位目标的员工个体。"
    ).strip()
    job_id = normalized_work_type_id or normalized_role_key
    normalized_account_id = str(account_id or "default").strip() or "default"
    normalized_department_id = str(department_id or "").strip() or None
    normalized_department_label = str(department_label or "").strip() or None
    normalized_content_direction = str(content_direction or "").strip() or None
    normalized_clone_from = str(cloned_from_member_id or "").strip() or None
    normalized_clone_mode = str(clone_mode or "").strip() or None
    persona_patch = persona_overrides if isinstance(persona_overrides, dict) else {}
    role_memory_patch = role_memory_overrides if isinstance(role_memory_overrides, dict) else {}
    operating_patch = operating_contract_overrides if isinstance(operating_contract_overrides, dict) else {}
    training_patch = training_plan_overrides if isinstance(training_plan_overrides, dict) else {}
    onboarding_notes = "已由育成师建立初始画像与边界，等待首轮正式任务。"
    if normalized_clone_from and normalized_clone_mode == "account_variant":
        onboarding_notes = (
            f"由同岗位复制建档（源员工 {normalized_clone_from}），"
            f"账号与内容方向独立，等待首轮正式任务。"
        )
    return normalize_child_member_runtime({
        "tenant_id": tenant_id,
        "member_id": member_id,
        "name": normalized_name,
        "primary_role": normalized_role_key,
        "role_key": normalized_role_key,
        "role_label": normalized_role_label,
        "organization": {
            "department_id": normalized_department_id,
            "department_label": normalized_department_label,
        },
        "content_profile": {
            "content_direction": normalized_content_direction,
        },
        "persona": {
            "role_label": normalized_role_label,
            "self_description": description,
            "tone": str(persona_patch.get("tone") or "curious_steady").strip() or "curious_steady",
            "speaking_style": str(persona_patch.get("speaking_style") or "clear_supportive").strip() or "clear_supportive",
            "interaction_style": str(persona_patch.get("interaction_style") or "friendly_observant").strip() or "friendly_observant",
        },
        "identity": {
            "agent_id": member_id,
            "name": normalized_name,
            "self_description": description,
            "tone": "curious_steady",
        },
        "role_memory": {
            "primary_identity": normalized_role_key,
            "long_term_goal": goal,
            "strengths": _string_list(role_memory_patch.get("strengths"), fallback=["自主研究", "智能分析", "复盘成长"]),
            "shortcomings": _string_list(role_memory_patch.get("shortcomings"), fallback=["真实案例仍需积累", "岗位稳定性还需要验证"]),
            "preferred_domains": _string_list(role_memory_patch.get("preferred_domains"), fallback=[normalized_role_key]),
        },
        "growth_state": {
            "phase": "profile_initialized",
            "current_focus": normalized_role_key,
            "next_goal": "完成首轮真实案例并建立第一批经验资产",
        },
        "operating_contract": {
            "autonomy_mode": str(operating_patch.get("autonomy_mode") or "observe_plan_act_reflect").strip() or "observe_plan_act_reflect",
            "learning_strategy": str(operating_patch.get("learning_strategy") or "self_directed_case_growth").strip() or "self_directed_case_growth",
            "allow_external_learning": bool(operating_patch.get("allow_external_learning", True)),
            "allow_shared_knowledge": bool(operating_patch.get("allow_shared_knowledge", False)),
            "must_record_experience": bool(operating_patch.get("must_record_experience", True)),
        },
        "onboarding": {
            "created_by_member_id": created_by_member_id,
            "training_owner_member_id": training_owner_member_id,
            "status": "profile_initialized",
            "created_at": datetime.now().isoformat(),
            "notes": onboarding_notes,
            "cloned_from_member_id": normalized_clone_from,
            "clone_mode": normalized_clone_mode,
        },
        "training_plan": {
            "stage": "profile_initialized",
            "owner_member_id": training_owner_member_id,
            "next_action": str(training_patch.get("next_action") or "等待育成官制定下一步训练动作").strip() or "等待育成官制定下一步训练动作",
            "curriculum": _string_list(training_patch.get("curriculum"), fallback=[]),
            "milestones": _string_list(training_patch.get("milestones"), fallback=[]),
        },
        "current_jobs": [{
            "job_id": job_id,
            "title": normalized_role_label,
            "status": "profile_initialized",
            "priority": "high",
            "target_outcome": "接到首轮正式任务后自行生成学习计划与行动链，并完成第一次闭环复盘",
            "account_id": normalized_account_id,
        }],
        "instance_runtime": {
            "instance_id": member_id,
            "execution_mode": "employee_instance",
            "official_work_policy": "employee_self_execution_only",
            "external_project_policy": "learning_material_only",
        },
    })


def _purge_preset_runtime_state(payload: dict) -> dict:
    """移除历史预置测试成员在自治/反馈/关系层中的残留状态。"""
    cleaned = dict(payload)
    self_media = cleaned.get("self_media") if isinstance(cleaned.get("self_media"), dict) else {}
    tenants = self_media.get("tenants") if isinstance(self_media.get("tenants"), dict) else {}
    for key in list(tenants.keys()):
        if key in {"self_media_child", "default", "test"} or str(key).startswith("self_media_"):
            tenants.pop(key, None)
    self_media["tenants"] = tenants
    cleaned["self_media"] = self_media

    feedback = cleaned.get("feedback_monitor") if isinstance(cleaned.get("feedback_monitor"), dict) else {}
    fb_tenants = feedback.get("tenants") if isinstance(feedback.get("tenants"), dict) else {}
    for key in list(fb_tenants.keys()):
        if key in {"self_media_child", "default", "test"}:
            fb_tenants.pop(key, None)
    feedback["tenants"] = fb_tenants
    cleaned["feedback_monitor"] = feedback

    relationship = cleaned.get("relationship_center") if isinstance(cleaned.get("relationship_center"), dict) else {}
    threads = relationship.get("conversation_threads") if isinstance(relationship.get("conversation_threads"), list) else []
    relationship["conversation_threads"] = [
        thread for thread in threads
        if isinstance(thread, dict)
        and "self_media_child" not in str(thread.get("thread_id") or "")
        and "self_media_child" not in ",".join(str(x) for x in (thread.get("participants") or []))
    ]
    inbox = relationship.get("parent_inbox") if isinstance(relationship.get("parent_inbox"), list) else []
    relationship["parent_inbox"] = inbox[-20:] if len(inbox) > 20 else inbox
    cleaned["relationship_center"] = relationship
    cleaned.pop("child_agent", None)
    return cleaned


def normalize_autonomy_runtime(payload: dict | None) -> dict:
    payload = _purge_preset_runtime_state(payload if isinstance(payload, dict) else {})
    child_members = normalize_child_members_runtime(payload.get("child_members"), legacy_child_agent=payload.get("child_agent"))
    user_members = _user_operational_members(child_members.get("items", []))
    selected_member_id = child_members.get("selected_member_id")
    selected_member = next(
        (item for item in user_members if item.get("member_id") == selected_member_id),
        user_members[0] if user_members else None,
    )
    from admin.collaboration_runtime import normalize_collaboration_center
    from admin.intake_runtime import normalize_intake_center

    return {
        "tenant_id": str(payload.get("tenant_id") or "").strip() or None,
        "enabled": bool(payload.get("enabled", True)),
        "domain": payload.get("domain", "operations"),
        "status": payload.get("status", "idle"),
        "loop_interval_seconds": int(payload.get("loop_interval_seconds", int(os.getenv("EVO_AUTONOMY_INTERVAL_SECONDS", "20") or 20))),
        "last_run_at": payload.get("last_run_at"),
        "last_error": payload.get("last_error"),
        "samples": payload.get("samples", {}) if isinstance(payload.get("samples"), dict) else {},
        "feedback_monitor": normalize_feedback_monitor_runtime(payload.get("feedback_monitor")),
        "self_media": normalize_self_media_runtime(payload.get("self_media")),
        "parent_profile": normalize_parent_profile_runtime(payload.get("parent_profile")),
        "finance": normalize_finance_runtime(payload.get("finance")),
        "training_review": normalize_training_review_runtime(payload.get("training_review")),
        "relationship_center": normalize_relationship_runtime(payload.get("relationship_center")),
        "task_center": normalize_task_center_runtime(payload.get("task_center")),
        "collaboration_center": normalize_collaboration_center(payload.get("collaboration_center")),
        "intake_center": normalize_intake_center(payload.get("intake_center")),
        "child_members": child_members,
        "primary_child_member_id": selected_member.get("member_id") if isinstance(selected_member, dict) else None,
        "child_agent": normalize_child_agent_runtime(selected_member if isinstance(selected_member, dict) else None),
    }


def load_autonomy_runtime(workspace: Path, tenant_id: str | None = None) -> dict:
    normalized_tenant_id = str(tenant_id or "").strip() or None
    path = autonomy_runtime_file(workspace, normalized_tenant_id)
    if not path.is_file():
        if normalized_tenant_id == "default":
            legacy_path = autonomy_runtime_file(workspace)
            if legacy_path.is_file():
                try:
                    data = json.loads(legacy_path.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
                normalized = normalize_autonomy_runtime({
                    **(data if isinstance(data, dict) else {}),
                    "tenant_id": normalized_tenant_id,
                })
                return normalized
        return normalize_autonomy_runtime({"tenant_id": normalized_tenant_id} if normalized_tenant_id else None)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if normalized_tenant_id:
        data = {
            **(data if isinstance(data, dict) else {}),
            "tenant_id": normalized_tenant_id,
        }
    return normalize_autonomy_runtime(data)


def save_autonomy_runtime(workspace: Path, payload: dict, tenant_id: str | None = None) -> None:
    normalized_tenant_id = str(tenant_id or (payload.get("tenant_id") if isinstance(payload, dict) else "") or "").strip() or None
    normalized_payload = normalize_autonomy_runtime({
        **(payload if isinstance(payload, dict) else {}),
        "tenant_id": normalized_tenant_id,
    })
    autonomy_runtime_file(workspace, normalized_tenant_id).write_text(
        json.dumps(normalized_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def learning_tasks_file(workspace: Path) -> Path:
    path = workspace / ".admin" / "learning_tasks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_learning_tasks(workspace: Path) -> dict:
    path = learning_tasks_file(workspace)
    if not path.is_file():
        return {
            "updated_at": None,
            "tasks": {},
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "updated_at": data.get("updated_at"),
        "tasks": data.get("tasks", {}) if isinstance(data.get("tasks"), dict) else {},
    }


def save_learning_tasks(workspace: Path, payload: dict) -> None:
    normalized = {
        "updated_at": datetime.now().isoformat(),
        "tasks": payload.get("tasks", {}) if isinstance(payload, dict) else {},
    }
    learning_tasks_file(workspace).write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
