"""
智脑运行时装配：聚合自媒体、演化策略、外部学习、后台研究等绑定。
"""

from __future__ import annotations

from typing import Callable

from admin.background_research_runtime import create_background_research_runtime_bindings
from admin.evolution_overview_runtime import create_evolution_overview_runtime_bindings
from admin.evolution_summary_runtime import create_evolution_summary_runtime_bindings
from admin.external_learning_runtime import create_external_learning_runtime_bindings
from admin.git_knowledge_runtime import create_git_knowledge_runtime_bindings
from admin.mission_app_runtime import create_mission_app_runtime_bindings
from admin.self_media_runtime import create_self_media_runtime_bindings
from admin.strategy_bindings import create_strategy_bindings
from admin.autonomy_validation_runtime import create_autonomy_validation_bindings


def create_intelligence_bootstrap_runtime_bindings(
    *,
    task_priority_cls,
    task_status_cls,
    trim_candidate_text: Callable[[str | None, int], str],
    safe_float: Callable[[object, float], float],
    record_growth_event: Callable,
    record_member_experience_journal: Callable,
    list_platform_strategy_promotions: Callable,
    find_review_item_signature: Callable,
    task_evaluation_score: Callable,
    get_platform_shared_root: Callable,
    build_review_item_signature: Callable,
    load_review_queue: Callable,
    save_review_queue: Callable,
    task_strategy_id: Callable,
    task_evaluation_verdict: Callable,
    generate_review_draft: Callable,
    generate_review_experiment_plan: Callable,
    run_review_experiment: Callable,
    build_strategy_upgrade_candidate: Callable,
    maybe_auto_accept_upgrade_candidate: Callable,
    refresh_review_queue_experiment_runs: Callable,
    advance_background_research_for_tenant: Callable,
    summarize_experiment_run: Callable,
    record_experiment_run_validations: Callable,
    update_upgrade_candidate_decision: Callable,
    rollback_strategy_override: Callable,
    enqueue_strategy_review: Callable,
    auto_enqueue_review_cases: Callable,
    auto_prepare_review_entries: Callable,
    auto_promote_review_entries: Callable,
    classify_review_case: Callable,
    recommend_actions: Callable,
    build_operation_experience_timeline: Callable,
    load_autonomy_runtime: Callable,
    load_learning_tasks: Callable,
    normalize_child_members_runtime: Callable,
    normalize_feedback_monitor_runtime: Callable,
    save_autonomy_runtime: Callable,
    save_learning_tasks: Callable,
    discover_javascript_research_samples: Callable,
    auto_submit_javascript_research_tasks: Callable,
    diagnose_research_sample: Callable,
    auto_draft_stable_experience_skills: Callable,
    advance_background_self_media_autonomy_for_tenant: Callable,
    get_self_media_git_export_status: Callable[[str], dict],
    advance_background_feedback_monitor_for_tenant: Callable,
    make_learning_task_id: Callable,
    build_diagnosis_signature: Callable,
    score_signature_similarity: Callable,
    latest_sample_task: Callable,
    parse_iso_datetime: Callable,
    draft_learning_signature: Callable,
    build_task_comparison: Callable,
    record_replay_validation: Callable,
    build_snapshot_signature: Callable,
):
    self_media = create_self_media_runtime_bindings(
        trim_candidate_text=trim_candidate_text,
        load_autonomy_runtime=load_autonomy_runtime,
    )

    evolution_runtime = create_evolution_overview_runtime_bindings(
        list_platform_strategy_promotions=list_platform_strategy_promotions,
        record_growth_event=record_growth_event,
        find_review_item_signature=find_review_item_signature,
        safe_float=safe_float,
        task_evaluation_score=task_evaluation_score,
    )
    evolution_overview_runtime_ref: dict[str, object] = {}

    def build_evolution_overview_forwarder(**kwargs):
        runtime_fn = evolution_overview_runtime_ref.get("fn")
        if not callable(runtime_fn):
            return {}
        return runtime_fn(**kwargs)

    strategy = create_strategy_bindings(
        safe_float=safe_float,
        get_platform_promotion_status=evolution_runtime["get_platform_promotion_status"],
        get_platform_shared_root=get_platform_shared_root,
        record_growth_event=record_growth_event,
        build_review_item_signature=build_review_item_signature,
        load_review_queue=load_review_queue,
        save_review_queue=save_review_queue,
        task_strategy_id=task_strategy_id,
        task_evaluation_verdict=task_evaluation_verdict,
        task_evaluation_score=task_evaluation_score,
        generate_review_draft=generate_review_draft,
        generate_review_experiment_plan=generate_review_experiment_plan,
        run_review_experiment=run_review_experiment,
        build_strategy_upgrade_candidate=build_strategy_upgrade_candidate,
        maybe_auto_accept_upgrade_candidate=maybe_auto_accept_upgrade_candidate,
        refresh_review_queue_experiment_runs=refresh_review_queue_experiment_runs,
        advance_background_research_for_tenant=advance_background_research_for_tenant,
        summarize_experiment_run=summarize_experiment_run,
        record_experiment_run_validations=record_experiment_run_validations,
        build_evolution_overview=build_evolution_overview_forwarder,
        update_upgrade_candidate_decision=update_upgrade_candidate_decision,
        rollback_strategy_override=rollback_strategy_override,
        enqueue_strategy_review=enqueue_strategy_review,
        auto_enqueue_review_cases=auto_enqueue_review_cases,
        auto_prepare_review_entries=auto_prepare_review_entries,
        auto_promote_review_entries=auto_promote_review_entries,
    )

    evolution_summary = create_evolution_summary_runtime_bindings(
        safe_float=safe_float,
        classify_review_case=classify_review_case,
        recommend_actions=recommend_actions,
        auto_enqueue_review_cases=strategy["auto_enqueue_review_cases"],
        auto_prepare_review_entries=strategy["auto_prepare_review_entries"],
        summarize_override_effects=evolution_runtime["summarize_override_effects"],
        auto_rollback_risky_overrides=evolution_runtime["auto_rollback_risky_overrides"],
        refresh_review_queue_experiment_runs=strategy["refresh_review_queue_experiment_runs"],
        build_growth_timeline=evolution_runtime["build_growth_timeline"],
        build_knowledge_layer_advice=evolution_runtime["build_knowledge_layer_advice"],
        get_platform_promotion_status=evolution_runtime["get_platform_promotion_status"],
        list_platform_strategy_promotions=list_platform_strategy_promotions,
        build_operation_experience_timeline=build_operation_experience_timeline,
    )
    build_evolution_overview = evolution_summary["build_evolution_overview"]
    evolution_overview_runtime_ref["fn"] = build_evolution_overview

    mission_app_runtime = create_mission_app_runtime_bindings(
        extract_feedback_entries_from_result=self_media["extract_feedback_entries_from_result"],
        trim_candidate_text=trim_candidate_text,
        normalize_string_list=lambda value: [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else [],
    )

    git_knowledge = create_git_knowledge_runtime_bindings(
        load_learning_tasks=load_learning_tasks,
        trim_candidate_text=trim_candidate_text,
        build_evolution_overview=build_evolution_overview,
    )

    external_learning = create_external_learning_runtime_bindings(
        list_platform_strategy_promotions=list_platform_strategy_promotions,
        load_review_queue=load_review_queue,
        load_enterprise_repo_index=git_knowledge["load_enterprise_repo_index"],
        trim_candidate_text=trim_candidate_text,
        make_learning_task_id=make_learning_task_id,
        build_diagnosis_signature=build_diagnosis_signature,
        build_review_item_signature=build_review_item_signature,
        score_signature_similarity=score_signature_similarity,
    )

    learning = create_autonomy_validation_bindings(
        task_priority_cls=task_priority_cls,
        load_learning_tasks=load_learning_tasks,
        save_learning_tasks=save_learning_tasks,
        load_review_queue=load_review_queue,
        refresh_review_queue_experiment_runs=strategy["refresh_review_queue_experiment_runs"],
        generate_review_draft=strategy["generate_review_draft"],
        generate_review_experiment_plan=strategy["generate_review_experiment_plan"],
        run_review_experiment=strategy["run_review_experiment"],
        latest_sample_task=latest_sample_task,
        execute_learning_task=external_learning["execute_learning_task"],
        parse_iso_datetime=parse_iso_datetime,
        draft_learning_signature=draft_learning_signature,
        detect_local_codex=external_learning["detect_local_codex"],
        run_local_codex_learning=external_learning["run_local_codex_learning"],
        trim_candidate_text=trim_candidate_text,
        build_task_comparison=build_task_comparison,
        record_replay_validation=record_replay_validation,
        record_growth_event=record_growth_event,
        safe_float=safe_float,
        build_snapshot_signature=build_snapshot_signature,
        make_learning_task_id=make_learning_task_id,
    )

    background_runtime = create_background_research_runtime_bindings(
        load_autonomy_runtime=load_autonomy_runtime,
        load_learning_tasks=load_learning_tasks,
        normalize_child_members_runtime=normalize_child_members_runtime,
        normalize_feedback_monitor_runtime=normalize_feedback_monitor_runtime,
        save_autonomy_runtime=save_autonomy_runtime,
        save_learning_tasks=save_learning_tasks,
        discover_javascript_research_samples=discover_javascript_research_samples,
        auto_submit_javascript_research_tasks=auto_submit_javascript_research_tasks,
        diagnose_research_sample=diagnose_research_sample,
        build_external_learning_plan=external_learning["build_external_learning_plan"],
        refresh_learning_task=learning["refresh_learning_task"],
        advance_background_research_for_tenant=strategy["advance_background_research_for_tenant"],
        auto_draft_stable_experience_skills=auto_draft_stable_experience_skills,
        record_growth_event=record_growth_event,
        record_member_experience_journal=record_member_experience_journal,
        safe_float=safe_float,
        advance_background_self_media_autonomy_for_tenant=advance_background_self_media_autonomy_for_tenant,
        get_account_identity=self_media["get_toutiao_account_identity"],
        describe_toutiao_executor_registry=self_media["describe_toutiao_executor_registry"],
        get_git_export_status=get_self_media_git_export_status,
        advance_background_feedback_monitor_for_tenant=advance_background_feedback_monitor_for_tenant,
        task_priority_normal=task_priority_cls.NORMAL,
        pending_status=task_status_cls.PENDING,
        running_status=task_status_cls.RUNNING,
    )

    return {
        "self_media": self_media,
        "evolution_runtime": evolution_runtime,
        "strategy": strategy,
        "evolution_summary": evolution_summary,
        "background_runtime": background_runtime,
        "mission_app_runtime": mission_app_runtime,
        "git_knowledge": git_knowledge,
        "external_learning": external_learning,
        "learning": learning,
        "build_evolution_overview": build_evolution_overview,
    }


__all__ = ["create_intelligence_bootstrap_runtime_bindings"]
