"""
策略自治决策规则：升级候选生成与自动采纳。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from core.tenant import TenantManager


def build_strategy_upgrade_candidate(
    item: dict,
    run: dict,
    *,
    safe_float: Callable[[object, float], float],
) -> dict | None:
    summary = run.get("summary", {}) if isinstance(run.get("summary"), dict) else {}
    if summary.get("status") != "improved":
        return None

    strategy_id = item.get("strategy_id", "unknown")
    score_delta = safe_float(summary.get("score_delta"), 0.0)
    improved_count = int(summary.get("improved_count", 0) or 0)
    review_count = int(summary.get("review", 0) or 0)
    failed_count = int(summary.get("failed", 0) or 0)

    rationale = [
        f"本轮实验相对基线提升 {score_delta:.2f}",
        f"正向样本 {improved_count} 个，review {review_count} 个，failed {failed_count} 个",
        "实验结果说明该策略有进入下一阶段固化的价值",
    ]
    actions = [
        "将当前实验结论整理为策略升级候选说明",
        "补一轮更广样本验证，确认不是偶发收益",
        "若下一轮仍为正向，则进入正式策略固化或默认加权",
    ]
    risk_checks = [
        "检查是否只在单一输入类型上提升",
        "确认没有隐藏失败样本或边界条件退化",
        "确认租户插件策略不会影响升级后的稳定性",
    ]

    return {
        "generated_at": datetime.now().isoformat(),
        "title": f"{strategy_id} 升级候选",
        "summary": f"{strategy_id} 在最近实验中呈现正向收益，建议进入升级候选池。",
        "rationale": rationale,
        "proposed_actions": actions,
        "risk_checks": risk_checks,
        "decision": "pending",
        "decision_note": "等待人工确认是否采纳、继续观察或拒绝",
    }


def maybe_auto_accept_upgrade_candidate(
    workspace: Path,
    tenant_id: str,
    item: dict,
    *,
    safe_float: Callable[[object, float], float],
    record_growth_event: Callable[..., object],
    build_review_item_signature: Callable[[dict], dict],
) -> bool:
    candidate = item.get("upgrade_candidate")
    runs = item.get("experiment_runs")
    if not isinstance(candidate, dict) or not isinstance(runs, list):
        return False
    if candidate.get("decision") != "pending":
        return False

    completed_runs = [
        run for run in runs
        if isinstance(run, dict)
        and isinstance(run.get("summary"), dict)
        and run["summary"].get("status") == "improved"
        and safe_float(run["summary"].get("score_delta"), 0.0) >= 0.1
    ]
    latest_run = completed_runs[0] if completed_runs else None
    latest_summary = latest_run.get("summary", {}) if isinstance(latest_run, dict) and isinstance(latest_run.get("summary"), dict) else {}
    strong_single_run = bool(
        latest_summary
        and int(latest_summary.get("sample_count_actual", 0) or 0) >= 3
        and int(latest_summary.get("improved_count", 0) or 0) >= 2
        and int(latest_summary.get("review", 0) or 0) == 0
        and int(latest_summary.get("failed", 0) or 0) == 0
        and safe_float(latest_summary.get("avg_score"), 0.0) >= 0.85
        and safe_float(latest_summary.get("score_delta"), 0.0) >= 0.15
    )
    if len(completed_runs) < 2 and not strong_single_run:
        return False

    tenant_manager = TenantManager(workspace)
    decided_at = datetime.now().isoformat()
    strategy_id = item.get("strategy_id")
    if strategy_id:
        tenant_manager.set_strategy_override(
            tenant_id,
            strategy_id,
            weight_delta=2.5,
            preferred=True,
            blocked=False,
            source="auto_upgrade_accept",
            note="Auto accepted after repeated improved experiments",
            updated_at=decided_at,
            expires_at=(datetime.now() + timedelta(days=14)).isoformat(),
        )

    candidate["decision"] = "auto_accept"
    candidate["decision_note"] = (
        "系统检测到连续正向实验，已自动采纳并提升运行时权重"
        if len(completed_runs) >= 2
        else "系统检测到单轮强正向实验，已自动采纳并提升运行时权重"
    )
    candidate["decided_at"] = decided_at
    item["status"] = "promotion_auto_accepted"
    item["upgrade_candidate"] = candidate
    if strategy_id:
        record_growth_event(
            workspace,
            tenant_id,
            strategy_id=strategy_id,
            event_type="auto_accept",
            summary=f"{strategy_id} auto accepted after repeated improved experiments",
            quality_score=0.9,
            task_type="strategy_governance",
            domain="evolution",
            signature=build_review_item_signature(item),
            metadata={
                "decision": "auto_accept",
                "source": "growth_loop",
                "note": candidate["decision_note"],
            },
        )
    return True
