"""
策略复盘编排层：入队、自动准备、平台共享。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from core.tenant import TenantManager


def promote_review_entry_to_platform(
    workspace: Path,
    tenant_id: str,
    review_entry: dict,
    tenant_manager: TenantManager,
    *,
    get_platform_promotion_status: Callable[..., dict],
    get_platform_shared_root: Callable[[Path], Path],
    record_growth_event: Callable[..., object],
    build_review_item_signature: Callable[[dict], dict],
) -> dict:
    effective_policy = (
        review_entry.get("effective_growth_policy")
        if isinstance(review_entry.get("effective_growth_policy"), dict)
        else None
    )
    status = get_platform_promotion_status(
        tenant_manager,
        tenant_id,
        policy_override=effective_policy,
    )
    if not status["allowed"]:
        raise PermissionError(status["reason"])

    candidate = review_entry.get("upgrade_candidate")
    if not isinstance(candidate, dict):
        raise ValueError("当前复盘项还没有升级候选")

    if status["review_required"] and candidate.get("decision") not in {"accept", "auto_accept"}:
        raise ValueError("当前租户要求共享前先审核，升级候选尚未被 accept")

    root = get_platform_shared_root(workspace) / "strategy_promotions"
    root.mkdir(parents=True, exist_ok=True)

    strategy_id = str(review_entry.get("strategy_id") or "unknown")
    promoted_at = datetime.now().isoformat()
    file_path = root / f"{tenant_id}_{strategy_id.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    payload = {
        "tenant_id": tenant_id,
        "strategy_id": strategy_id,
        "promoted_at": promoted_at,
        "knowledge_policy": tenant_manager.get_knowledge_policy(tenant_id),
        "effective_growth_policy": effective_policy or tenant_manager.get_knowledge_policy(tenant_id),
        "review_entry": review_entry,
    }
    file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    review_entry["platform_promotion"] = {
        "status": "promoted",
        "promoted_at": promoted_at,
        "path": str(file_path),
    }
    record_growth_event(
        workspace,
        tenant_id,
        strategy_id=strategy_id,
        event_type="platform_promoted",
        summary=f"{strategy_id} promoted to platform shared layer",
        quality_score=0.88,
        task_type="strategy_governance",
        domain="evolution",
        signature=build_review_item_signature(review_entry),
        metadata={
            "path": str(file_path),
            "share_mode": status["share_mode"],
            "review_required": status["review_required"],
        },
    )
    return review_entry


def enqueue_strategy_review(
    workspace: Path,
    tenant_id: str,
    strategy_id: str,
    payload: dict,
    *,
    load_review_queue: Callable[[Path, str], list[dict]],
    save_review_queue: Callable[[Path, str, list[dict]], None],
) -> dict:
    items = load_review_queue(workspace, tenant_id)
    existing = next((item for item in items if item.get("strategy_id") == strategy_id and item.get("status") != "done"), None)
    if existing:
        return existing

    entry = {
        "id": f"review_{strategy_id.replace('.', '_')}",
        "strategy_id": strategy_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "reason": payload.get("reason", "strategy_alert"),
        "alert_reason": payload.get("alert_reason"),
        "count": payload.get("count"),
        "review_ratio": payload.get("review_ratio"),
        "avg_eval": payload.get("avg_eval"),
        "total_gain": payload.get("total_gain"),
        "notes": payload.get("notes", ""),
    }
    items.insert(0, entry)
    save_review_queue(workspace, tenant_id, items[:100])
    return entry


def auto_enqueue_review_cases(
    workspace: Path,
    tenant_id: str,
    review_events: list[dict],
    *,
    enqueue_strategy_review_fn: Callable[..., dict],
) -> list[dict]:
    auto_categories = {"strategy_gap", "capability_gap", "plugin_policy_gap"}
    queued: list[dict] = []
    seen_review_ids: set[str] = set()

    for event in review_events:
        if not isinstance(event, dict):
            continue
        strategy_id = event.get("strategy_id")
        category = event.get("issue_category")
        if not strategy_id or category not in auto_categories:
            continue

        notes_parts = [
            event.get("summary") or "",
            *(event.get("issue_hints") or []),
            *(event.get("recommended_actions") or [])[:2],
        ]
        notes = " | ".join(part for part in notes_parts if part)
        entry = enqueue_strategy_review_fn(
            workspace=workspace,
            tenant_id=tenant_id,
            strategy_id=strategy_id,
            payload={
                "reason": "auto_review_case",
                "alert_reason": category,
                "avg_eval": event.get("evaluation_score"),
                "notes": notes,
                "source_task_id": event.get("task_id"),
                "task_type": event.get("task_type"),
            },
        )
        entry_id = str(entry.get("id") or "")
        if entry and entry_id and entry_id not in seen_review_ids:
            seen_review_ids.add(entry_id)
            queued.append(entry)

    return queued


def auto_prepare_review_entries(
    workspace: Path,
    tenant_id: str,
    entries: list[dict],
    *,
    generate_review_draft_fn: Callable[[Path, str, str], dict | None],
    generate_review_experiment_plan_fn: Callable[[Path, str, str], dict | None],
) -> list[dict]:
    prepared: list[dict] = []
    seen_review_ids: set[str] = set()

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        review_id = str(entry.get("id") or "")
        if not review_id or review_id in seen_review_ids:
            continue
        seen_review_ids.add(review_id)

        current = entry
        if current.get("reason") != "auto_review_case":
            continue
        if not isinstance(current.get("draft"), dict):
            generated = generate_review_draft_fn(workspace, tenant_id, review_id)
            if isinstance(generated, dict):
                current = generated
        if isinstance(current.get("draft"), dict) and not isinstance(current.get("experiment_plan"), dict):
            generated = generate_review_experiment_plan_fn(workspace, tenant_id, review_id)
            if isinstance(generated, dict):
                current = generated
        prepared.append(current)

    return prepared


def auto_promote_review_entries(
    workspace: Path,
    tenant_id: str,
    tenant_manager: TenantManager,
    *,
    load_review_queue: Callable[[Path, str], list[dict]],
    save_review_queue: Callable[[Path, str, list[dict]], None],
    promote_review_entry_to_platform_fn: Callable[[Path, str, dict, TenantManager], dict],
) -> list[dict]:
    items = load_review_queue(workspace, tenant_id)
    promoted: list[dict] = []
    changed = False

    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = item.get("upgrade_candidate") if isinstance(item.get("upgrade_candidate"), dict) else None
        platform_promotion = item.get("platform_promotion") if isinstance(item.get("platform_promotion"), dict) else None
        if not isinstance(candidate, dict) or platform_promotion:
            continue
        if candidate.get("decision") not in {"accept", "auto_accept"}:
            continue
        try:
            promote_review_entry_to_platform_fn(workspace, tenant_id, item, tenant_manager)
        except (PermissionError, ValueError):
            continue
        promoted.append(item)
        changed = True

    if changed:
        save_review_queue(workspace, tenant_id, items[:100])
    return promoted
