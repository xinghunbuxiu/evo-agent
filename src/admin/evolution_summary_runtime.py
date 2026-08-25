"""
演化总览聚合运行时：
负责把任务、经验、复盘、共享与成长事件聚合成统一 overview。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from core import ExperienceStore
from core.tenant import TenantManager


def create_evolution_summary_runtime_bindings(
    *,
    safe_float: Callable[[object, float], float],
    classify_review_case: Callable[..., tuple[str, list[str]]],
    recommend_actions: Callable[..., list[str]],
    auto_enqueue_review_cases: Callable[..., list[dict]],
    auto_prepare_review_entries: Callable[..., list[dict]],
    summarize_override_effects: Callable[[list, dict], tuple[dict, list[dict]]],
    auto_rollback_risky_overrides: Callable[..., list[dict]],
    refresh_review_queue_experiment_runs: Callable[[Path, str, object], list[dict]],
    build_growth_timeline: Callable[[list[dict], list[dict], list[dict]], list[dict]],
    build_knowledge_layer_advice: Callable[..., dict],
    get_platform_promotion_status: Callable[..., dict],
    list_platform_strategy_promotions: Callable[[Path, int], list[dict]],
    build_operation_experience_timeline: Callable[[list], list[dict]],
):
    def build_evolution_overview(
        workspace: Path,
        tenant_id: str,
        task_queue,
        plugin_summary,
        tenant_manager: TenantManager,
    ) -> dict:
        tasks = task_queue.list_tasks(tenant_id=tenant_id, limit=200)
        experiences_root = workspace / ".tenants" / tenant_id / "experiences"
        store = ExperienceStore(workspace, tenant_id)

        domains = sorted([item.name for item in experiences_root.iterdir() if item.is_dir()]) if experiences_root.is_dir() else []
        experiences = []
        for domain in domains:
            experiences.extend(store.load_by_domain(domain, limit=60))
        experiences.sort(key=lambda item: item.created_at, reverse=True)

        decision_events = []
        review_events = []
        review_category_counts: dict[str, int] = {}
        capability_counts: dict[str, int] = {}
        strategy_counts: dict[str, int] = {}
        strategy_health_stats: dict[str, dict[str, float | int]] = {}
        verdict_counts: dict[str, int] = {}
        score_total = 0.0
        score_count = 0

        for task in tasks:
            result = task.result or {}
            feedback = result.get("feedback", {}) if isinstance(result, dict) else {}
            decision = feedback.get("decision", {}) if isinstance(feedback, dict) else {}
            evaluation = feedback.get("evaluation", {}) if isinstance(feedback, dict) else {}
            strategy = decision.get("strategy", {}) if isinstance(decision, dict) else {}
            candidate_scores = decision.get("scores", []) if isinstance(decision, dict) else []

            capability_id = decision.get("selected_capability_id")
            strategy_id = strategy.get("strategy_id")
            verdict = evaluation.get("verdict")
            score = evaluation.get("score")
            replay_of = (task.payload or {}).get("_replay_of")

            if capability_id:
                capability_counts[capability_id] = capability_counts.get(capability_id, 0) + 1
            if strategy_id:
                strategy_counts[strategy_id] = strategy_counts.get(strategy_id, 0) + 1
                health = strategy_health_stats.setdefault(
                    strategy_id,
                    {"count": 0, "review_count": 0, "total_eval": 0.0},
                )
                health["count"] = int(health["count"]) + 1
            if verdict:
                verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
                if strategy_id and verdict == "review":
                    health = strategy_health_stats.setdefault(
                        strategy_id,
                        {"count": 0, "review_count": 0, "total_eval": 0.0},
                    )
                    health["review_count"] = int(health["review_count"]) + 1
            if score is not None:
                score_total += safe_float(score)
                score_count += 1
                if strategy_id:
                    health = strategy_health_stats.setdefault(
                        strategy_id,
                        {"count": 0, "review_count": 0, "total_eval": 0.0},
                    )
                    health["total_eval"] = safe_float(health["total_eval"]) + safe_float(score)

            if decision or evaluation:
                event = {
                    "task_id": task.id,
                    "tenant_id": task.tenant_id,
                    "task_type": task.type,
                    "status": task.status.value,
                    "created_at": task.created_at,
                    "capability_id": capability_id,
                    "strategy_id": strategy_id,
                    "strategy_score": safe_float(strategy.get("score")) if strategy else None,
                    "strategy_reasons": strategy.get("reasons", []) if isinstance(strategy, dict) else [],
                    "strategy_runtime_adjustments": strategy.get("runtime_adjustments", {}) if isinstance(strategy, dict) else {},
                    "evaluation_score": safe_float(score) if score is not None else None,
                    "evaluation_verdict": verdict,
                    "evaluation_reasons": evaluation.get("reasons", []) if isinstance(evaluation, dict) else [],
                    "evaluation_metrics": evaluation.get("metrics", {}) if isinstance(evaluation, dict) else {},
                    "history_size": feedback.get("history_size"),
                    "summary": result.get("summary"),
                    "candidate_scores": [
                        {
                            "capability_id": item.get("capability_id"),
                            "score": safe_float(item.get("score")),
                            "reasons": item.get("reasons", []),
                        }
                        for item in candidate_scores
                        if isinstance(item, dict)
                    ],
                    "error": task.error,
                    "replay_of": replay_of,
                }
                decision_events.append(event)
                if task.status.value == "failed" or verdict == "review":
                    category, category_hints = classify_review_case(
                        status=task.status.value,
                        error=task.error,
                        verdict=verdict,
                        evaluation_reasons=event["evaluation_reasons"],
                        evaluation_metrics=event["evaluation_metrics"],
                        candidate_scores=event["candidate_scores"],
                        capability_id=capability_id,
                        strategy_id=strategy_id,
                        plugin_policy=tenant_manager.get_plugin_policy(tenant_id),
                    )
                    event["issue_category"] = category
                    event["issue_hints"] = category_hints
                    event["recommended_actions"] = recommend_actions(
                        category=category,
                        task_type=task.type,
                        capability_id=capability_id,
                        strategy_id=strategy_id,
                        plugin_policy=tenant_manager.get_plugin_policy(tenant_id),
                    )
                    review_category_counts[category] = review_category_counts.get(category, 0) + 1
                    review_events.append(event)
            elif task.status.value == "failed":
                category, category_hints = classify_review_case(
                    status=task.status.value,
                    error=task.error,
                    verdict=None,
                    evaluation_reasons=[],
                    evaluation_metrics={},
                    candidate_scores=[],
                    capability_id=None,
                    strategy_id=None,
                    plugin_policy=tenant_manager.get_plugin_policy(tenant_id),
                )
                review_category_counts[category] = review_category_counts.get(category, 0) + 1
                review_events.append({
                    "task_id": task.id,
                    "tenant_id": task.tenant_id,
                    "task_type": task.type,
                    "status": task.status.value,
                    "created_at": task.created_at,
                    "capability_id": None,
                    "strategy_id": None,
                    "strategy_score": None,
                    "strategy_reasons": [],
                    "evaluation_score": None,
                    "evaluation_verdict": None,
                    "evaluation_reasons": [],
                    "evaluation_metrics": {},
                    "history_size": None,
                    "summary": result.get("summary") if isinstance(result, dict) else None,
                    "candidate_scores": [],
                    "error": task.error,
                    "replay_of": replay_of,
                    "issue_category": category,
                    "issue_hints": category_hints,
                    "recommended_actions": recommend_actions(
                        category=category,
                        task_type=task.type,
                        capability_id=None,
                        strategy_id=None,
                        plugin_policy=tenant_manager.get_plugin_policy(tenant_id),
                    ),
                })

        recent_experiences = []
        recent_role_reflections = []
        replay_validations = []
        positive_strategy_stats: dict[str, dict[str, float | int]] = {}
        for exp in experiences[:12]:
            metadata = exp.metadata if isinstance(exp.metadata, dict) else {}
            strategy = metadata.get("strategy", {}) if isinstance(metadata.get("strategy"), dict) else {}
            evaluation = metadata.get("evaluation", {}) if isinstance(metadata.get("evaluation"), dict) else {}
            professional_experience = metadata.get("professional_experience", {}) if isinstance(metadata.get("professional_experience"), dict) else {}
            reflection_card = professional_experience.get("card", {}) if isinstance(professional_experience.get("card"), dict) else {}
            recent_experiences.append({
                "id": exp.id,
                "domain": exp.domain,
                "task_type": exp.task_type,
                "quality_score": exp.quality_score,
                "created_at": exp.created_at,
                "strategy_id": strategy.get("strategy_id"),
                "evaluation_verdict": evaluation.get("verdict"),
                "evaluation_score": safe_float(evaluation.get("score")) if evaluation else None,
                "output_summary": exp.output_summary,
                "experience_kind": "role_reflection" if professional_experience else "execution",
                "member_id": professional_experience.get("member_id"),
                "member_name": professional_experience.get("member_name"),
                "primary_role": professional_experience.get("primary_role"),
                "stage": reflection_card.get("stage"),
                "status": reflection_card.get("status"),
            })
            if professional_experience:
                recent_role_reflections.append({
                    "id": exp.id,
                    "created_at": exp.created_at,
                    "member_id": professional_experience.get("member_id"),
                    "member_name": professional_experience.get("member_name"),
                    "primary_role": professional_experience.get("primary_role"),
                    "domain": exp.domain,
                    "quality_score": exp.quality_score,
                    "summary": exp.output_summary,
                    "stage": reflection_card.get("stage"),
                    "status": reflection_card.get("status"),
                    "next_experiment": reflection_card.get("next_experiment"),
                })

        evolution_store = ExperienceStore(workspace, tenant_id)
        for exp in evolution_store.load_by_task("evolution", "replay_validation", limit=8):
            metadata = exp.metadata if isinstance(exp.metadata, dict) else {}
            comparison = metadata.get("comparison", {}) if isinstance(metadata.get("comparison"), dict) else {}
            diff = comparison.get("diff", {}) if isinstance(comparison.get("diff"), dict) else {}
            replay_snapshot = comparison.get("replay", {}) if isinstance(comparison.get("replay"), dict) else {}
            strategy_id = replay_snapshot.get("strategy_id") or "unknown"
            score_delta = safe_float(diff.get("score_delta"), 0.0)

            current = positive_strategy_stats.setdefault(
                strategy_id,
                {"count": 0, "total_gain": 0.0},
            )
            current["count"] = int(current["count"]) + 1
            current["total_gain"] = safe_float(current["total_gain"]) + score_delta
            replay_validations.append({
                "id": exp.id,
                "created_at": exp.created_at,
                "quality_score": exp.quality_score,
                "output_summary": exp.output_summary,
                "original_task_id": metadata.get("source_tasks", {}).get("original"),
                "replay_task_id": metadata.get("source_tasks", {}).get("replay"),
                "score_delta": diff.get("score_delta"),
                "outcome": diff.get("outcome"),
                "strategy_id": strategy_id,
                "signatures": metadata.get("signatures") if isinstance(metadata.get("signatures"), dict) else None,
            })

        positive_strategies = []
        for strategy_id, stats in positive_strategy_stats.items():
            count = int(stats["count"])
            total_gain = round(safe_float(stats["total_gain"]), 3)
            avg_gain = round(total_gain / count, 3) if count else 0.0
            positive_strategies.append({
                "strategy_id": strategy_id,
                "count": count,
                "total_gain": total_gain,
                "avg_gain": avg_gain,
            })
        positive_strategies.sort(key=lambda item: (item["avg_gain"], item["count"]), reverse=True)

        strategy_alerts = []
        for strategy_id, stats in strategy_health_stats.items():
            count = int(stats["count"])
            review_count = int(stats["review_count"])
            total_eval = safe_float(stats["total_eval"])
            avg_eval = round(total_eval / count, 3) if count else 0.0
            review_ratio = round(review_count / count, 3) if count else 0.0
            total_gain = safe_float(positive_strategy_stats.get(strategy_id, {}).get("total_gain"), 0.0)

            if count >= 2 and (review_ratio >= 0.5 or avg_eval < 0.7 or total_gain <= 0.0):
                strategy_alerts.append({
                    "strategy_id": strategy_id,
                    "count": count,
                    "review_ratio": review_ratio,
                    "avg_eval": avg_eval,
                    "total_gain": round(total_gain, 3),
                    "alert_reason": (
                        "review 比例偏高" if review_ratio >= 0.5
                        else "平均评估分偏低" if avg_eval < 0.7
                        else "暂无正向增益"
                    ),
                })
        strategy_alerts.sort(key=lambda item: (item["review_ratio"], -item["avg_eval"]), reverse=True)

        top_capabilities = [
            {"id": key, "count": value}
            for key, value in sorted(capability_counts.items(), key=lambda item: item[1], reverse=True)[:6]
        ]
        top_strategies = [
            {"id": key, "count": value}
            for key, value in sorted(strategy_counts.items(), key=lambda item: item[1], reverse=True)[:8]
        ]

        auto_review_entries = auto_enqueue_review_cases(workspace, tenant_id, review_events)
        auto_review_entries = auto_prepare_review_entries(workspace, tenant_id, auto_review_entries)
        enabled_plugins = tenant_manager.get_plugin_policy(tenant_id)
        strategy_overrides = tenant_manager.get_strategy_overrides(tenant_id)
        override_stats, risky_override_events = summarize_override_effects(tasks, strategy_overrides)
        auto_rollback_events = auto_rollback_risky_overrides(workspace, tenant_id, tenant_manager, risky_override_events)
        if auto_rollback_events:
            strategy_overrides = tenant_manager.get_strategy_overrides(tenant_id)
            override_stats, _ = summarize_override_effects(tasks, strategy_overrides)
        loaded_plugins = [item.plugin_name for item in plugin_summary.loaded]
        loaded_capability_types = sorted({
            capability_type
            for item in plugin_summary.loaded
            for capability_type in item.capability_types
        })
        strategy_review_queue = refresh_review_queue_experiment_runs(workspace, tenant_id, task_queue)
        if auto_review_entries:
            auto_review_ids = {str(item.get("id") or "") for item in auto_review_entries if isinstance(item, dict)}
            auto_review_entries = [
                item for item in strategy_review_queue
                if isinstance(item, dict) and str(item.get("id") or "") in auto_review_ids
            ]
        growth_events = [
            {
                "id": exp.id,
                "created_at": exp.created_at,
                "quality_score": exp.quality_score,
                "output_summary": exp.output_summary,
                "strategy_id": (
                    exp.metadata.get("growth_event", {}).get("strategy_id")
                    if isinstance(exp.metadata, dict)
                    else None
                ),
                "event_type": (
                    exp.metadata.get("growth_event", {}).get("event_type")
                    if isinstance(exp.metadata, dict)
                    else None
                ),
                "task_type": (
                    exp.metadata.get("growth_event", {}).get("task_type")
                    if isinstance(exp.metadata, dict)
                    else None
                ),
                "domain": (
                    exp.metadata.get("growth_event", {}).get("domain")
                    if isinstance(exp.metadata, dict)
                    else None
                ),
                "member_id": (
                    exp.metadata.get("growth_event", {}).get("member_id")
                    if isinstance(exp.metadata, dict)
                    else None
                ),
                "member_name": (
                    exp.metadata.get("growth_event", {}).get("member_name")
                    if isinstance(exp.metadata, dict)
                    else None
                ),
                "primary_role": (
                    exp.metadata.get("growth_event", {}).get("primary_role")
                    if isinstance(exp.metadata, dict)
                    else None
                ),
                "mission_run_id": (
                    exp.metadata.get("growth_event", {}).get("mission_run_id")
                    if isinstance(exp.metadata, dict)
                    else None
                ),
                "mission_status": (
                    exp.metadata.get("growth_event", {}).get("mission_status")
                    if isinstance(exp.metadata, dict)
                    else None
                ),
                "training_stage_from": (
                    exp.metadata.get("growth_event", {}).get("training_stage_from")
                    if isinstance(exp.metadata, dict)
                    else None
                ),
                "training_stage_to": (
                    exp.metadata.get("growth_event", {}).get("training_stage_to")
                    if isinstance(exp.metadata, dict)
                    else None
                ),
                "next_action": (
                    exp.metadata.get("growth_event", {}).get("next_action")
                    if isinstance(exp.metadata, dict)
                    else None
                ),
                "signature": (
                    exp.metadata.get("growth_event", {}).get("signature")
                    if isinstance(exp.metadata, dict) and isinstance(exp.metadata.get("growth_event"), dict)
                    else None
                ),
            }
            for exp in ExperienceStore(workspace, tenant_id).load_by_task("evolution", "growth_event", limit=12)
        ]
        growth_timeline = build_growth_timeline(strategy_review_queue, auto_rollback_events, growth_events)
        operation_timeline = build_operation_experience_timeline(experiences)
        merged_growth_timeline = [*growth_timeline, *operation_timeline]
        merged_growth_timeline = [item for item in merged_growth_timeline if item.get("timestamp")]
        merged_growth_timeline.sort(key=lambda item: item["timestamp"], reverse=True)
        override_hits = sum(int(item.get("hits", 0)) for item in override_stats.values())
        override_success = sum(int(item.get("success", 0)) for item in override_stats.values())
        override_success_rate = round(override_success / override_hits, 3) if override_hits else None
        summary = {
            "tasks_total": len(tasks),
            "decision_events": len(decision_events),
            "experiences_total": len(experiences),
            "role_reflections_total": len([
                exp for exp in experiences
                if isinstance(exp.metadata, dict) and isinstance(exp.metadata.get("professional_experience"), dict)
            ]),
            "avg_evaluation_score": round(score_total / score_count, 3) if score_count else None,
            "success_rate": round(
                len([task for task in tasks if task.status.value == "success"]) / len(tasks),
                3,
            ) if tasks else None,
            "override_hits": override_hits,
            "override_success_rate": override_success_rate,
        }
        knowledge_policy = tenant_manager.get_knowledge_policy(tenant_id)
        platform_promotion_status = get_platform_promotion_status(tenant_manager, tenant_id)
        platform_shared_promotions = list_platform_strategy_promotions(workspace, limit=12)
        knowledge_layer_advice = build_knowledge_layer_advice(
            knowledge_policy=knowledge_policy,
            platform_promotion_status=platform_promotion_status,
            recent_experiences=recent_experiences,
            strategy_review_queue=strategy_review_queue,
            platform_shared_promotions=platform_shared_promotions,
            summary=summary,
            review_cases=review_events[:12],
        )

        return {
            "tenant_id": tenant_id,
            "summary": summary,
            "domains": domains,
            "capability_types": tenant_manager.get_tenant(tenant_id).capability_types if tenant_manager.get_tenant(tenant_id) else [],
            "plugin_policy": {
                **enabled_plugins,
                "loaded": loaded_plugins,
                "capability_types": loaded_capability_types,
            },
            "knowledge_policy": knowledge_policy,
            "platform_promotion_status": platform_promotion_status,
            "knowledge_layer_advice": knowledge_layer_advice,
            "strategy_overrides": strategy_overrides,
            "override_stats": override_stats,
            "auto_rollback_events": auto_rollback_events[:8],
            "growth_timeline": merged_growth_timeline[:30],
            "top_capabilities": top_capabilities,
            "top_strategies": top_strategies,
            "evaluation_verdicts": verdict_counts,
            "review_category_counts": review_category_counts,
            "recent_decisions": decision_events[:12],
            "recent_experiences": recent_experiences,
            "recent_role_reflections": recent_role_reflections[:8],
            "review_cases": review_events[:12],
            "replay_validations": replay_validations,
            "growth_events": growth_events,
            "positive_strategies": positive_strategies[:8],
            "strategy_alerts": strategy_alerts[:8],
            "strategy_review_queue": strategy_review_queue[:20],
            "auto_review_entries": auto_review_entries[:8],
            "platform_shared_promotions": platform_shared_promotions,
        }

    return {
        "build_evolution_overview": build_evolution_overview,
    }
