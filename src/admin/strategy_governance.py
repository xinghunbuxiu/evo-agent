"""
策略升级候选治理：决策与回滚。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from core.tenant import TenantManager


def update_upgrade_candidate_decision(
    workspace: Path,
    tenant_id: str,
    review_id: str,
    decision: str,
    *,
    load_review_queue: Callable[[Path, str], list[dict]],
    save_review_queue: Callable[[Path, str, list[dict]], None],
    record_growth_event: Callable[..., object],
    build_review_item_signature: Callable[[dict], dict],
) -> dict | None:
    tenant_manager = TenantManager(workspace)
    items = load_review_queue(workspace, tenant_id)
    target = next((item for item in items if item.get("id") == review_id), None)
    if not target:
        return None

    candidate = target.get("upgrade_candidate")
    if not isinstance(candidate, dict):
        return None

    decided_at = datetime.now().isoformat()
    strategy_id = target.get("strategy_id")
    if decision == "accept":
        target["status"] = "promotion_accepted"
        note = "已采纳升级候选，运行时已提升该策略权重并标记为 preferred"
        if strategy_id:
            tenant_manager.set_strategy_override(
                tenant_id,
                strategy_id,
                weight_delta=2.0,
                preferred=True,
                blocked=False,
                source="upgrade_candidate_accept",
                note="Accepted from evolution upgrade candidate",
                updated_at=decided_at,
                expires_at=(datetime.now() + timedelta(days=14)).isoformat(),
            )
    elif decision == "observe":
        target["status"] = "promotion_observing"
        note = "继续观察升级候选，运行时给予轻量加权，等待更多实验样本"
        if strategy_id:
            tenant_manager.set_strategy_override(
                tenant_id,
                strategy_id,
                weight_delta=0.5,
                preferred=False,
                blocked=False,
                source="upgrade_candidate_observe",
                note="Observed from evolution upgrade candidate",
                updated_at=decided_at,
                expires_at=(datetime.now() + timedelta(days=7)).isoformat(),
            )
    elif decision == "reject":
        target["status"] = "promotion_rejected"
        note = "当前不采纳该升级候选，已撤销运行时加权，后续需要重新验证"
        if strategy_id:
            tenant_manager.clear_strategy_override(tenant_id, strategy_id)
    else:
        raise ValueError("unsupported decision")

    candidate["decision"] = decision
    candidate["decision_note"] = note
    candidate["decided_at"] = decided_at
    target["upgrade_candidate"] = candidate
    save_review_queue(workspace, tenant_id, items)
    if strategy_id:
        quality_score = 0.85 if decision == "accept" else 0.65 if decision == "observe" else 0.25
        record_growth_event(
            workspace,
            tenant_id,
            strategy_id=strategy_id,
            event_type=f"manual_{decision}",
            summary=f"{strategy_id} {decision} by operator",
            quality_score=quality_score,
            task_type="strategy_governance",
            domain="evolution",
            signature=build_review_item_signature(target),
            metadata={
                "decision": decision,
                "source": "operator",
                "note": note,
            },
        )
    return target


def rollback_strategy_override(
    workspace: Path,
    tenant_id: str,
    strategy_id: str,
    *,
    record_growth_event: Callable[..., object],
) -> dict:
    tenant_manager = TenantManager(workspace)
    tenant_manager.clear_strategy_override(tenant_id, strategy_id)
    record_growth_event(
        workspace,
        tenant_id,
        strategy_id=strategy_id,
        event_type="manual_rollback",
        summary=f"{strategy_id} override rolled back manually",
        quality_score=0.2,
        task_type="strategy_governance",
        domain="evolution",
        metadata={
            "decision": "rollback",
            "source": "operator",
            "note": "Manual override rollback",
        },
    )
    return tenant_manager.get_strategy_overrides(tenant_id)
