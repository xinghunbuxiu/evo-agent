"""
将策略模块装配成可直接注入 route/background 的绑定函数集合。
"""

from __future__ import annotations

from typing import Callable


def create_strategy_bindings(
    *,
    safe_float: Callable[[object, float], float],
    get_platform_promotion_status: Callable[..., dict],
    get_platform_shared_root: Callable,
    record_growth_event: Callable[..., object],
    build_review_item_signature: Callable[[dict], dict],
    load_review_queue: Callable,
    save_review_queue: Callable,
    task_strategy_id: Callable,
    task_evaluation_verdict: Callable,
    task_evaluation_score: Callable,
    generate_review_draft: Callable,
    generate_review_experiment_plan: Callable,
    run_review_experiment: Callable,
    build_strategy_upgrade_candidate: Callable,
    maybe_auto_accept_upgrade_candidate: Callable,
    refresh_review_queue_experiment_runs: Callable,
    advance_background_research_for_tenant: Callable,
    summarize_experiment_run: Callable,
    record_experiment_run_validations: Callable,
    build_evolution_overview: Callable,
    update_upgrade_candidate_decision: Callable,
    rollback_strategy_override: Callable,
    enqueue_strategy_review: Callable,
    auto_enqueue_review_cases: Callable,
    auto_prepare_review_entries: Callable,
    auto_promote_review_entries: Callable,
):
    def promote_review_entry_to_platform_bound(workspace, tenant_id, review_entry, tenant_manager):
        return promote_review_entry_to_platform(
            workspace,
            tenant_id,
            review_entry,
            tenant_manager,
            get_platform_promotion_status=get_platform_promotion_status,
            get_platform_shared_root=get_platform_shared_root,
            record_growth_event=record_growth_event,
            build_review_item_signature=build_review_item_signature,
        )

    def enqueue_strategy_review_bound(workspace, tenant_id, strategy_id, payload):
        return enqueue_strategy_review(
            workspace,
            tenant_id,
            strategy_id,
            payload,
            load_review_queue=load_review_queue,
            save_review_queue=save_review_queue,
        )

    def auto_enqueue_review_cases_bound(workspace, tenant_id, review_events):
        return auto_enqueue_review_cases(
            workspace,
            tenant_id,
            review_events,
            enqueue_strategy_review_fn=enqueue_strategy_review_bound,
        )

    def auto_prepare_review_entries_bound(workspace, tenant_id, entries):
        return auto_prepare_review_entries(
            workspace,
            tenant_id,
            entries,
            generate_review_draft_fn=generate_review_draft_bound,
            generate_review_experiment_plan_fn=generate_review_experiment_plan_bound,
        )

    def auto_promote_review_entries_bound(workspace, tenant_id, tenant_manager):
        return auto_promote_review_entries(
            workspace,
            tenant_id,
            tenant_manager,
            load_review_queue=load_review_queue,
            save_review_queue=save_review_queue,
            promote_review_entry_to_platform_fn=promote_review_entry_to_platform_bound,
        )

    def task_strategy_id_bound(task):
        return task_strategy_id(task)

    def task_evaluation_verdict_bound(task):
        return task_evaluation_verdict(task)

    def task_evaluation_score_bound(task):
        return task_evaluation_score(task, safe_float=safe_float)

    def generate_review_draft_bound(workspace, tenant_id, review_id):
        return generate_review_draft(
            workspace,
            tenant_id,
            review_id,
            load_review_queue=load_review_queue,
            save_review_queue=save_review_queue,
            safe_float=safe_float,
        )

    def generate_review_experiment_plan_bound(workspace, tenant_id, review_id):
        return generate_review_experiment_plan(
            workspace,
            tenant_id,
            review_id,
            load_review_queue=load_review_queue,
            save_review_queue=save_review_queue,
            safe_float=safe_float,
        )

    def run_review_experiment_bound(workspace, tenant_id, review_id, task_queue):
        return run_review_experiment(
            workspace,
            tenant_id,
            review_id,
            task_queue,
            load_review_queue=load_review_queue,
            save_review_queue=save_review_queue,
        )

    def build_strategy_upgrade_candidate_bound(item, run):
        return build_strategy_upgrade_candidate(
            item,
            run,
            safe_float=safe_float,
        )

    def maybe_auto_accept_upgrade_candidate_bound(workspace, tenant_id, item):
        return maybe_auto_accept_upgrade_candidate(
            workspace,
            tenant_id,
            item,
            safe_float=safe_float,
            record_growth_event=record_growth_event,
            build_review_item_signature=build_review_item_signature,
        )

    def refresh_review_queue_experiment_runs_bound(workspace, tenant_id, task_queue):
        return refresh_review_queue_experiment_runs(
            workspace,
            tenant_id,
            task_queue,
            load_review_queue=load_review_queue,
            save_review_queue=save_review_queue,
            summarize_experiment_run=summarize_experiment_run,
            record_experiment_run_validations=record_experiment_run_validations,
            build_strategy_upgrade_candidate=build_strategy_upgrade_candidate_bound,
            maybe_auto_accept_upgrade_candidate=maybe_auto_accept_upgrade_candidate_bound,
        )

    def advance_background_research_for_tenant_bound(workspace, tenant_id, task_queue, plugin_summary, tenant_manager):
        return advance_background_research_for_tenant(
            workspace,
            tenant_id,
            task_queue,
            plugin_summary,
            tenant_manager,
            build_evolution_overview=build_evolution_overview,
            load_review_queue=load_review_queue,
            generate_review_draft_fn=generate_review_draft_bound,
            generate_review_experiment_plan_fn=generate_review_experiment_plan_bound,
            run_review_experiment_fn=run_review_experiment_bound,
            refresh_review_queue_experiment_runs_fn=refresh_review_queue_experiment_runs_bound,
            auto_promote_review_entries_fn=auto_promote_review_entries_bound,
        )

    def update_upgrade_candidate_decision_bound(workspace, tenant_id, review_id, decision):
        return update_upgrade_candidate_decision(
            workspace,
            tenant_id,
            review_id,
            decision,
            load_review_queue=load_review_queue,
            save_review_queue=save_review_queue,
            record_growth_event=record_growth_event,
            build_review_item_signature=build_review_item_signature,
        )

    def rollback_strategy_override_bound(workspace, tenant_id, strategy_id):
        return rollback_strategy_override(
            workspace,
            tenant_id,
            strategy_id,
            record_growth_event=record_growth_event,
        )

    return {
        "promote_review_entry_to_platform": promote_review_entry_to_platform_bound,
        "enqueue_strategy_review": enqueue_strategy_review_bound,
        "auto_enqueue_review_cases": auto_enqueue_review_cases_bound,
        "auto_prepare_review_entries": auto_prepare_review_entries_bound,
        "auto_promote_review_entries": auto_promote_review_entries_bound,
        "task_strategy_id": task_strategy_id_bound,
        "task_evaluation_verdict": task_evaluation_verdict_bound,
        "task_evaluation_score": task_evaluation_score_bound,
        "generate_review_draft": generate_review_draft_bound,
        "generate_review_experiment_plan": generate_review_experiment_plan_bound,
        "run_review_experiment": run_review_experiment_bound,
        "build_strategy_upgrade_candidate": build_strategy_upgrade_candidate_bound,
        "maybe_auto_accept_upgrade_candidate": maybe_auto_accept_upgrade_candidate_bound,
        "refresh_review_queue_experiment_runs": refresh_review_queue_experiment_runs_bound,
        "advance_background_research_for_tenant": advance_background_research_for_tenant_bound,
        "update_upgrade_candidate_decision": update_upgrade_candidate_decision_bound,
        "rollback_strategy_override": rollback_strategy_override_bound,
    }
