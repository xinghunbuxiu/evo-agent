"""商业接单运行时：配置驱动，不绑定具体工种或平台。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from admin.intake_policy_runtime import expand_capabilities, resolve_intake_rule
from admin.runtime_state import normalize_child_members_runtime
from admin.task_center_runtime import has_open_formal_task, upsert_task
from admin.worker_route_runtime import (
    resolve_primary_worker_id,
    resolve_work_type_id,
    worker_has_operation_tasks,
    worker_manifest,
)
from work_types import get_work_type, load_work_types

ORCHESTRATOR_MEMBER_ID = "talent_development_officer"

INTAKE_STATUSES = frozenset({
    "received",
    "analyzing",
    "assigned",
    "in_progress",
    "delivered",
    "settled",
    "cancelled",
})

FUNNEL_STATUSES = (
    "received",
    "analyzing",
    "assigned",
    "in_progress",
    "delivered",
    "settled",
    "cancelled",
)


def normalize_intake_center(payload: dict | None) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    normalized_items: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        intake_id = str(item.get("intake_id") or "").strip()
        if not intake_id:
            continue
        status = str(item.get("status") or "received").strip() or "received"
        if status not in INTAKE_STATUSES:
            status = "received"
        deliverables = item.get("expected_deliverables")
        capabilities = item.get("needed_capabilities")
        normalized_items.append({
            "intake_id": intake_id,
            "title": str(item.get("title") or "").strip() or None,
            "description": str(item.get("description") or "").strip() or None,
            "expected_deliverables": [
                str(x).strip() for x in (deliverables if isinstance(deliverables, list) else []) if str(x).strip()
            ],
            "needed_capabilities": [
                str(x).strip() for x in (capabilities if isinstance(capabilities, list) else []) if str(x).strip()
            ],
            "source": str(item.get("source") or "outsourcing").strip() or "outsourcing",
            "status": status,
            "budget": item.get("budget"),
            "quoted_amount": item.get("quoted_amount"),
            "settled_amount": item.get("settled_amount"),
            "currency": str(item.get("currency") or "CNY").strip() or "CNY",
            "client_label": str(item.get("client_label") or "").strip() or None,
            "deadline_at": item.get("deadline_at"),
            "policy_id": str(item.get("policy_id") or "").strip() or None,
            "member_id": str(item.get("member_id") or "").strip() or None,
            "task_id": str(item.get("task_id") or "").strip() or None,
            "project_id": str(item.get("project_id") or "").strip() or None,
            "work_type_id": str(item.get("work_type_id") or "").strip() or None,
            "routing": item.get("routing") if isinstance(item.get("routing"), dict) else {},
            "fulfillment": item.get("fulfillment") if isinstance(item.get("fulfillment"), dict) else {},
            "finance": item.get("finance") if isinstance(item.get("finance"), dict) else {},
            "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "assigned_at": item.get("assigned_at"),
            "delivered_at": item.get("delivered_at"),
            "settled_at": item.get("settled_at"),
        })
    normalized_events: list[dict] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        normalized_events.append({
            "event_id": str(item.get("event_id") or "").strip() or None,
            "event_type": str(item.get("event_type") or "").strip() or None,
            "intake_id": str(item.get("intake_id") or "").strip() or None,
            "created_at": item.get("created_at"),
            "payload": item.get("payload") if isinstance(item.get("payload"), dict) else {},
        })
    return {
        "items": normalized_items[-120:],
        "events": normalized_events[-200:],
    }


def _now() -> str:
    return datetime.now().isoformat()


def _find_member(runtime: dict, member_id: str) -> dict | None:
    members = normalize_child_members_runtime(
        runtime.get("child_members"),
        legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
    )
    target = str(member_id or "").strip()
    if not target:
        return None
    return next(
        (
            item for item in members.get("items", [])
            if isinstance(item, dict) and str(item.get("member_id") or "").strip() == target
        ),
        None,
    )


def _append_event(center: dict, *, event_type: str, intake_id: str, payload: dict | None = None) -> None:
    events = center.get("events")
    if not isinstance(events, list):
        events = []
        center["events"] = events
    events.append({
        "event_id": f"intake_event:{intake_id}:{int(datetime.now().timestamp() * 1000)}",
        "event_type": event_type,
        "intake_id": intake_id,
        "created_at": _now(),
        "payload": payload if isinstance(payload, dict) else {},
    })
    center["events"] = events[-200:]


def _upsert_intake(center: dict, intake: dict) -> dict:
    items = center.get("items")
    if not isinstance(items, list):
        items = []
        center["items"] = items
    intake_id = str(intake.get("intake_id") or "").strip()
    existing = next(
        (item for item in items if isinstance(item, dict) and str(item.get("intake_id") or "").strip() == intake_id),
        None,
    )
    if existing is None:
        items.append(intake)
    else:
        existing.update(intake)
    center["items"] = items[-120:]
    return intake


def _get_intake(center: dict, intake_id: str) -> dict | None:
    target = str(intake_id or "").strip()
    items = center.get("items") if isinstance(center.get("items"), list) else []
    return next(
        (item for item in items if isinstance(item, dict) and str(item.get("intake_id") or "").strip() == target),
        None,
    )


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _routing_feedback_path(workspace: Path) -> Path:
    path = workspace / ".admin" / "intake_routing_feedback.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_routing_feedback(workspace: Path) -> list[dict]:
    """Historical assign/settle signals for capability routing (config file, not code branches)."""
    path = _routing_feedback_path(workspace)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)][-200:]


def append_routing_feedback(workspace: Path, entry: dict) -> dict:
    items = load_routing_feedback(workspace)
    record = {
        "feedback_id": str(entry.get("feedback_id") or f"rfb:{int(datetime.now().timestamp() * 1000)}").strip(),
        "event_type": str(entry.get("event_type") or "").strip() or None,
        "intake_id": str(entry.get("intake_id") or "").strip() or None,
        "member_id": str(entry.get("member_id") or "").strip() or None,
        "recommended_member_id": str(entry.get("recommended_member_id") or "").strip() or None,
        "needed_capabilities": [
            str(x).strip()
            for x in (entry.get("needed_capabilities") if isinstance(entry.get("needed_capabilities"), list) else [])
            if str(x).strip()
        ],
        "override_reason": str(entry.get("override_reason") or "").strip() or None,
        "outcome": str(entry.get("outcome") or "").strip() or None,
        "settled_amount": entry.get("settled_amount"),
        "created_at": entry.get("created_at") or _now(),
    }
    items.append(record)
    path = _routing_feedback_path(workspace)
    path.write_text(
        json.dumps({"version": 1, "items": items[-200:], "updated_at": _now()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record


def routing_feedback_score_bonus(
    workspace: Path,
    *,
    member_id: str,
    needed_capabilities: list[str],
) -> tuple[int, list[str]]:
    """Boost members with prior commercial settle success on overlapping capabilities."""
    target = str(member_id or "").strip()
    if not target:
        return 0, []
    needed = {str(x).strip() for x in needed_capabilities if str(x).strip()}
    bonus = 0
    reasons: list[str] = []
    settled_hits = 0
    override_away = 0
    for item in load_routing_feedback(workspace):
        if str(item.get("member_id") or "").strip() != target:
            # count times this member was recommended but overridden away
            if (
                str(item.get("event_type") or "") == "assign_override"
                and str(item.get("recommended_member_id") or "").strip() == target
            ):
                override_away += 1
            continue
        caps = {
            str(x).strip()
            for x in (item.get("needed_capabilities") if isinstance(item.get("needed_capabilities"), list) else [])
            if str(x).strip()
        }
        overlap = needed & caps if needed else caps
        if str(item.get("outcome") or "") == "settled" and (overlap or not needed):
            settled_hits += 1
    if settled_hits:
        bonus += min(12, settled_hits * 4)
        reasons.append(f"历史商业结算成功 ×{settled_hits}")
    if override_away >= 2:
        bonus -= min(6, override_away * 2)
        reasons.append(f"曾被改派跳过 ×{override_away}")
    return bonus, reasons


def journal_routing_score_bonus(
    member: dict,
    *,
    needed_capabilities: list[str],
) -> tuple[int, list[str]]:
    """Boost members whose experience_journal cards overlap needed capabilities."""
    journal = member.get("experience_journal") if isinstance(member.get("experience_journal"), dict) else {}
    cards = [c for c in (journal.get("cards") if isinstance(journal.get("cards"), list) else []) if isinstance(c, dict)]
    if not cards:
        return 0, []
    needed = {str(x).strip() for x in needed_capabilities if str(x).strip()}
    commercial_hits = 0
    learning_hits = 0
    for card in cards[:24]:
        meta = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
        caps = {
            str(x).strip()
            for x in (meta.get("needed_capabilities") if isinstance(meta.get("needed_capabilities"), list) else [])
            if str(x).strip()
        }
        source = str(card.get("source") or "").strip()
        text = f"{card.get('title') or ''} {card.get('summary') or ''} {card.get('current_pattern') or ''}".lower()
        overlap = needed & caps if needed and caps else set()
        soft_hit = bool(needed) and any(cap.lower() in text for cap in needed)
        if source in {"commercial_intake_settle", "commercial_intake"} or str(card.get("signature") or "").startswith("commercial_intake:"):
            if overlap or soft_hit or (not needed and caps):
                commercial_hits += 1
        elif source == "knowledge_learning" or str(card.get("signature") or "").startswith("knowledge_learning:"):
            if overlap or soft_hit or not needed:
                learning_hits += 1
    bonus = 0
    reasons: list[str] = []
    if commercial_hits:
        bonus += min(10, commercial_hits * 3)
        reasons.append(f"经验卡·商业结算 ×{commercial_hits}")
    if learning_hits:
        bonus += min(6, learning_hits * 2)
        reasons.append(f"经验卡·补知识 ×{learning_hits}")
    return bonus, reasons


def _member_capabilities(workspace: Path, member: dict) -> list[str]:
    work_type_id = resolve_work_type_id(member)
    caps: list[str] = []
    if work_type_id:
        work_type = get_work_type(workspace, work_type_id) or {}
        collab = work_type.get("collaboration") if isinstance(work_type.get("collaboration"), dict) else {}
        provide = collab.get("can_provide_capabilities")
        if isinstance(provide, list):
            caps.extend(str(x).strip() for x in provide if str(x).strip())
        intake_cfg = work_type.get("intake") if isinstance(work_type.get("intake"), dict) else {}
        defaults = intake_cfg.get("default_capabilities")
        if isinstance(defaults, list):
            caps.extend(str(x).strip() for x in defaults if str(x).strip())
        capability_type = str(work_type.get("capability_type") or "").strip()
        if capability_type:
            caps.append(capability_type)
        caps.append(work_type_id)
    profile = member.get("content_profile") if isinstance(member.get("content_profile"), dict) else {}
    for key in ("skills", "capabilities"):
        values = profile.get(key)
        if isinstance(values, list):
            caps.extend(str(x).strip() for x in values if str(x).strip())
    # unique preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for cap in caps:
        if cap and cap not in seen:
            seen.add(cap)
            ordered.append(cap)
    return ordered


def _independence_ready(member: dict) -> bool:
    plan = member.get("training_plan") if isinstance(member.get("training_plan"), dict) else {}
    readiness = plan.get("independence_readiness") if isinstance(plan.get("independence_readiness"), dict) else {}
    if readiness.get("ready_for_independence") is True:
        return True
    stage = str(plan.get("stage") or "").strip()
    return stage in {"independent_candidate", "independent", "ready_for_independence"}


def _infer_capabilities_from_text(workspace: Path, text: str) -> list[str]:
    """Lightweight keyword → capability hints via policy aliases only (no platform names)."""
    blob = str(text or "").lower()
    policies = resolve_intake_rule(workspace, needed_capabilities=["*"])
    # Use alias keys from policies file
    from admin.intake_policy_runtime import load_intake_routing_policies

    payload = load_intake_routing_policies(workspace)
    aliases = payload.get("capability_aliases") if isinstance(payload.get("capability_aliases"), dict) else {}
    hits: list[str] = []
    for key in aliases.keys():
        token = str(key or "").strip().lower()
        if token and token in blob:
            hits.append(str(key).strip())
    # generic Chinese commercial verbs → content ops capability family via aliases
    keyword_map = {
        "草稿": "content",
        "发布": "publish",
        "文章": "content",
        "数据": "analytics",
        "分析": "analytics",
        "运营": "content",
        "内容": "content",
    }
    for word, alias_key in keyword_map.items():
        if word in blob and alias_key not in hits:
            hits.append(alias_key)
    return expand_capabilities(workspace, hits) if hits else []


def build_intake_funnel(center: dict | None) -> dict[str, Any]:
    center = normalize_intake_center(center)
    items = center.get("items") if isinstance(center.get("items"), list) else []
    counts = {status: 0 for status in FUNNEL_STATUSES}
    pipeline_value = 0.0
    settled_value = 0.0
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "received")
        if status in counts:
            counts[status] += 1
        amount = _safe_float(item.get("quoted_amount"))
        if amount is None:
            amount = _safe_float(item.get("budget")) or 0.0
        if status in {"received", "analyzing", "assigned", "in_progress", "delivered"}:
            pipeline_value += amount
        if status == "settled":
            settled_value += _safe_float(item.get("settled_amount")) or amount
    return {
        "counts": counts,
        "open_count": sum(counts[s] for s in ("received", "analyzing", "assigned", "in_progress")),
        "pipeline_value": round(pipeline_value, 2),
        "settled_value": round(settled_value, 2),
        "currency": "CNY",
        "item_count": len(items),
    }


def create_intake(
    *,
    workspace: Path,
    runtime: dict,
    title: str,
    description: str = "",
    expected_deliverables: list[str] | None = None,
    needed_capabilities: list[str] | None = None,
    source: str = "outsourcing",
    budget: Any = None,
    quoted_amount: Any = None,
    currency: str = "CNY",
    client_label: str | None = None,
    deadline_at: str | None = None,
    policy_id: str | None = None,
    project_id: str | None = None,
    auto_analyze: bool = True,
) -> dict:
    title_clean = str(title or "").strip()
    if not title_clean:
        raise ValueError("title 必填")
    now_iso = _now()
    intake_id = f"intake:{int(datetime.now().timestamp() * 1000)}"
    caps = [str(x).strip() for x in (needed_capabilities or []) if str(x).strip()]
    if not caps:
        caps = _infer_capabilities_from_text(workspace, f"{title_clean} {description}")
    intake = {
        "intake_id": intake_id,
        "title": title_clean,
        "description": str(description or "").strip() or None,
        "expected_deliverables": [
            str(x).strip() for x in (expected_deliverables or []) if str(x).strip()
        ],
        "needed_capabilities": caps,
        "source": str(source or "outsourcing").strip() or "outsourcing",
        "status": "received",
        "budget": _safe_float(budget),
        "quoted_amount": _safe_float(quoted_amount),
        "settled_amount": None,
        "currency": str(currency or "CNY").strip() or "CNY",
        "client_label": str(client_label or "").strip() or None,
        "deadline_at": deadline_at,
        "policy_id": str(policy_id or "").strip() or None,
        "member_id": None,
        "task_id": None,
        "project_id": str(project_id or "").strip() or None,
        "work_type_id": None,
        "routing": {},
        "fulfillment": {},
        "finance": {},
        "metadata": {},
        "created_at": now_iso,
        "updated_at": now_iso,
        "assigned_at": None,
        "delivered_at": None,
        "settled_at": None,
    }
    center = normalize_intake_center(runtime.get("intake_center"))
    _upsert_intake(center, intake)
    _append_event(center, event_type="intake.created", intake_id=intake_id, payload={"source": intake["source"]})
    runtime["intake_center"] = center
    if auto_analyze:
        return analyze_intake(workspace=workspace, runtime=runtime, intake_id=intake_id)
    return intake


def analyze_intake(*, workspace: Path, runtime: dict, intake_id: str) -> dict:
    center = normalize_intake_center(runtime.get("intake_center"))
    intake = _get_intake(center, intake_id)
    if not isinstance(intake, dict):
        raise ValueError("接单不存在")
    if str(intake.get("status") or "") in {"settled", "cancelled"}:
        raise ValueError(f"当前状态 {intake.get('status')} 不可分析")

    needed = list(intake.get("needed_capabilities") or [])
    resolved = resolve_intake_rule(
        workspace,
        needed_capabilities=needed,
        policy_id=str(intake.get("policy_id") or "").strip() or None,
    )
    rule = resolved.get("rule") if isinstance(resolved.get("rule"), dict) else {}
    expanded = resolved.get("expanded_capabilities") if isinstance(resolved.get("expanded_capabilities"), list) else needed
    prefer_department = str(rule.get("prefer_department_id") or "").strip() or None
    candidate_work_types = {
        str(x).strip()
        for x in (rule.get("candidate_work_type_ids") if isinstance(rule.get("candidate_work_type_ids"), list) else [])
        if str(x).strip()
    }
    require_independent = rule.get("require_independent_ready") is True
    resolve_by = str(rule.get("resolve_by") or "trainer_manual").strip()

    members = normalize_child_members_runtime(
        runtime.get("child_members"),
        legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
    )
    task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
    candidates: list[dict] = []
    expanded_set = set(expanded)

    for member in members.get("items", []):
        if not isinstance(member, dict):
            continue
        member_id = str(member.get("member_id") or "").strip()
        if not member_id or member_id == ORCHESTRATOR_MEMBER_ID:
            continue
        if str(member.get("primary_role") or "").strip() == "talent_development":
            continue
        work_type_id = resolve_work_type_id(member)
        if candidate_work_types and work_type_id not in candidate_work_types:
            continue
        work_type = get_work_type(workspace, work_type_id or "") if work_type_id else None
        organization = member.get("organization") if isinstance(member.get("organization"), dict) else {}
        department_id = str(
            (work_type or {}).get("department_id") or organization.get("department_id") or ""
        ).strip()
        if prefer_department and department_id and department_id != prefer_department:
            # soft preference: score penalty instead of hard skip
            pass
        caps = _member_capabilities(workspace, member)
        overlap = [c for c in caps if c in expanded_set]
        if expanded_set and not overlap and resolve_by != "trainer_manual":
            # still allow if member has any work type when capabilities empty on intake
            if needed:
                continue
        independent = _independence_ready(member)
        if require_independent and not independent:
            continue
        busy = has_open_formal_task(task_center, member_id)
        score = 0
        score += len(overlap) * 10
        if independent:
            score += 5
        if not busy:
            score += 8
        if prefer_department and department_id == prefer_department:
            score += 3
        if work_type_id:
            score += 1
        needed_for_bonus = list(expanded_set) if expanded_set else list(needed)
        feedback_bonus, feedback_reasons = routing_feedback_score_bonus(
            workspace,
            member_id=member_id,
            needed_capabilities=needed_for_bonus,
        )
        journal_bonus, journal_reasons = journal_routing_score_bonus(
            member,
            needed_capabilities=needed_for_bonus,
        )
        score += feedback_bonus
        score += journal_bonus
        reasons = []
        if overlap:
            reasons.append(f"能力匹配：{', '.join(overlap[:4])}")
        if independent:
            reasons.append("已达可独立运营候选")
        if not busy:
            reasons.append("当前无进行中正式任务")
        else:
            reasons.append("已有进行中任务（负载较高）")
        if prefer_department and department_id == prefer_department:
            reasons.append(f"部门偏好命中：{prefer_department}")
        reasons.extend(feedback_reasons)
        reasons.extend(journal_reasons)
        if not reasons:
            reasons.append("可人工改派候选")
        candidates.append({
            "member_id": member_id,
            "name": str(member.get("name") or member_id).strip(),
            "work_type_id": work_type_id,
            "department_id": department_id or None,
            "score": score,
            "capability_overlap": overlap,
            "busy": busy,
            "independent_ready": independent,
            "feedback_bonus": feedback_bonus,
            "journal_bonus": journal_bonus,
            "reasons": reasons,
        })

    candidates.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("member_id") or "")))
    recommended = candidates[0] if candidates else None
    if resolve_by == "round_robin" and candidates:
        # simple rotate: pick least recently assigned among top scorers
        top_score = candidates[0]["score"]
        top = [c for c in candidates if c["score"] == top_score]
        recommended = top[0]

    now_iso = _now()
    intake["status"] = "analyzing"
    intake["needed_capabilities"] = list(expanded) if expanded else list(intake.get("needed_capabilities") or [])
    intake["routing"] = {
        "policy_id": resolved.get("policy_id"),
        "resolve_by": resolve_by,
        "expanded_capabilities": expanded,
        "candidates": candidates[:12],
        "recommended_member_id": recommended.get("member_id") if isinstance(recommended, dict) else None,
        "analyzed_at": now_iso,
    }
    intake["updated_at"] = now_iso
    _upsert_intake(center, intake)
    _append_event(
        center,
        event_type="intake.analyzed",
        intake_id=str(intake.get("intake_id")),
        payload={
            "recommended_member_id": intake["routing"].get("recommended_member_id"),
            "candidate_count": len(candidates),
        },
    )
    runtime["intake_center"] = center
    return intake


def build_fulfillment_plan(
    *,
    workspace: Path,
    member: dict,
    intake: dict,
) -> dict[str, Any]:
    work_type_id = resolve_work_type_id(member)
    worker_id = resolve_primary_worker_id(workspace, member=member, work_type_id=work_type_id)
    manifest = worker_manifest(workspace, worker_id) if worker_id else {}
    task_types = manifest.get("task_types") if isinstance(manifest.get("task_types"), list) else []
    operation_types = [str(t).strip() for t in task_types if str(t).strip().startswith("operation_")]
    rule = resolve_intake_rule(
        workspace,
        needed_capabilities=list(intake.get("needed_capabilities") or []),
        policy_id=str(intake.get("policy_id") or "").strip() or None,
    ).get("rule") or {}
    prefer_prefix = str(rule.get("prefer_operation_prefix") or "operation_").strip() or "operation_"
    primary = next((t for t in operation_types if t.startswith(prefer_prefix)), None)
    if not primary and operation_types:
        primary = operation_types[0]
    return {
        "worker_id": worker_id,
        "work_type_id": work_type_id,
        "has_operation_automation": bool(worker_id and worker_has_operation_tasks(workspace, worker_id)),
        "suggested_operation_types": operation_types,
        "primary_operation_type": primary,
        "deliverable_template_id": str(rule.get("deliverable_template_id") or "").strip() or None,
        "status": "planned" if primary else "manual_only",
    }


def assign_intake(
    *,
    workspace: Path,
    runtime: dict,
    intake_id: str,
    member_id: str,
    assigned_by: str = ORCHESTRATOR_MEMBER_ID,
    override_reason: str | None = None,
    task_queue=None,
    task_priority_normal=None,
    append_relationship_message: Callable[..., None] | None = None,
) -> dict:
    center = normalize_intake_center(runtime.get("intake_center"))
    intake = _get_intake(center, intake_id)
    if not isinstance(intake, dict):
        raise ValueError("接单不存在")
    if str(intake.get("status") or "") not in {"received", "analyzing", "assigned"}:
        raise ValueError(f"当前状态 {intake.get('status')} 不可分派")

    member = _find_member(runtime, member_id)
    if not isinstance(member, dict):
        raise ValueError("目标员工不存在")
    if str(member.get("primary_role") or "").strip() == "talent_development":
        raise ValueError("育成师不能作为接单执行人")

    # ensure routing exists
    if not (intake.get("routing") or {}).get("candidates"):
        analyze_intake(workspace=workspace, runtime=runtime, intake_id=intake_id)
        center = normalize_intake_center(runtime.get("intake_center"))
        intake = _get_intake(center, intake_id) or intake

    fulfillment = build_fulfillment_plan(workspace=workspace, member=member, intake=intake)
    now_iso = _now()
    task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
    task_id = f"task:{member_id}:{int(datetime.now().timestamp() * 1000)}:intake"
    deliverables = list(intake.get("expected_deliverables") or [])
    if not deliverables:
        deliverables = ["按接单需求完成交付物", "提交结果摘要与复盘"]
    work_type_id = fulfillment.get("work_type_id") or resolve_work_type_id(member)
    project_id = str(intake.get("project_id") or "").strip()
    if not project_id:
        work_type = get_work_type(workspace, work_type_id or "") if work_type_id else None
        project_id = str((work_type or {}).get("finance_project_id") or work_type_id or f"intake_{intake_id}").strip()

    job_ids: list[str] = []
    primary_op = str(fulfillment.get("primary_operation_type") or "").strip()
    if task_queue is not None and primary_op and fulfillment.get("has_operation_automation"):
        tenant_id = str(runtime.get("tenant_id") or "default").strip() or "default"
        payload = {
            "topic": str(intake.get("title") or "").strip(),
            "deliverable_goal": str(intake.get("description") or intake.get("title") or "").strip(),
            "goal_hint": str(intake.get("description") or "").strip(),
            "member_id": member_id,
            "intake_id": intake_id,
            "work_type_id": work_type_id,
            "project_id": project_id,
            "_source": "intake_fulfillment",
        }
        try:
            kwargs = {
                "task_type": primary_op,
                "payload": payload,
                "tenant_id": tenant_id,
            }
            if task_priority_normal is not None:
                kwargs["priority"] = task_priority_normal
            created = task_queue.submit(**kwargs)
            job_id = str(getattr(created, "id", None) or getattr(created, "task_id", None) or "").strip()
            if job_id:
                job_ids.append(job_id)
                fulfillment["status"] = "queued"
                fulfillment["queued_at"] = now_iso
        except Exception as exc:  # noqa: BLE001 — keep assign success; surface error in fulfillment
            fulfillment["status"] = "queue_failed"
            fulfillment["queue_error"] = str(exc)

    fulfillment["job_ids"] = job_ids

    task = upsert_task(task_center, {
        "task_id": task_id,
        "member_id": member_id,
        "assigned_by_member_id": str(assigned_by or ORCHESTRATOR_MEMBER_ID).strip() or ORCHESTRATOR_MEMBER_ID,
        "title": str(intake.get("title") or "接单任务").strip(),
        "objective": str(intake.get("description") or intake.get("title") or "").strip(),
        "deliverables": deliverables,
        "status": "assigned",
        "assigned_at": now_iso,
        "started_at": None,
        "submitted_at": None,
        "approved_at": None,
        "result_summary": None,
        "reflection": None,
        "review_note": None,
        "metadata": {
            "source": "commercial_intake",
            "intake_id": intake_id,
            "needed_capabilities": list(intake.get("needed_capabilities") or []),
            "work_type_id": work_type_id,
            "project_id": project_id,
            "fulfillment": fulfillment,
            "job_ids": job_ids,
            "commercial": {
                "budget": intake.get("budget"),
                "quoted_amount": intake.get("quoted_amount"),
                "currency": intake.get("currency"),
                "client_label": intake.get("client_label"),
            },
        },
    })
    runtime["task_center"] = task_center

    intake["status"] = "assigned"
    intake["member_id"] = member_id
    intake["task_id"] = task_id
    intake["work_type_id"] = work_type_id
    intake["project_id"] = project_id
    intake["fulfillment"] = fulfillment
    intake["assigned_at"] = now_iso
    intake["updated_at"] = now_iso
    routing = intake.get("routing") if isinstance(intake.get("routing"), dict) else {}
    recommended_id = str(routing.get("recommended_member_id") or "").strip() or None
    is_override = bool(recommended_id and recommended_id != member_id)
    reason = str(override_reason or "").strip() or None
    if is_override and not reason:
        reason = "trainer_manual_override"
    routing["assigned_member_id"] = member_id
    routing["assigned_by"] = str(assigned_by or ORCHESTRATOR_MEMBER_ID)
    routing["is_override"] = is_override
    routing["override_reason"] = reason if is_override else None
    routing["assigned_at"] = now_iso
    intake["routing"] = routing
    _upsert_intake(center, intake)
    _append_event(
        center,
        event_type="intake.assigned",
        intake_id=intake_id,
        payload={
            "member_id": member_id,
            "task_id": task_id,
            "job_ids": job_ids,
            "is_override": is_override,
            "override_reason": reason if is_override else None,
            "recommended_member_id": recommended_id,
        },
    )
    if is_override:
        append_routing_feedback(
            workspace,
            {
                "event_type": "assign_override",
                "intake_id": intake_id,
                "member_id": member_id,
                "recommended_member_id": recommended_id,
                "needed_capabilities": list(intake.get("needed_capabilities") or []),
                "override_reason": reason,
                "outcome": "assigned_override",
                "created_at": now_iso,
            },
        )
    runtime["intake_center"] = center

    if append_relationship_message is not None:
        relationship_center = runtime.get("relationship_center") if isinstance(runtime.get("relationship_center"), dict) else {}
        append_relationship_message(
            relationship_center,
            thread_id=f"trainer:{member_id}",
            participants=[ORCHESTRATOR_MEMBER_ID, member_id],
            sender_member_id=ORCHESTRATOR_MEMBER_ID,
            sender_role="talent_development",
            message_type="intake_assignment",
            content=(
                f"商业接单已分派给你：{intake.get('title')}。"
                f"请按交付要求完成并提交结果与复盘。"
            ),
            metadata={
                "intake_id": intake_id,
                "task_id": task_id,
                "job_ids": job_ids,
            },
        )
        runtime["relationship_center"] = relationship_center

    return {"intake": intake, "task": task, "fulfillment": fulfillment}


def list_intakes(
    runtime: dict,
    *,
    status: str | None = None,
    member_id: str | None = None,
) -> list[dict]:
    center = normalize_intake_center(runtime.get("intake_center"))
    items = center.get("items") if isinstance(center.get("items"), list) else []
    status_filter = str(status or "").strip()
    member_filter = str(member_id or "").strip()
    results: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if status_filter and str(item.get("status") or "") != status_filter:
            continue
        if member_filter and str(item.get("member_id") or "") != member_filter:
            continue
        results.append(item)
    results.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return results


_ARTIFACT_PATH_KEYS = (
    "draft_path",
    "article_path",
    "output_path",
    "artifact_path",
    "report_path",
    "local_path",
    "file_path",
)


def extract_operation_artifacts(operation_result: dict | None, *, job_id: str | None = None) -> list[dict]:
    """Pull file-like artifacts from worker results without platform brand branches."""
    if not isinstance(operation_result, dict):
        return []
    found: list[dict] = []
    seen: set[str] = set()

    def _push(kind: str, path: str, *, label: str | None = None, meta: dict | None = None) -> None:
        normalized = str(path or "").strip()
        if not normalized or normalized in seen:
            return
        # accept absolute/relative filesystem paths or repo-relative export paths
        if len(normalized) < 2:
            return
        seen.add(normalized)
        found.append({
            "kind": kind,
            "path": normalized,
            "label": label or kind,
            "job_id": job_id,
            "exists": Path(normalized).is_file() if ("/" in normalized or normalized.endswith((".md", ".json", ".txt", ".html"))) else None,
            "meta": meta or {},
        })

    nested = operation_result.get("result") if isinstance(operation_result.get("result"), dict) else {}
    bags = [operation_result, nested]
    for bag in bags:
        if not isinstance(bag, dict):
            continue
        for key in _ARTIFACT_PATH_KEYS:
            value = bag.get(key)
            if isinstance(value, str) and value.strip():
                _push(key.replace("_path", ""), value, label=key)
        files = bag.get("files")
        if isinstance(files, list):
            for item in files:
                if isinstance(item, str) and item.strip():
                    _push("file", item)
                elif isinstance(item, dict):
                    path = str(item.get("path") or item.get("file_path") or item.get("draft_path") or "").strip()
                    if path:
                        _push(str(item.get("kind") or "file"), path, label=str(item.get("label") or "") or None, meta=item)

    git_export = operation_result.get("git_export") if isinstance(operation_result.get("git_export"), dict) else {}
    for item in (git_export.get("files") if isinstance(git_export.get("files"), list) else []):
        if isinstance(item, str) and item.strip():
            _push("git_export", item, label="git_export")
        elif isinstance(item, dict):
            path = str(item.get("file_path") or item.get("path") or "").strip()
            if path:
                _push("git_export", path, label="git_export")

    summary = str(
        operation_result.get("insight_summary")
        or operation_result.get("message")
        or nested.get("message")
        or ""
    ).strip()
    if summary and not found:
        found.append({
            "kind": "summary",
            "path": "",
            "label": "insight_summary",
            "job_id": job_id,
            "exists": None,
            "meta": {"text": summary[:500]},
        })
    return found[:20]


def attach_operation_artifacts_to_intake(
    *,
    workspace: Path,
    runtime: dict,
    queue_task: Any,
    operation_result: dict,
) -> dict | None:
    """When an operation_* job finishes, mirror artifacts onto intake + formal task for workspace UI."""
    payload = getattr(queue_task, "payload", None)
    if not isinstance(payload, dict):
        payload = operation_result.get("payload") if isinstance(operation_result.get("payload"), dict) else {}
    if not isinstance(payload, dict):
        return None
    if str(payload.get("_source") or "").strip() != "intake_fulfillment":
        # still allow if intake_id present (manual re-run)
        if not str(payload.get("intake_id") or "").strip():
            return None

    intake_id = str(payload.get("intake_id") or "").strip()
    if not intake_id:
        return None

    job_id = str(getattr(queue_task, "id", None) or getattr(queue_task, "task_id", None) or "").strip() or None
    task_type = str(getattr(queue_task, "type", None) or operation_result.get("task_type") or "").strip() or None
    artifacts = extract_operation_artifacts(operation_result, job_id=job_id)
    now_iso = _now()

    center = normalize_intake_center(runtime.get("intake_center"))
    intake = _get_intake(center, intake_id)
    if not isinstance(intake, dict):
        return None

    fulfillment = intake.get("fulfillment") if isinstance(intake.get("fulfillment"), dict) else {}
    existing = fulfillment.get("artifacts") if isinstance(fulfillment.get("artifacts"), list) else []
    merged_paths = {str(item.get("path") or "").strip() for item in existing if isinstance(item, dict)}
    next_artifacts = [item for item in existing if isinstance(item, dict)]
    for item in artifacts:
        path_key = str(item.get("path") or "").strip()
        if path_key and path_key in merged_paths:
            continue
        if path_key:
            merged_paths.add(path_key)
        next_artifacts.append({**item, "attached_at": now_iso, "operation_type": task_type})
    fulfillment["artifacts"] = next_artifacts[-30:]
    fulfillment["last_artifact_at"] = now_iso
    fulfillment["last_operation_type"] = task_type
    fulfillment["last_job_id"] = job_id
    if str(fulfillment.get("status") or "") in {"planned", "queued", "queue_failed", "manual_only", ""}:
        fulfillment["status"] = "artifacts_ready" if any(str(a.get("path") or "") for a in next_artifacts) else "operation_done"
    intake["fulfillment"] = fulfillment
    intake["updated_at"] = now_iso
    if str(intake.get("status") or "") == "assigned":
        intake["status"] = "in_progress"
    _upsert_intake(center, intake)
    _append_event(
        center,
        event_type="intake.fulfillment_artifacts",
        intake_id=intake_id,
        payload={"job_id": job_id, "operation_type": task_type, "artifact_count": len(artifacts)},
    )
    runtime["intake_center"] = center

    # Mirror onto formal task metadata for employee workspace
    formal_task_id = str(intake.get("task_id") or "").strip()
    task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
    formal_task = None
    if formal_task_id:
        for item in (task_center.get("items") if isinstance(task_center.get("items"), list) else []):
            if isinstance(item, dict) and str(item.get("task_id") or "").strip() == formal_task_id:
                formal_task = item
                break
    if isinstance(formal_task, dict):
        meta = formal_task.get("metadata") if isinstance(formal_task.get("metadata"), dict) else {}
        meta_fulfillment = meta.get("fulfillment") if isinstance(meta.get("fulfillment"), dict) else {}
        meta_fulfillment.update({
            "artifacts": fulfillment.get("artifacts"),
            "status": fulfillment.get("status"),
            "last_artifact_at": now_iso,
            "last_operation_type": task_type,
            "last_job_id": job_id,
        })
        meta["fulfillment"] = meta_fulfillment
        meta["job_ids"] = list(dict.fromkeys([
            *(meta.get("job_ids") if isinstance(meta.get("job_ids"), list) else []),
            *([job_id] if job_id else []),
        ]))
        # Prefer path labels in result_summary hint when empty
        path_hints = [str(a.get("path") or "").strip() for a in artifacts if str(a.get("path") or "").strip()]
        if path_hints and not str(formal_task.get("result_summary") or "").strip():
            formal_task["result_summary"] = f"履约产物已回挂：{', '.join(path_hints[:3])}"
        formal_task["metadata"] = meta
        formal_task["updated_at"] = now_iso
        upsert_task(task_center, formal_task)
        runtime["task_center"] = task_center

    return {
        "intake_id": intake_id,
        "job_id": job_id,
        "operation_type": task_type,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "fulfillment_status": fulfillment.get("status"),
    }


def mark_intake_in_progress_from_task(*, runtime: dict, task: dict) -> dict | None:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    intake_id = str(metadata.get("intake_id") or "").strip()
    if not intake_id:
        return None
    center = normalize_intake_center(runtime.get("intake_center"))
    intake = _get_intake(center, intake_id)
    if not isinstance(intake, dict):
        return None
    if str(intake.get("status") or "") not in {"assigned", "analyzing"}:
        return intake
    now_iso = _now()
    intake["status"] = "in_progress"
    intake["updated_at"] = now_iso
    if task.get("result_summary"):
        meta = intake.get("metadata") if isinstance(intake.get("metadata"), dict) else {}
        meta["last_result_summary"] = task.get("result_summary")
        meta["last_reflection"] = task.get("reflection")
        intake["metadata"] = meta
    _upsert_intake(center, intake)
    _append_event(center, event_type="intake.in_progress", intake_id=intake_id, payload={"task_id": task.get("task_id")})
    runtime["intake_center"] = center
    return intake


def mark_intake_delivered_from_task(*, runtime: dict, task: dict) -> dict | None:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    intake_id = str(metadata.get("intake_id") or "").strip()
    if not intake_id:
        return None
    center = normalize_intake_center(runtime.get("intake_center"))
    intake = _get_intake(center, intake_id)
    if not isinstance(intake, dict):
        return None
    if str(intake.get("status") or "") in {"settled", "cancelled", "delivered"}:
        return intake
    now_iso = _now()
    intake["status"] = "delivered"
    intake["delivered_at"] = now_iso
    intake["updated_at"] = now_iso
    _upsert_intake(center, intake)
    _append_event(center, event_type="intake.delivered", intake_id=intake_id, payload={"task_id": task.get("task_id")})
    runtime["intake_center"] = center
    return intake


def apply_supply_growth_from_commercial_intake(
    *,
    runtime: dict,
    intake: dict,
    settled_amount: float | None = None,
) -> dict | None:
    """消费环结算后回写供给环：员工经验 / 成长状态 + 育成带教履历。"""
    member_id = str(intake.get("member_id") or "").strip()
    if not member_id:
        return None
    member = _find_member(runtime, member_id)
    if not isinstance(member, dict):
        return None

    now_iso = _now()
    amount = settled_amount if settled_amount is not None else _safe_float(intake.get("settled_amount"))
    currency = str(intake.get("currency") or "CNY").strip() or "CNY"
    title = str(intake.get("title") or "商业接单").strip()
    intake_id = str(intake.get("intake_id") or "").strip()
    caps = [
        str(x).strip()
        for x in (intake.get("needed_capabilities") if isinstance(intake.get("needed_capabilities"), list) else [])
        if str(x).strip()
    ]

    growth = member.get("growth_state") if isinstance(member.get("growth_state"), dict) else {}
    commercial_count = int(growth.get("commercial_settled_count") or 0) + 1
    commercial_revenue = (_safe_float(growth.get("commercial_settled_revenue")) or 0.0) + (amount or 0.0)
    member["growth_state"] = {
        **growth,
        "current_focus": f"沉淀商业交付：{title}",
        "next_goal": "把本单有效动作固化为可复用岗位方法，准备下一单",
        "last_reflection_at": now_iso,
        "last_commercial_settled_at": now_iso,
        "commercial_settled_count": commercial_count,
        "commercial_settled_revenue": round(commercial_revenue, 2),
        "last_commercial_intake_id": intake_id or None,
    }

    training = member.get("training_plan") if isinstance(member.get("training_plan"), dict) else {}
    stage = str(training.get("stage") or "").strip()
    if stage in {"", "onboarding", "first_task_assigned", "awaiting_first_task"}:
        stage = "commercial_delivery_done"
    elif stage == "first_reflection_done":
        stage = "commercial_delivery_done"
    member["training_plan"] = {
        **training,
        "stage": stage or "commercial_delivery_done",
        "next_action": "复盘本单商业方法并评估是否扩权接更大单",
        "last_commercial_loop_at": now_iso,
    }

    journal = member.get("experience_journal") if isinstance(member.get("experience_journal"), dict) else {}
    cards = journal.get("cards") if isinstance(journal.get("cards"), list) else []
    signature = f"commercial_intake:{intake_id}"
    card = {
        "card_id": f"exp:commercial:{intake_id}:{int(datetime.now().timestamp() * 1000)}",
        "signature": signature,
        "title": f"商业交付结算 · {title}",
        "summary": (
            f"接单已结算 {amount if amount is not None else '—'} {currency}。"
            f"能力：{', '.join(caps[:4]) or '未标注'}。"
        ),
        "reflections": [
            f"intake_id={intake_id}",
            f"project_id={intake.get('project_id') or ''}",
            "loop=consumption_to_supply",
        ],
        "source": "commercial_intake_settle",
        "updated_at": now_iso,
        "metadata": {
            "intake_id": intake_id,
            "settled_amount": amount,
            "currency": currency,
            "needed_capabilities": caps,
        },
    }
    next_cards = [card] + [
        item for item in cards
        if isinstance(item, dict) and str(item.get("signature") or "") != signature
    ]
    member["experience_journal"] = {
        "last_compiled_at": now_iso,
        "latest_card_id": card["card_id"],
        "cards": next_cards[:24],
    }

    members = normalize_child_members_runtime(
        runtime.get("child_members"),
        legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
    )
    items = members.get("items") if isinstance(members.get("items"), list) else []
    next_items: list[dict] = []
    for item in items:
        if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id:
            next_items.append(member)
        else:
            next_items.append(item)
    members["items"] = next_items
    runtime["child_members"] = members

    from admin.trainer_coaching_runtime import record_commercial_intake_settled_coaching

    record_commercial_intake_settled_coaching(
        runtime,
        coached_member=member,
        intake=intake,
        settled_amount=amount,
    )
    return member


def settle_intake(
    *,
    workspace: Path,
    runtime: dict,
    intake_id: str,
    settled_amount: Any = None,
    cost: Any = None,
    note: str | None = None,
) -> dict:
    from admin.finance_runtime import upsert_finance_period

    center = normalize_intake_center(runtime.get("intake_center"))
    intake = _get_intake(center, intake_id)
    if not isinstance(intake, dict):
        raise ValueError("接单不存在")
    prior_status = str(intake.get("status") or "")
    if prior_status not in {"delivered", "in_progress", "assigned", "settled"}:
        raise ValueError(f"当前状态 {intake.get('status')} 不可结算")
    already_settled = prior_status == "settled"

    amount = _safe_float(settled_amount)
    if amount is None:
        amount = _safe_float(intake.get("quoted_amount"))
    if amount is None:
        amount = _safe_float(intake.get("budget"))
    if amount is None:
        amount = 0.0

    project_id = str(intake.get("project_id") or "").strip()
    if not project_id:
        project_id = f"intake_{str(intake.get('intake_id') or 'unknown').replace(':', '_')}"

    # channel is a finance store label only; use generic commercial, never a platform brand
    summary = upsert_finance_period(
        workspace,
        project_id=project_id,
        channel="commercial",
        patch={
            "revenue": amount,
            "cost": _safe_float(cost),
            "source": f"intake_settle:{intake_id}",
            "headline": str(note or intake.get("title") or "接单结算").strip(),
            "intake_id": intake_id,
            "member_id": intake.get("member_id"),
        },
    )
    now_iso = _now()
    intake["status"] = "settled"
    intake["settled_amount"] = amount
    intake["settled_at"] = now_iso
    intake["updated_at"] = now_iso
    intake["project_id"] = project_id
    intake["finance"] = {
        "project_id": project_id,
        "summary": summary,
        "settled_at": now_iso,
    }
    _upsert_intake(center, intake)
    _append_event(
        center,
        event_type="intake.settled",
        intake_id=intake_id,
        payload={"amount": amount, "project_id": project_id},
    )
    runtime["intake_center"] = center
    growth_member = None
    if not already_settled:
        growth_member = apply_supply_growth_from_commercial_intake(
            runtime=runtime,
            intake=intake,
            settled_amount=amount,
        )
        # Commercial settle success → routing feedback flywheel (boost next analyze)
        append_routing_feedback(
            workspace,
            {
                "event_type": "settle_success",
                "intake_id": intake_id,
                "member_id": intake.get("member_id"),
                "recommended_member_id": (
                    (intake.get("routing") or {}).get("recommended_member_id")
                    if isinstance(intake.get("routing"), dict)
                    else None
                ),
                "needed_capabilities": list(intake.get("needed_capabilities") or []),
                "override_reason": (
                    (intake.get("routing") or {}).get("override_reason")
                    if isinstance(intake.get("routing"), dict)
                    else None
                ),
                "outcome": "settled",
                "settled_amount": amount,
                "created_at": now_iso,
            },
        )
        git_export = None
        if isinstance(growth_member, dict):
            from admin.local_git_export_runtime import export_commercial_intake_experience_locally

            tenant_id = str(runtime.get("tenant_id") or "default").strip() or "default"
            try:
                git_export = export_commercial_intake_experience_locally(
                    workspace,
                    tenant_id=tenant_id,
                    member=growth_member,
                    intake=intake,
                    settled_amount=amount,
                )
            except Exception as exc:
                git_export = {
                    "status": "failed",
                    "reason": str(exc)[:240],
                    "next_action": "检查 .admin/local_git_exports 写权限后重试结算导出",
                }
            growth = growth_member.get("growth_state") if isinstance(growth_member.get("growth_state"), dict) else {}
            exported_ok = str((git_export or {}).get("status") or "") in {"local_exported", "exported", "local_only"}
            growth_member["growth_state"] = {
                **growth,
                "pending_git_export": not exported_ok,
                "pending_git_export_reason": None if exported_ok else "commercial_intake_settled",
                "last_git_export_at": now_iso if exported_ok else growth.get("last_git_export_at"),
                "last_git_export_status": (git_export or {}).get("status"),
                "last_git_export_path": (git_export or {}).get("file_path"),
                "last_git_export_root": (git_export or {}).get("local_root"),
            }
            # re-upsert member after export flags
            members = normalize_child_members_runtime(
                runtime.get("child_members"),
                legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
            )
            mid = str(growth_member.get("member_id") or "").strip()
            next_items = []
            for item in (members.get("items") if isinstance(members.get("items"), list) else []):
                if isinstance(item, dict) and str(item.get("member_id") or "").strip() == mid:
                    next_items.append(growth_member)
                else:
                    next_items.append(item)
            members["items"] = next_items
            runtime["child_members"] = members
            intake["git_export"] = {
                "status": (git_export or {}).get("status"),
                "file_path": (git_export or {}).get("file_path"),
                "local_root": (git_export or {}).get("local_root"),
                "exported_at": now_iso,
            }
            _upsert_intake(center, intake)
            runtime["intake_center"] = center
    return {
        "intake": intake,
        "finance": summary,
        "growth_member_id": str((growth_member or {}).get("member_id") or "").strip() or None,
        "git_export": intake.get("git_export") if isinstance(intake.get("git_export"), dict) else None,
    }


def cancel_intake(*, runtime: dict, intake_id: str, reason: str | None = None) -> dict:
    center = normalize_intake_center(runtime.get("intake_center"))
    intake = _get_intake(center, intake_id)
    if not isinstance(intake, dict):
        raise ValueError("接单不存在")
    if str(intake.get("status") or "") == "settled":
        raise ValueError("已结算订单不可取消")
    now_iso = _now()
    intake["status"] = "cancelled"
    intake["updated_at"] = now_iso
    meta = intake.get("metadata") if isinstance(intake.get("metadata"), dict) else {}
    meta["cancel_reason"] = str(reason or "").strip() or None
    intake["metadata"] = meta
    _upsert_intake(center, intake)
    _append_event(center, event_type="intake.cancelled", intake_id=intake_id, payload={"reason": reason})
    runtime["intake_center"] = center
    return intake


def list_available_capabilities(workspace: Path) -> list[dict]:
    """Capability catalog derived from work_types config (not hardcoded brands)."""
    payload = load_work_types(workspace)
    items = payload.get("items") if isinstance(payload, dict) else []
    catalog: dict[str, dict] = {}
    for work_type in items if isinstance(items, list) else []:
        if not isinstance(work_type, dict):
            continue
        work_type_id = str(work_type.get("work_type_id") or "").strip()
        collab = work_type.get("collaboration") if isinstance(work_type.get("collaboration"), dict) else {}
        provide = collab.get("can_provide_capabilities") if isinstance(collab.get("can_provide_capabilities"), list) else []
        intake_cfg = work_type.get("intake") if isinstance(work_type.get("intake"), dict) else {}
        defaults = intake_cfg.get("default_capabilities") if isinstance(intake_cfg.get("default_capabilities"), list) else []
        for cap in [*provide, *defaults]:
            key = str(cap or "").strip()
            if not key:
                continue
            entry = catalog.setdefault(key, {"capability": key, "work_type_ids": []})
            if work_type_id and work_type_id not in entry["work_type_ids"]:
                entry["work_type_ids"].append(work_type_id)
    return sorted(catalog.values(), key=lambda item: str(item.get("capability") or ""))
