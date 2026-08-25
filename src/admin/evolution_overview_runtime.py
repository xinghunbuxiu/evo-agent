"""
演化总览相关运行时：
负责平台共享种子、知识层建议、override 风险与成长时间线。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from core import ExperienceStore
from core.tenant import TenantManager


def create_evolution_overview_runtime_bindings(
    *,
    list_platform_strategy_promotions: Callable[[Path, int], list[dict]],
    record_growth_event: Callable[..., object],
    find_review_item_signature: Callable[[Path, str, str | None], dict | None],
    safe_float: Callable[[object, float], float],
    task_evaluation_score: Callable,
):
    def platform_shared_seed_recommendations(
        workspace: Path,
        tenant_id: str,
        tenant_manager: TenantManager,
        limit: int = 5,
    ) -> dict:
        promotions = list_platform_strategy_promotions(workspace, limit=50)
        store = ExperienceStore(workspace, tenant_id)
        local_growth_events = store.load_by_task("evolution", "growth_event", limit=10)
        local_replay_validations = store.load_by_task("evolution", "replay_validation", limit=10)
        local_js_experiences = store.load_by_domain("javascript", limit=10)
        current_overrides = tenant_manager.get_strategy_overrides(tenant_id)

        recommended: list[dict] = []
        for item in promotions:
            strategy_id = str(item.get("strategy_id") or "")
            if not strategy_id:
                continue
            if strategy_id in current_overrides:
                continue

            score = 0.6
            reasons = ["来自平台共享层的已验证升级候选"]
            if item.get("decision") in {"accept", "auto_accept"}:
                score += 0.25
                reasons.append("平台样本已通过 accept/auto_accept")
            if strategy_id.startswith("builtin.javascript"):
                score += 0.2
                reasons.append("与当前 JS 主线能力直接相关")
            if not local_js_experiences:
                score += 0.15
                reasons.append("当前租户还缺少 javascript 本地经验，可用于冷启动")
            if not local_growth_events and not local_replay_validations:
                score += 0.1
                reasons.append("当前租户还没有成长闭环样本")

            recommended.append({
                "strategy_id": strategy_id,
                "title": item.get("title") or strategy_id,
                "summary": item.get("summary") or "平台共享层推荐策略",
                "promoted_at": item.get("promoted_at"),
                "source_tenant_id": item.get("tenant_id"),
                "source_path": item.get("path"),
                "decision": item.get("decision"),
                "share_mode": item.get("share_mode"),
                "score": round(min(score, 1.0), 3),
                "reasons": reasons,
                "recommended_override": {
                    "weight_delta": 0.8 if strategy_id.startswith("builtin.javascript") else 0.45,
                    "preferred": strategy_id.startswith("builtin.javascript"),
                    "blocked": False,
                    "source": "platform_shared_seed",
                    "note": f"Seeded from platform shared layer for tenant {tenant_id}",
                },
            })

        recommended.sort(key=lambda item: item["score"], reverse=True)
        return {
            "tenant_id": tenant_id,
            "is_cold_start": not local_js_experiences and not local_growth_events and not local_replay_validations,
            "current_override_count": len(current_overrides),
            "items": recommended[:limit],
        }

    def apply_platform_shared_seeds(
        workspace: Path,
        tenant_id: str,
        tenant_manager: TenantManager,
        strategy_ids: list[str] | None = None,
    ) -> dict:
        recommendations = platform_shared_seed_recommendations(
            workspace=workspace,
            tenant_id=tenant_id,
            tenant_manager=tenant_manager,
            limit=20,
        )
        candidates = recommendations.get("items", [])
        wanted = set(strategy_ids or [])
        selected = [item for item in candidates if not wanted or item.get("strategy_id") in wanted]

        applied: list[dict] = []
        for item in selected:
            strategy_id = str(item.get("strategy_id") or "")
            override = item.get("recommended_override", {})
            tenant_manager.set_strategy_override(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                weight_delta=float(override.get("weight_delta", 0.0) or 0.0),
                preferred=bool(override.get("preferred", False)),
                blocked=False,
                source=str(override.get("source") or "platform_shared_seed"),
                note=str(override.get("note") or ""),
                updated_at=datetime.now().isoformat(),
            )
            applied.append({
                "strategy_id": strategy_id,
                "weight_delta": override.get("weight_delta", 0.0),
                "preferred": bool(override.get("preferred", False)),
                "source_tenant_id": item.get("source_tenant_id"),
            })
            record_growth_event(
                workspace,
                tenant_id,
                strategy_id=strategy_id,
                event_type="platform_seed_applied",
                summary=f"{strategy_id} seeded from platform shared layer",
                quality_score=0.72,
                task_type="strategy_governance",
                domain="evolution",
                signature=find_review_item_signature(workspace, tenant_id, strategy_id),
                metadata={
                    "source_tenant_id": item.get("source_tenant_id"),
                    "seed_score": item.get("score"),
                    "source_path": item.get("source_path"),
                },
            )

        return {
            "tenant_id": tenant_id,
            "applied": applied,
            "count": len(applied),
            "strategy_overrides": tenant_manager.get_strategy_overrides(tenant_id),
        }

    def get_platform_promotion_status(
        tenant_manager: TenantManager,
        tenant_id: str,
        policy_override: dict | None = None,
    ) -> dict:
        policy = policy_override if isinstance(policy_override, dict) else tenant_manager.get_knowledge_policy(tenant_id)
        share_mode = policy.get("share_mode", "private_only")
        allow_platform_promotion = bool(policy.get("allow_platform_promotion", False))
        review_required = bool(policy.get("review_required", True))
        allowed = share_mode != "private_only" and allow_platform_promotion
        reason = (
            "effective policy is private_only"
            if share_mode == "private_only"
            else "platform promotion disabled by effective policy"
            if not allow_platform_promotion
            else "promotion allowed"
        )
        return {
            "allowed": allowed,
            "share_mode": share_mode,
            "allow_platform_promotion": allow_platform_promotion,
            "review_required": review_required,
            "reason": reason,
            "source": policy.get("source"),
        }

    def build_knowledge_layer_advice(
        *,
        knowledge_policy: dict | None,
        platform_promotion_status: dict | None,
        recent_experiences: list[dict],
        strategy_review_queue: list[dict],
        platform_shared_promotions: list[dict],
        summary: dict | None,
        review_cases: list[dict],
    ) -> dict:
        knowledge_policy = knowledge_policy if isinstance(knowledge_policy, dict) else {}
        platform_promotion_status = platform_promotion_status if isinstance(platform_promotion_status, dict) else {}
        summary = summary if isinstance(summary, dict) else {}
        share_mode = str(knowledge_policy.get("share_mode") or "private_only")
        allow_platform_promotion = bool(knowledge_policy.get("allow_platform_promotion", False))
        review_required = bool(knowledge_policy.get("review_required", True))
        experience_total = int(summary.get("experiences_total") or 0)
        review_total = len(strategy_review_queue)
        promotion_total = len(platform_shared_promotions)
        failure_total = len(review_cases)
        avg_score = summary.get("avg_evaluation_score")
        has_positive_signal = isinstance(avg_score, (int, float)) and avg_score >= 0.75
        has_review_backlog = review_total > 0 or failure_total > 0
        can_promote = bool(platform_promotion_status.get("allowed"))

        if promotion_total > 0:
            overall_stage = "platform_shared"
            overall_status = "shared"
            headline = "已有稳定经验进入平台共享层"
        elif has_review_backlog:
            overall_stage = "project_review"
            overall_status = "reviewing"
            headline = "当前更适合先走项目复盘和实验"
        else:
            overall_stage = "private_growth"
            overall_status = "growing"
            headline = "当前以租户私有成长为主"

        if can_promote and not has_review_backlog and experience_total > 0 and has_positive_signal:
            recommended_next_layer = "platform_shared"
            recommendation_reason = "经验分数稳定且当前没有明显复盘阻塞，可以考虑进入平台共享层。"
        elif review_total > 0 or failure_total > 0:
            recommended_next_layer = "project_review"
            recommendation_reason = "存在待复盘策略或失败样本，先在项目层完成实验和校验更稳妥。"
        else:
            recommended_next_layer = "private_growth"
            recommendation_reason = "当前经验还需要继续在私有层积累，避免过早共享污染系统。"

        next_actions: list[str] = []
        if recommended_next_layer == "platform_shared":
            next_actions.append("优先挑选最近稳定通过的经验或策略，进入共享候选。")
            if review_required:
                next_actions.append("保持 review 门禁，先完成复盘记录再上报平台共享层。")
        elif recommended_next_layer == "project_review":
            next_actions.append("先把失败样本和低收益策略放入 review/experiment 队列。")
            next_actions.append("等待实验结果稳定后，再决定是否升级或共享。")
        else:
            next_actions.append("继续在当前租户私有层积累同类案例，先提升命中率和稳定性。")
            if not allow_platform_promotion:
                next_actions.append("如果后续希望共享，可再打开 allow_platform_promotion。")

        return {
            "headline": headline,
            "overall_stage": overall_stage,
            "overall_status": overall_status,
            "recommended_next_layer": recommended_next_layer,
            "recommendation_reason": recommendation_reason,
            "share_mode": share_mode,
            "allow_platform_promotion": allow_platform_promotion,
            "review_required": review_required,
            "counts": {
                "private_experiences": experience_total,
                "review_queue": review_total,
                "platform_shared": promotion_total,
                "review_cases": failure_total,
            },
            "layers": [
                {
                    "key": "private_growth",
                    "label": "Private Growth",
                    "count": experience_total,
                    "status": "active" if experience_total > 0 else "empty",
                    "reason": "租户自己的经验、重放和失败样本先沉淀在私有层。",
                    "next_action": "继续积累同类案例并提高稳定性。",
                },
                {
                    "key": "project_review",
                    "label": "Project Review",
                    "count": review_total,
                    "status": "active" if has_review_backlog else "idle",
                    "reason": "项目层负责复盘、实验、升级候选和共享前校验。",
                    "next_action": "把待处理策略推进到 draft、experiment 和 decision。",
                },
                {
                    "key": "platform_shared",
                    "label": "Platform Shared",
                    "count": promotion_total,
                    "status": "active" if promotion_total > 0 else "gated" if not can_promote else "ready",
                    "reason": platform_promotion_status.get("reason") or "平台共享层只接收经过验证的经验。",
                    "next_action": "只有稳定样本才上报，避免污染平台共享层。",
                },
            ],
            "next_actions": next_actions,
            "recent_candidate_ids": [
                str(item.get("id") or item.get("strategy_id") or "")
                for item in strategy_review_queue[:3]
                if item.get("id") or item.get("strategy_id")
            ],
            "recent_experience_ids": [
                str(item.get("id") or "")
                for item in recent_experiences[:3]
                if item.get("id")
            ],
        }

    def summarize_override_effects(tasks: list, strategy_overrides: dict) -> tuple[dict, list[dict]]:
        stats: dict[str, dict] = {}
        events: list[dict] = []

        for task in tasks:
            result = task.result or {}
            if not isinstance(result, dict):
                continue
            feedback = result.get("feedback", {})
            if not isinstance(feedback, dict):
                continue
            decision = feedback.get("decision", {})
            if not isinstance(decision, dict):
                continue
            strategy = decision.get("strategy", {})
            if not isinstance(strategy, dict):
                continue
            runtime_adjustments = strategy.get("runtime_adjustments", {})
            if not isinstance(runtime_adjustments, dict) or not runtime_adjustments.get("override_active"):
                continue

            strategy_id = strategy.get("strategy_id")
            if not strategy_id:
                continue
            evaluation = feedback.get("evaluation", {})
            verdict = evaluation.get("verdict") if isinstance(evaluation, dict) else None
            score = task_evaluation_score(task)

            current = stats.setdefault(strategy_id, {
                "hits": 0,
                "success": 0,
                "review": 0,
                "failed": 0,
                "avg_eval": None,
                "last_hit_at": None,
                "source": runtime_adjustments.get("source"),
                "weight_delta": runtime_adjustments.get("weight_delta"),
                "preferred": runtime_adjustments.get("preferred"),
                "expires_at": runtime_adjustments.get("expires_at"),
                "_score_total": 0.0,
                "_score_count": 0,
            })
            current["hits"] = int(current["hits"]) + 1
            current["last_hit_at"] = task.created_at

            if task.status.value == "failed":
                current["failed"] = int(current["failed"]) + 1
            elif verdict == "review":
                current["review"] = int(current["review"]) + 1
            elif task.status.value == "success":
                current["success"] = int(current["success"]) + 1

            if score is not None:
                current["_score_total"] = safe_float(current["_score_total"]) + score
                current["_score_count"] = int(current["_score_count"]) + 1

        for strategy_id, item in stats.items():
            score_count = int(item.pop("_score_count", 0))
            score_total = safe_float(item.pop("_score_total", 0.0))
            item["avg_eval"] = round(score_total / score_count, 3) if score_count else None
            hits = int(item["hits"])
            review_ratio = round(int(item["review"]) / hits, 3) if hits else 0.0
            item["review_ratio"] = review_ratio
            item["status"] = (
                "risky"
                if hits >= 3 and (
                    int(item["failed"]) > 0
                    or review_ratio >= 0.67
                    or (safe_float(item["avg_eval"], 1.0) < 0.55)
                )
                else "healthy"
            )

            override = strategy_overrides.get(strategy_id, {})
            source = override.get("source") if isinstance(override, dict) else item.get("source")
            if item["status"] == "risky" and source in {"upgrade_candidate_accept", "upgrade_candidate_observe"}:
                events.append({
                    "strategy_id": strategy_id,
                    "reason": (
                        "override 命中后出现 failed 样本"
                        if int(item["failed"]) > 0
                        else "override 命中后 review 比例过高"
                        if review_ratio >= 0.67
                        else "override 命中后平均评估分过低"
                    ),
                    "hits": hits,
                    "review_ratio": review_ratio,
                    "avg_eval": item["avg_eval"],
                    "source": source,
                })

        return stats, events

    def auto_rollback_risky_overrides(
        workspace: Path,
        tenant_id: str,
        tenant_manager: TenantManager,
        events: list[dict],
    ) -> list[dict]:
        applied_events: list[dict] = []
        for event in events:
            strategy_id = event.get("strategy_id")
            if not strategy_id:
                continue
            tenant_manager.clear_strategy_override(tenant_id, strategy_id)
            record_growth_event(
                workspace,
                tenant_id,
                strategy_id=strategy_id,
                event_type="auto_rollback",
                summary=f"{strategy_id} override rolled back automatically",
                quality_score=0.1,
                task_type="strategy_governance",
                domain="evolution",
                metadata={
                    "decision": "auto_rollback",
                    "source": event.get("source"),
                    "note": event.get("reason"),
                },
            )
            applied_events.append({
                **event,
                "rolled_back_at": datetime.now().isoformat(),
                "action": "auto_rollback",
            })
        return applied_events

    def build_growth_timeline(
        strategy_review_queue: list[dict],
        auto_rollback_events: list[dict],
        growth_events: list[dict],
    ) -> list[dict]:
        timeline: list[dict] = []

        for item in strategy_review_queue:
            strategy_id = item.get("strategy_id")
            created_at = item.get("created_at")
            if strategy_id and created_at:
                timeline.append({
                    "timestamp": created_at,
                    "strategy_id": strategy_id,
                    "event_type": "review_enqueued",
                    "title": "进入复盘队列",
                    "detail": item.get("alert_reason") or item.get("reason") or "待复盘",
                })

            if item.get("draft_generated_at"):
                timeline.append({
                    "timestamp": item.get("draft_generated_at"),
                    "strategy_id": strategy_id,
                    "event_type": "draft_generated",
                    "title": "生成优化草案",
                    "detail": item.get("draft", {}).get("summary") if isinstance(item.get("draft"), dict) else "",
                })

            if item.get("experiment_generated_at"):
                timeline.append({
                    "timestamp": item.get("experiment_generated_at"),
                    "strategy_id": strategy_id,
                    "event_type": "experiment_planned",
                    "title": "生成实验计划",
                    "detail": item.get("experiment_plan", {}).get("title") if isinstance(item.get("experiment_plan"), dict) else "",
                })

            runs = item.get("experiment_runs")
            if isinstance(runs, list):
                for run in runs:
                    if not isinstance(run, dict):
                        continue
                    summary = run.get("summary", {}) if isinstance(run.get("summary"), dict) else {}
                    timeline.append({
                        "timestamp": run.get("created_at"),
                        "strategy_id": strategy_id,
                        "event_type": "experiment_run",
                        "title": "执行实验批次",
                        "detail": f"{summary.get('status', 'running')} | delta {summary.get('score_delta', '--')}",
                    })

            candidate = item.get("upgrade_candidate")
            if isinstance(candidate, dict):
                timeline.append({
                    "timestamp": candidate.get("generated_at"),
                    "strategy_id": strategy_id,
                    "event_type": "upgrade_candidate",
                    "title": "生成升级候选",
                    "detail": candidate.get("summary"),
                })
                if candidate.get("decided_at"):
                    decision = candidate.get("decision")
                    timeline.append({
                        "timestamp": candidate.get("decided_at"),
                        "strategy_id": strategy_id,
                        "event_type": "upgrade_decision",
                        "title": "升级候选决策",
                        "detail": f"{decision} | {candidate.get('decision_note', '')}",
                    })

        for event in auto_rollback_events:
            timeline.append({
                "timestamp": event.get("rolled_back_at"),
                "strategy_id": event.get("strategy_id"),
                "event_type": "auto_rollback",
                "title": "自动回滚 override",
                "detail": event.get("reason"),
            })

        growth_titles = {
            "observation_stable": "观察确认稳定",
            "observation_improved": "观察发现增益",
            "observation_regressed": "观察发现退化",
            "platform_promoted": "进入平台共享层",
            "platform_seed_applied": "注入平台共享经验",
            "auto_accept": "自动采纳升级候选",
        }
        for event in growth_events:
            if not isinstance(event, dict):
                continue
            timestamp = event.get("created_at")
            if not timestamp:
                continue
            event_type = str(event.get("event_type") or "")
            detail = event.get("output_summary") or event.get("task_type") or "--"
            timeline.append({
                "timestamp": timestamp,
                "strategy_id": event.get("strategy_id"),
                "event_type": event_type,
                "title": growth_titles.get(event_type, event_type or "成长事件"),
                "detail": detail,
            })

        timeline = [item for item in timeline if item.get("timestamp")]
        timeline.sort(key=lambda item: item["timestamp"], reverse=True)
        return timeline[:30]

    return {
        "platform_shared_seed_recommendations": platform_shared_seed_recommendations,
        "apply_platform_shared_seeds": apply_platform_shared_seeds,
        "get_platform_promotion_status": get_platform_promotion_status,
        "build_knowledge_layer_advice": build_knowledge_layer_advice,
        "summarize_override_effects": summarize_override_effects,
        "auto_rollback_risky_overrides": auto_rollback_risky_overrides,
        "build_growth_timeline": build_growth_timeline,
    }
