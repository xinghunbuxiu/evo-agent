"""
Evo Admin API Server - FastAPI
轻量级后端，为 Vue3 前端提供服务
"""

import os
import json
import copy
import asyncio
import threading
import time
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
import httpx
from dotenv import load_dotenv

from admin.spa_static import register_spa_static

# 核心组件
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from core import (
    Experience,
    ExperienceStore,
    get_distributed_config,
    get_capability_registry,
    DecisionEngine,
    PluginLoader,
    GitProviderError,
    capability_type_catalog,
    capability_type_label,
    MissionPlanner,
    MISSION_KIND_TEMPLATES,
)
from core.tenant import TenantManager
from core.task_queue import get_task_queue, TaskPriority, TaskStatus
from admin.database import db, MYSQL_AVAILABLE
from admin.mission_runtime import (
    derive_follow_up_context,
    derive_follow_up_goal,
    find_mission_run,
    load_mission_runs,
    save_mission_runs,
)
from admin.mission_bootstrap_runtime import (
    create_mission_bootstrap_runtime_bindings,
)
from admin.worker_bootstrap_runtime import (
    create_worker_bootstrap_runtime_bindings,
)
from admin.intelligence_bootstrap_runtime import (
    create_intelligence_bootstrap_runtime_bindings,
)
from admin.mission_execution_runtime import (
    create_mission_execution_bindings,
)
from admin.growth_policy_runtime import (
    effective_platform_promotion_status as _effective_platform_promotion_status,
    growth_policy_decision_label as _growth_policy_decision_label,
    resolve_effective_growth_policy as _resolve_effective_growth_policy,
)
from admin.mission_action_runtime import (
    create_mission_action_runtime_bindings,
)
from admin.knowledge_runtime import (
    auto_draft_stable_experience_skills as _auto_draft_stable_experience_skills,
    collect_task_verified_skills as _collect_task_verified_skills,
    create_mission_delivery_skill_candidate as _create_mission_delivery_skill_candidate,
    infer_framework_hint_from_delivery as _infer_framework_hint_from_delivery,
    skill_ids_from_items as _skill_ids_from_items,
)
from admin.autonomy_learning_runtime import (
    normalize_mission_learning_task_payload as _normalize_mission_learning_task_payload,
    upsert_plan_learning_tasks as _upsert_plan_learning_tasks,
)
from admin.runtime_state import (
    create_employee_member_runtime as _create_employee_member_runtime,
    load_autonomy_runtime as _load_autonomy_runtime,
    load_learning_tasks as _load_learning_tasks,
    normalize_child_agent_runtime as _normalize_child_agent_runtime,
    normalize_child_members_runtime as _normalize_child_members_runtime,
    normalize_feedback_monitor_runtime as _normalize_feedback_monitor_runtime,
    normalize_parent_profile_runtime as _normalize_parent_profile_runtime,
    save_autonomy_runtime as _save_autonomy_runtime,
    save_learning_tasks as _save_learning_tasks,
)
from admin.session_runtime import (
    create_session as _create_session_entry,
    delete_session as _delete_session_entry,
    get_session_user as _resolve_session_user,
    get_user_gitee_token as _resolve_user_gitee_token,
    load_sessions as _load_sessions_from_file,
    persist_sessions as _persist_sessions_to_file,
)
from admin.strategy_runtime import (
    get_platform_shared_root as _get_platform_shared_root,
    list_platform_strategy_promotions as _list_platform_strategy_promotions,
    load_review_queue as _load_review_queue,
    save_review_queue as _save_review_queue,
)
from admin.strategy_governance import (
    rollback_strategy_override,
    update_upgrade_candidate_decision,
)
from admin.strategy_decision import (
    build_strategy_upgrade_candidate,
    maybe_auto_accept_upgrade_candidate,
)
from admin.strategy_loop import (
    advance_background_research_for_tenant,
    refresh_review_queue_experiment_runs,
)
from admin.strategy_orchestration import (
    auto_enqueue_review_cases,
    auto_promote_review_entries,
    auto_prepare_review_entries,
    enqueue_strategy_review,
    promote_review_entry_to_platform,
)
from admin.strategy_workflow import (
    generate_review_draft,
    generate_review_experiment_plan,
    run_review_experiment,
    task_evaluation_score,
    task_evaluation_verdict,
    task_strategy_id,
)
from admin.finance_runtime import purge_preset_finance_data, upsert_finance_from_analytics
from admin.worker_route_runtime import resolve_experience_domain, resolve_work_type_id
from admin.routes import (
    register_auth_routes,
    register_evolution_strategy_routes,
    register_catalog_routes,
    register_finance_routes,
    register_git_knowledge_routes,
    register_mission_routes,
    register_self_media_routes,
    register_system_runtime_routes,
    register_task_tool_routes,
    register_tenant_policy_routes,
)
from workers.javascript_reverse.runtime import (
    auto_submit_javascript_research_tasks,
    discover_javascript_research_samples,
    latest_sample_task,
)
from workers import (
    build_mission_context_resolvers,
    builtin_worker_manifests,
    load_worker_registry_config,
    register_builtin_worker_mission_action_handlers,
    register_builtin_worker_mission_post_action_handlers,
    register_builtin_worker_mission_summary_handlers,
    save_worker_registry_config,
)
from workers.self_media_operations.monitor import (
    advance_background_self_media_autonomy_for_tenant,
    advance_background_feedback_monitor_for_tenant,
)
from workers.self_media_operations.runtime import (
    build_operation_experience_timeline,
    record_operation_experience,
    summarize_toutiao_analytics_result,
)
from project_caps import (
    build_project_package_runtime_entries,
    load_project_packages,
    purge_preset_project_packages,
    register_project_capabilities,
    register_project_orchestration,
    save_project_packages,
)
from work_types import (
    load_work_types,
    resolve_work_type_context,
    save_work_types,
    summarize_work_type,
    validate_work_type_request,
)
from work_type_runtime import (
    build_work_type_runtime_index,
    resolve_runtime_route,
)

# 内存 session 存储（生产环境建议用 Redis）
_sessions: dict = {}
_sessions_file: Path | None = None
_mission_action_runtime_ref: dict[str, object] = {}


def _normalize_string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _serialize_user(user: dict) -> dict:
    """只返回前端需要的安全字段，避免把原始 token 回传给前端。"""
    return {
        "id": user.get("id"),
        "login": user.get("login"),
        "name": user.get("name"),
        "avatar": user.get("avatar"),
        "gitee_login": user.get("gitee_login"),
    }


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_sessions() -> None:
    global _sessions
    _sessions = _load_sessions_from_file(_sessions_file)


def _persist_sessions() -> None:
    _persist_sessions_to_file(_sessions_file, _sessions)


def _create_session(user: dict) -> str:
    return _create_session_entry(_sessions_file, _sessions, user)


def _delete_session(session_id: str | None) -> None:
    _delete_session_entry(_sessions_file, _sessions, session_id)


def _get_session_user(request: Request) -> dict | None:
    return _resolve_session_user(_sessions, request)


def _get_user_gitee_token(request: Request) -> str | None:
    return _resolve_user_gitee_token(_sessions, request)


def _get_background_gitee_token() -> str | None:
    for user in _sessions.values():
        if not isinstance(user, dict):
            continue
        token = str(user.get("token") or "").strip()
        if token:
            return token
    env_token = str(os.getenv("GITEE_TOKEN") or "").strip()
    return env_token or None


def _classify_review_case(
    *,
    status: str,
    error: str | None,
    verdict: str | None,
    evaluation_reasons: list[str],
    evaluation_metrics: dict,
    candidate_scores: list[dict],
    capability_id: str | None,
    strategy_id: str | None,
    plugin_policy: dict,
) -> tuple[str, list[str]]:
    hints: list[str] = []
    error_text = (error or "").lower()
    reasons_text = " ".join(evaluation_reasons).lower()
    disabled_plugins = set(plugin_policy.get("disabled", []))
    enabled_plugins = set(plugin_policy.get("enabled", []))
    framework_count = int(evaluation_metrics.get("framework_count", 0) or 0)
    pattern_count = int(evaluation_metrics.get("pattern_count", 0) or 0)
    confidence = _safe_float(evaluation_metrics.get("confidence"), -1)
    components = int(evaluation_metrics.get("components", 0) or 0)
    has_target_dir = bool(evaluation_metrics.get("has_target_dir"))

    if status == "failed":
        if "missing path" in error_text or "no such file" in error_text or "not found" in error_text:
            hints.append("输入路径缺失或无效")
            return "input_gap", hints
        if "disabled for tenant" in error_text:
            hints.append("租户策略禁用了当前能力或插件")
            return "plugin_policy_gap", hints
        if "no capability candidates" in error_text or "no handler" in error_text:
            hints.append("当前任务没有可用能力或执行入口")
            return "capability_gap", hints
        hints.append("执行阶段直接抛错，需要先排查运行链路")
        return "execution_error", hints

    if verdict == "review":
        if confidence >= 0 and confidence < 0.45:
            hints.append("置信度偏低，输入样本特征不足")
            return "input_gap", hints
        if framework_count == 0 and pattern_count == 0 and "frameworks detected" not in reasons_text:
            hints.append("识别结果过少，说明分析规则覆盖还不够")
            return "strategy_gap", hints
        if not has_target_dir and components == 0 and capability_id:
            hints.append("重构结果产物不足，脚手架策略需要增强")
            return "strategy_gap", hints
        if enabled_plugins or disabled_plugins:
            plugin_name = None
            if strategy_id and strategy_id.startswith("plugin."):
                plugin_name = strategy_id.split(".")[1] if len(strategy_id.split(".")) > 1 else None
            if plugin_name and plugin_name in disabled_plugins:
                hints.append("插件被租户策略禁用，导致策略空间受限")
                return "plugin_policy_gap", hints
        if candidate_scores and len(candidate_scores) == 1 and _safe_float(candidate_scores[0].get("score")) < 2.5:
                hints.append("候选能力过少，当前能力空间太窄")
                return "capability_gap", hints
        hints.append("任务完成了，但评估器认为质量还不稳定")
        return "evaluator_strict", hints

    if verdict == "pass":
        if capability_id == "builtin.javascript":
            if components > 0 and has_target_dir:
                hints.append("当前样本已经形成可接手的项目骨架")
                hints.append("适合继续扩样本并观察是否仍然稳定")
                return "stable_verified", hints
            if components == 0 and has_target_dir:
                hints.append("产物目录已生成，但组件恢复仍然偏弱")
                return "partial_recovery", hints
            if framework_count > 0 or pattern_count > 0 or "frameworks detected" in reasons_text:
                if confidence >= 0.75 or confidence < 0:
                    hints.append("当前识别链路稳定，可作为后续扩展能力的基线")
                    return "stable_verified", hints
                hints.append("已经识别到关键特征，但仍建议继续观察更多样本")
                return "observation_needed", hints
        hints.append("当前任务通过，可以继续作为稳定基线样本")
        return "stable_verified", hints

    hints.append("暂无明确问题分类")
    return "unknown", hints


def _recommend_actions(
    *,
    category: str,
    task_type: str,
    capability_id: str | None,
    strategy_id: str | None,
    plugin_policy: dict,
) -> list[str]:
    actions: list[str] = []

    if category == "input_gap":
        actions.append("补充更完整的输入样本，避免只给单文件或缺少上下文目录")
        actions.append("为任务增加更明确的 preferred_tags、signals 或 domain_hint")
    elif category == "plugin_policy_gap":
        enabled = plugin_policy.get("enabled", []) or []
        disabled = plugin_policy.get("disabled", []) or []
        if disabled:
            actions.append(f"检查租户禁用列表：{', '.join(disabled[:3])}")
        if enabled:
            actions.append("确认目标插件是否在 enabled 白名单内")
        actions.append("到设置页调整当前 tenant 的插件策略后再重放任务")
    elif category == "capability_gap":
        actions.append("扩展 capability provider，避免当前任务只有单一能力可选")
        actions.append("为该任务类型补充新的内置能力或企业插件能力")
    elif category == "strategy_gap":
        actions.append("基于当前复盘样本新增或优化策略规则")
        actions.append("将这条样本沉淀为策略测试用例，验证优化前后差异")
    elif category == "execution_error":
        actions.append("优先排查输入路径、运行环境和任务参数是否完整")
        actions.append("重放同一任务并记录完整错误栈，确认是否为稳定复现问题")
    elif category == "evaluator_strict":
        actions.append("检查评估器阈值是否过严，必要时放宽 verdict 条件")
        actions.append("对比通过样本与 review 样本，补充更高质量输出特征")
    elif category == "stable_verified":
        actions.append("把当前样本沉淀为稳定基线，用于后续重放对比")
        actions.append("继续扩充相邻类型样本，验证是否能跨样本稳定通过")
    elif category == "partial_recovery":
        actions.append("补强从识别结果到组件/页面骨架的恢复规则")
        actions.append("把当前样本加入观察队列，比较后续组件恢复数量是否提升")
    elif category == "observation_needed":
        actions.append("继续后台观察同类样本，确认当前通过是否只是偶发")
        actions.append("补充更细的评估指标，记录识别置信度和关键特征波动")
    else:
        actions.append("先人工复盘该样本，再决定是补能力、补策略还是调评估器")

    if task_type == "reconstruct":
        actions.append("重点检查 analysis_result 是否完整传入 reconstruct 阶段")
    if capability_id:
        actions.append(f"复核当前能力链路：{capability_id}")
    if strategy_id:
        actions.append(f"复核当前策略命中逻辑：{strategy_id}")

    deduped: list[str] = []
    for item in actions:
        if item not in deduped:
            deduped.append(item)
    return deduped[:5]


def _extract_task_snapshot(task) -> dict:
    result = task.result or {}
    feedback = result.get("feedback", {}) if isinstance(result, dict) else {}
    decision = feedback.get("decision", {}) if isinstance(feedback, dict) else {}
    evaluation = feedback.get("evaluation", {}) if isinstance(feedback, dict) else {}
    strategy = decision.get("strategy", {}) if isinstance(decision, dict) else {}

    return {
        "task_id": task.id,
        "task_type": task.type,
        "tenant_id": task.tenant_id,
        "status": task.status.value,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
        "error": task.error,
        "summary": result.get("summary") if isinstance(result, dict) else None,
        "capability_id": decision.get("selected_capability_id"),
        "strategy_id": strategy.get("strategy_id"),
        "strategy_score": _safe_float(strategy.get("score")) if strategy else None,
        "strategy_runtime_adjustments": strategy.get("runtime_adjustments") if isinstance(strategy, dict) else None,
        "evaluation_verdict": evaluation.get("verdict"),
        "evaluation_score": _safe_float(evaluation.get("score")) if isinstance(evaluation, dict) and evaluation.get("score") is not None else None,
        "evaluation_metrics": evaluation.get("metrics", {}) if isinstance(evaluation, dict) else {},
        "replay_of": (task.payload or {}).get("_replay_of"),
    }


def _build_snapshot_signature(snapshot: dict) -> dict:
    return _normalize_learning_signature({
        "issue_category": snapshot.get("issue_category"),
        "strategy_id": snapshot.get("strategy_id"),
        "capability_id": snapshot.get("capability_id"),
        "task_type": snapshot.get("task_type"),
        "metrics": snapshot.get("evaluation_metrics", {}) if isinstance(snapshot.get("evaluation_metrics"), dict) else {},
    })


def _build_task_comparison(original_task, replay_task) -> dict:
    original = _extract_task_snapshot(original_task)
    replay = _extract_task_snapshot(replay_task)

    original_score = original.get("evaluation_score")
    replay_score = replay.get("evaluation_score")
    score_delta = None
    if original_score is not None and replay_score is not None:
        score_delta = round(replay_score - original_score, 3)

    if replay.get("status") == "success" and original.get("status") != "success":
        outcome = "improved"
    elif replay.get("status") == "failed" and original.get("status") == "success":
        outcome = "regressed"
    elif score_delta is not None and score_delta > 0:
        outcome = "improved"
    elif score_delta is not None and score_delta < 0:
        outcome = "regressed"
    else:
        outcome = "unchanged"

    return {
        "original": original,
        "replay": replay,
        "diff": {
            "score_delta": score_delta,
            "status_changed": original.get("status") != replay.get("status"),
            "capability_changed": original.get("capability_id") != replay.get("capability_id"),
            "strategy_changed": original.get("strategy_id") != replay.get("strategy_id"),
            "outcome": outcome,
        },
    }


def _record_replay_validation(workspace: Path, tenant_id: str, comparison: dict) -> dict | None:
    diff = comparison.get("diff", {})
    if diff.get("outcome") != "improved":
        return None

    original = comparison.get("original", {})
    replay = comparison.get("replay", {})
    original_signature = _build_snapshot_signature(original)
    replay_signature = _build_snapshot_signature(replay)
    validation_id = f"replay_validation_{original.get('task_id')}_{replay.get('task_id')}"
    exp = Experience(
        id=validation_id,
        domain="evolution",
        task_type="replay_validation",
        input_summary=str(original.get("task_id")),
        output_summary=f"Replay {replay.get('task_id')} improved over {original.get('task_id')}",
        quality_score=max(0.0, _safe_float(diff.get("score_delta"), 0.0)),
        metadata={
            "comparison": comparison,
            "validation_type": "replay_improvement",
            "signatures": {
                "original": original_signature,
                "replay": replay_signature,
            },
            "source_tasks": {
                "original": original.get("task_id"),
                "replay": replay.get("task_id"),
            },
        },
    )
    ExperienceStore(workspace, tenant_id).save(exp)
    return exp.to_dict()


def _record_experiment_run_validations(
    workspace: Path,
    tenant_id: str,
    task_queue,
    run: dict,
) -> list[str]:
    if not isinstance(run, dict):
        return []

    existing_ids = set(run.get("validation_ids", []) if isinstance(run.get("validation_ids"), list) else [])
    task_ids = run.get("task_ids", []) if isinstance(run.get("task_ids"), list) else []
    created_ids: list[str] = []

    for task_id in task_ids:
        replay_task = task_queue.get_task(task_id)
        if not replay_task:
            continue
        replay_of = (replay_task.payload or {}).get("_replay_of")
        if not replay_of:
            continue
        original_task = task_queue.get_task(replay_of)
        if not original_task:
            continue

        comparison = _build_task_comparison(original_task, replay_task)
        validation = _record_replay_validation(workspace, tenant_id, comparison)
        if not isinstance(validation, dict):
            continue
        validation_id = str(validation.get("id") or "")
        if validation_id and validation_id not in existing_ids:
            existing_ids.add(validation_id)
            created_ids.append(validation_id)

    if existing_ids:
        run["validation_ids"] = sorted(existing_ids)
    if created_ids:
        run["validation_recorded_at"] = datetime.now().isoformat()
    return created_ids


def _record_growth_event(
    workspace: Path,
    tenant_id: str,
    *,
    strategy_id: str,
    event_type: str,
    summary: str,
    quality_score: float,
    task_type: str | None = None,
    domain: str | None = None,
    signature: dict | None = None,
    metadata: dict,
) -> dict:
    event_id = f"growth_{event_type}_{strategy_id.replace('.', '_')}_{int(datetime.now().timestamp())}"
    exp = Experience(
        id=event_id,
        domain="evolution",
        task_type="growth_event",
        input_summary=strategy_id,
        output_summary=summary,
        quality_score=quality_score,
        metadata={
            "growth_event": {
                "strategy_id": strategy_id,
                "event_type": event_type,
                "task_type": task_type,
                "domain": domain,
                "signature": signature if isinstance(signature, dict) else None,
                **metadata,
            },
        },
    )
    ExperienceStore(workspace, tenant_id).save(exp)
    return exp.to_dict()


def _member_role_experience_domain(workspace: Path, primary_role: str, *, job_id: str | None = None) -> str:
    return resolve_experience_domain(workspace, primary_role=primary_role, work_type_id=job_id or primary_role)


def _member_experience_quality_score(stage: str, status: str) -> float:
    normalized_stage = str(stage or "").strip()
    normalized_status = str(status or "").strip()
    if normalized_stage == "stable":
        return 0.92
    if normalized_stage == "stabilizing":
        return 0.88
    if normalized_stage == "delivering":
        return 0.84
    if normalized_stage == "environment_blocked":
        return 0.62
    if normalized_status in {"error", "executor_missing", "waiting_login"}:
        return 0.58
    return 0.78


def _member_training_stage_from_mission_status(status: str) -> str:
    normalized = str(status or "").strip()
    if normalized in {"completed", "improved"}:
        return "stabilizing"
    if normalized in {"partially_completed", "validating"}:
        return "delivering"
    if normalized in {"needs_learning", "regressed", "failed"}:
        return "active_training"
    if normalized in {"blocked"}:
        return "environment_blocked"
    return "active_training"


def _member_growth_event_quality_score(status: str) -> float:
    normalized = str(status or "").strip()
    if normalized in {"improved"}:
        return 0.9
    if normalized in {"completed"}:
        return 0.86
    if normalized in {"partially_completed", "validating"}:
        return 0.79
    if normalized in {"blocked"}:
        return 0.61
    if normalized in {"needs_learning", "regressed", "failed"}:
        return 0.66
    return 0.74


def _record_member_growth_event(
    workspace: Path,
    tenant_id: str,
    *,
    member: dict,
    mission_run: dict,
    stage_from: str,
    stage_to: str,
    summary: str,
    signature: str,
    next_action: str,
    current_focus: str,
) -> dict:
    member_id = str(member.get("member_id") or "").strip()
    primary_role = str(member.get("primary_role") or "").strip() or "autonomous_child_agent"
    mission_run_id = str(mission_run.get("mission_run_id") or "").strip()
    strategy_id = f"member.{member_id}.{primary_role}"
    event_id = f"growth_member_sync_{member_id}_{signature[:12]}"
    exp = Experience(
        id=event_id,
        domain="evolution",
        task_type="growth_event",
        input_summary=f"{member_id}:{stage_from or 'unknown'}->{stage_to or 'unknown'}",
        output_summary=summary,
        quality_score=_member_growth_event_quality_score(mission_run.get("status")),
        metadata={
            "growth_event": {
                "strategy_id": strategy_id,
                "event_type": "member_role_progression",
                "task_type": "mission_sync",
                "domain": _member_role_experience_domain(
                    workspace,
                    primary_role,
                    job_id=resolve_work_type_id(member),
                ),
                "signature": {
                    "mission_run_id": mission_run_id,
                    "member_id": member_id,
                    "sync_signature": signature,
                },
                "member_id": member_id,
                "member_name": member.get("name"),
                "primary_role": primary_role,
                "mission_run_id": mission_run_id,
                "mission_status": mission_run.get("status"),
                "training_stage_from": stage_from,
                "training_stage_to": stage_to,
                "next_action": next_action,
                "current_focus": current_focus,
            },
        },
    )
    ExperienceStore(workspace, tenant_id).save(exp)
    return exp.to_dict()


def _record_member_experience_journal(
    workspace: Path,
    tenant_id: str,
    *,
    member: dict,
    journal: dict,
    source: str = "autonomy_runtime",
) -> list[str]:
    if not isinstance(member, dict) or not isinstance(journal, dict):
        return []
    cards = journal.get("cards") if isinstance(journal.get("cards"), list) else []
    if not cards:
        return []

    member_id = str(member.get("member_id") or "").strip()
    member_name = str(member.get("name") or "").strip()
    primary_role = str(member.get("primary_role") or "").strip() or "autonomous_child_agent"
    if not member_id:
        return []

    domain = _member_role_experience_domain(workspace, primary_role, job_id=resolve_work_type_id(member))
    saved_ids: list[str] = []
    store = ExperienceStore(workspace, tenant_id)
    for card in cards[:6]:
        if not isinstance(card, dict):
            continue
        signature = str(card.get("signature") or "").strip()
        if not signature:
            continue
        digest = hashlib.sha1(f"{member_id}|{signature}".encode("utf-8")).hexdigest()[:12]
        exp_id = f"role_reflection_{member_id}_{digest}"
        exp = Experience(
            id=exp_id,
            domain=domain,
            task_type="role_reflection",
            input_summary=f"{member_id}:{primary_role}:{card.get('stage') or 'active'}",
            output_summary=str(card.get("summary") or card.get("title") or f"{member_name or member_id} role reflection").strip(),
            quality_score=_member_experience_quality_score(
                str(card.get("stage") or ""),
                str(card.get("status") or ""),
            ),
            metadata={
                "professional_experience": {
                    "member_id": member_id,
                    "member_name": member_name,
                    "primary_role": primary_role,
                    "source": source,
                    "journal_last_compiled_at": journal.get("last_compiled_at"),
                    "latest_card_id": journal.get("latest_card_id"),
                    "card": card,
                },
            },
        )
        store.save(exp)
        saved_ids.append(exp_id)
    return saved_ids



def _extract_task_diagnostics(task, plugin_policy: dict) -> dict:
    if not task:
        return {}
    result = task.result or {}
    feedback = result.get("feedback", {}) if isinstance(result, dict) else {}
    decision = feedback.get("decision", {}) if isinstance(feedback, dict) else {}
    strategy = decision.get("strategy", {}) if isinstance(decision, dict) else {}
    evaluation = feedback.get("evaluation", {}) if isinstance(feedback, dict) else {}
    event = {
        "task_id": task.id,
        "task_type": task.type,
        "status": task.status.value,
        "summary": result.get("summary") if isinstance(result, dict) else None,
        "error": task.error,
        "capability_id": decision.get("selected_capability_id"),
        "strategy_id": strategy.get("strategy_id") if isinstance(strategy, dict) else None,
        "strategy_reasons": strategy.get("reasons", []) if isinstance(strategy, dict) else [],
        "evaluation_verdict": evaluation.get("verdict") if isinstance(evaluation, dict) else None,
        "evaluation_score": _safe_float(evaluation.get("score")) if isinstance(evaluation, dict) and evaluation.get("score") is not None else None,
        "evaluation_reasons": evaluation.get("reasons", []) if isinstance(evaluation, dict) else [],
        "evaluation_metrics": evaluation.get("metrics", {}) if isinstance(evaluation, dict) else {},
        "candidate_scores": decision.get("scores", []) if isinstance(decision, dict) else [],
    }
    category, hints = _classify_review_case(
        status=event["status"],
        error=event["error"],
        verdict=event["evaluation_verdict"],
        evaluation_reasons=event["evaluation_reasons"],
        evaluation_metrics=event["evaluation_metrics"],
        candidate_scores=event["candidate_scores"],
        capability_id=event["capability_id"],
        strategy_id=event["strategy_id"],
        plugin_policy=plugin_policy,
    )
    event["issue_category"] = category
    event["issue_hints"] = hints
    event["recommended_actions"] = _recommend_actions(
        category=category,
        task_type=event["task_type"],
        capability_id=event["capability_id"],
        strategy_id=event["strategy_id"],
        plugin_policy=plugin_policy,
    )
    return event


def _diagnose_research_sample(task_queue, tenant_id: str, sample: dict, plugin_policy: dict) -> dict:
    analyze_task = latest_sample_task(task_queue, tenant_id, sample, "analyze")
    reconstruct_task = latest_sample_task(task_queue, tenant_id, sample, "reconstruct")
    analyze_diag = _extract_task_diagnostics(analyze_task, plugin_policy)
    reconstruct_diag = _extract_task_diagnostics(reconstruct_task, plugin_policy)

    diagnosis = {
        "sample_path": sample.get("source_dir"),
        "bundle_path": sample.get("bundle_path"),
        "sample_signature": sample.get("sample_signature"),
        "analyze": analyze_diag,
        "reconstruct": reconstruct_diag,
        "research_state": "idle",
        "next_action": "等待样本或策略变化后继续观察",
        "stable": False,
    }

    if not analyze_diag:
        diagnosis["research_state"] = "discovering"
        diagnosis["next_action"] = "先完成 analyze，建立基础识别结果"
        return diagnosis

    if analyze_diag.get("status") == "failed":
        diagnosis["research_state"] = "blocked"
        diagnosis["next_action"] = (analyze_diag.get("recommended_actions") or ["修复 analyze 执行链路"])[0]
        return diagnosis

    if not reconstruct_diag:
        diagnosis["research_state"] = "planning"
        diagnosis["next_action"] = "继续执行 reconstruct，验证是否能形成可恢复产物"
        return diagnosis

    if reconstruct_diag.get("status") == "failed":
        diagnosis["research_state"] = "blocked"
        diagnosis["next_action"] = (reconstruct_diag.get("recommended_actions") or ["修复 reconstruct 执行链路"])[0]
        return diagnosis

    verdict = reconstruct_diag.get("evaluation_verdict")
    if verdict == "pass":
        reconstruct_issue = reconstruct_diag.get("issue_category")
        if reconstruct_issue == "partial_recovery":
            diagnosis["research_state"] = "observing"
            diagnosis["next_action"] = (reconstruct_diag.get("recommended_actions") or ["继续观察组件恢复质量"])[0]
            return diagnosis
        if reconstruct_issue == "observation_needed":
            diagnosis["research_state"] = "observing"
            diagnosis["stable"] = True
            diagnosis["next_action"] = (reconstruct_diag.get("recommended_actions") or ["继续收集更多真实样本，确认是否稳定"])[0]
            return diagnosis
        diagnosis["research_state"] = "stable"
        diagnosis["stable"] = True
        diagnosis["next_action"] = "继续收集更多真实样本，验证当前策略是否仍然稳定"
        return diagnosis

    diagnosis["research_state"] = "researching"
    diagnosis["next_action"] = (reconstruct_diag.get("recommended_actions") or ["进入复盘并生成实验计划"])[0]
    return diagnosis


def _make_learning_task_id(tenant_id: str, sample: dict) -> str:
    sample_key = sample.get("sample_signature") or sample.get("source_dir") or sample.get("bundle_path") or tenant_id
    return f"{tenant_id}:{hashlib.sha1(str(sample_key).encode('utf-8')).hexdigest()[:12]}"


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _trim_candidate_text(value: str | None, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _draft_learning_signature(learning_task: dict) -> str:
    if not isinstance(learning_task, dict):
        return ""
    seed = "::".join([
        str(learning_task.get("tenant_id") or "default"),
        str(learning_task.get("mission_kind") or "mission"),
        str(learning_task.get("mission_node_id") or learning_task.get("node_id") or "node"),
        str(learning_task.get("bundle_path") or learning_task.get("source_dir") or learning_task.get("work_type_id") or ""),
    ])
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _normalize_learning_signature(value: dict | None) -> dict:
    payload = value if isinstance(value, dict) else {}
    metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics"), dict) else {}
    return {
        "issue_category": payload.get("issue_category"),
        "strategy_id": payload.get("strategy_id"),
        "capability_id": payload.get("capability_id"),
        "task_type": payload.get("task_type"),
        "components_bucket": (
            "zero"
            if int(metrics.get("components", 0) or 0) == 0
            else "few"
            if int(metrics.get("components", 0) or 0) <= 3
            else "many"
        ),
        "has_target_dir": bool(metrics.get("has_target_dir")),
        "framework_count": int(metrics.get("framework_count", 0) or 0),
        "pattern_count": int(metrics.get("pattern_count", 0) or 0),
        "confidence_band": (
            "low"
            if _safe_float(metrics.get("confidence"), 0.0) < 0.45
            else "medium"
            if _safe_float(metrics.get("confidence"), 0.0) < 0.75
            else "high"
        ),
    }


def _build_diagnosis_signature(diagnosis: dict) -> dict:
    reconstruct = diagnosis.get("reconstruct", {}) if isinstance(diagnosis, dict) else {}
    analyze = diagnosis.get("analyze", {}) if isinstance(diagnosis, dict) else {}
    source = reconstruct if isinstance(reconstruct, dict) and reconstruct else analyze if isinstance(analyze, dict) else {}
    return _normalize_learning_signature({
        "issue_category": source.get("issue_category"),
        "strategy_id": source.get("strategy_id"),
        "capability_id": source.get("capability_id"),
        "task_type": source.get("task_type"),
        "metrics": source.get("evaluation_metrics", {}) if isinstance(source.get("evaluation_metrics"), dict) else {},
    })


def _build_review_item_signature(item: dict) -> dict:
    latest_run = item.get("experiment_runs", [{}])[0] if isinstance(item.get("experiment_runs"), list) and item.get("experiment_runs") else {}
    latest_summary = latest_run.get("summary", {}) if isinstance(latest_run, dict) else {}
    metrics = {
        "components": 0 if item.get("alert_reason") == "strategy_gap" else latest_summary.get("completed", 0),
        "has_target_dir": True,
        "framework_count": 1 if "javascript" in str(item.get("strategy_id") or "") else 0,
        "pattern_count": 0,
        "confidence": 0.6 if latest_summary.get("status") == "improved" else 0.4,
    }
    return _normalize_learning_signature({
        "issue_category": item.get("alert_reason"),
        "strategy_id": item.get("strategy_id"),
        "capability_id": "builtin.javascript" if "javascript" in str(item.get("strategy_id") or "") else None,
        "task_type": "reconstruct" if "reconstruct" in str(item.get("strategy_id") or "") else None,
        "metrics": metrics,
    })


def _find_review_item_signature(workspace: Path, tenant_id: str, strategy_id: str | None) -> dict | None:
    if not strategy_id:
        return None
    items = _load_review_queue(workspace, tenant_id)
    target = next((item for item in items if isinstance(item, dict) and item.get("strategy_id") == strategy_id), None)
    if not isinstance(target, dict):
        return None
    return _build_review_item_signature(target)


def _score_signature_similarity(current_signature: dict, historical_signature: dict) -> tuple[float, list[str]]:
    if not isinstance(current_signature, dict) or not isinstance(historical_signature, dict):
        return 0.0, []

    score = 0.0
    reasons: list[str] = []
    weighted_keys = [
        ("issue_category", 0.32, "issue"),
        ("strategy_id", 0.24, "strategy"),
        ("capability_id", 0.12, "capability"),
        ("task_type", 0.1, "task"),
        ("components_bucket", 0.1, "components"),
        ("confidence_band", 0.06, "confidence"),
        ("has_target_dir", 0.03, "target_dir"),
        ("framework_count", 0.02, "framework"),
        ("pattern_count", 0.01, "pattern"),
    ]
    for key, weight, label in weighted_keys:
        current = current_signature.get(key)
        historical = historical_signature.get(key)
        if current is None or historical is None:
            continue
        if current == historical:
            score += weight
            reasons.append(f"{label}_match")
    return round(min(score, 1.0), 3), reasons




def _summarize_experiment_run(task_queue, run: dict) -> dict:
    source_task_ids = run.get("source_task_ids", []) if isinstance(run.get("source_task_ids"), list) else []
    task_ids = run.get("task_ids", []) if isinstance(run.get("task_ids"), list) else []
    replay_tasks = [task_queue.get_task(task_id) for task_id in task_ids]
    source_tasks = [task_queue.get_task(task_id) for task_id in source_task_ids]

    completed = 0
    pending = 0
    success = 0
    review = 0
    failed = 0
    improved_count = 0
    regressed_count = 0
    unchanged_count = 0
    replay_scores = []
    source_scores = []

    source_map = {task.id: task for task in source_tasks if task}
    for replay_task in replay_tasks:
        if not replay_task:
            continue

        if replay_task.status.value in {"success", "failed", "cancelled"}:
            completed += 1
        else:
            pending += 1

        verdict = _task_evaluation_verdict(replay_task)
        replay_score = _task_evaluation_score(replay_task)
        if replay_score is not None:
            replay_scores.append(replay_score)

        if replay_task.status.value == "failed":
            failed += 1
        elif verdict == "review":
            review += 1
        elif replay_task.status.value == "success":
            success += 1

        replay_of = (replay_task.payload or {}).get("_replay_of")
        source_task = source_map.get(replay_of)
        source_score = _task_evaluation_score(source_task) if source_task else None
        if source_score is not None:
            source_scores.append(source_score)

        comparison = _build_task_comparison(source_task, replay_task) if source_task else None
        outcome = comparison.get("diff", {}).get("outcome") if comparison else None
        if outcome == "improved":
            improved_count += 1
        elif outcome == "regressed":
            regressed_count += 1
        else:
            unchanged_count += 1

    baseline_avg_score = round(sum(source_scores) / len(source_scores), 3) if source_scores else None
    avg_score = round(sum(replay_scores) / len(replay_scores), 3) if replay_scores else None
    score_delta = None
    if baseline_avg_score is not None and avg_score is not None:
        score_delta = round(avg_score - baseline_avg_score, 3)

    if pending > 0:
        status = "running"
        recommended_action = "仍有实验任务在执行，先等待本轮结果收敛"
    elif improved_count > regressed_count and failed == 0 and (score_delta or 0) >= 0:
        status = "improved"
        recommended_action = "本轮实验表现正向，可以进入策略固化或下一轮验证"
    elif regressed_count > 0 or failed > 0:
        status = "regressed"
        recommended_action = "出现退化或失败样本，先不要升级策略，优先复盘回退点"
    else:
        status = "mixed"
        recommended_action = "结果不够明确，建议补更多样本后再决策"

    return {
        "status": status,
        "completed": completed,
        "pending": pending,
        "success": success,
        "review": review,
        "failed": failed,
        "avg_score": avg_score,
        "baseline_avg_score": baseline_avg_score,
        "score_delta": score_delta,
        "improved_count": improved_count,
        "regressed_count": regressed_count,
        "unchanged_count": unchanged_count,
        "recommended_action": recommended_action,
    }



def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title="Evo Admin API",
        description="Evo 平台后台 API",
        version="2.0.0"
    )
    
    # CORS - 允许前端访问（开发环境）
    origins = [
        "http://localhost:5173",  # Vite 开发服务器
        "http://localhost:5174",
        "http://127.0.0.1:5173",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,  # 关键：允许携带 cookie
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Set-Cookie"],  # 暴露 Set-Cookie 头
    )
    
    # 初始化组件
    repo_workspace = Path(__file__).resolve().parents[2]
    env_workspace = str(os.getenv("EVO_ADMIN_WORKSPACE") or "").strip()
    workspace = repo_workspace
    if env_workspace:
        env_path = Path(env_workspace).expanduser()
        env_has_local_executor = (env_path / "executors" / "toutiao" / "scripts" / "cli.py").is_file()
        if env_has_local_executor:
            workspace = env_path
    workspace.mkdir(parents=True, exist_ok=True)
    global _sessions_file
    _sessions_file = workspace / ".admin" / "sessions.json"
    _mission_action_runtime_ref["build_mission_actions"] = create_mission_action_runtime_bindings(
        normalize_string_list=lambda value: [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else [],
        task_priority_cls=TaskPriority,
        mission_action_handlers=register_builtin_worker_mission_action_handlers(workspace=workspace),
        context_resolvers=build_mission_context_resolvers(workspace),
    )["build_mission_actions"]
    _load_sessions()
    
    # 自动初始化 MySQL 表（如果不存在）
    if MYSQL_AVAILABLE:
        try:
            db.init_tables()
            print(f"✅ MySQL 已连接: {db.host}:{db.port}/{db.db_name}")
        except Exception as e:
            print(f"⚠️ MySQL 连接失败: {e}")
            print(f"   请检查 DB_HOST/DB_PASSWORD 配置")
    else:
        print("⚠️ pymysql 未安装，用户登录将使用本地文件模式")
        print("   如需 MySQL，运行: pip3 install pymysql")
    
    config = get_distributed_config()
    task_queue = get_task_queue(workspace, max_workers=2)
    task_queue.start()
    
    # 注册项目级能力包
    capability_registry = register_project_capabilities(workspace, get_capability_registry())
    register_project_orchestration(workspace)
    project_packages = load_project_packages(workspace)
    plugin_summary = PluginLoader(capability_registry=capability_registry).load_default(workspace)
    decision_engine = DecisionEngine(workspace, capability_registry)
    mission_planner = MissionPlanner(workspace, capability_registry)
    tenant_manager = TenantManager(workspace)
    if plugin_summary.loaded:
        print(f"✅ 已加载插件: {[item.plugin_name for item in plugin_summary.loaded]}")
    if plugin_summary.skipped:
        print(f"⚠️ 跳过插件: {plugin_summary.skipped}")
    if project_packages.get("packages"):
        enabled_packages = [
            str(item.get("package_id") or item.get("adapter") or "unknown")
            for item in project_packages["packages"]
            if isinstance(item, dict) and bool(item.get("enabled", True))
        ]
        print(f"✅ 已启用项目能力包: {enabled_packages}")
    
    intelligence_runtime = create_intelligence_bootstrap_runtime_bindings(
        task_priority_cls=TaskPriority,
        task_status_cls=TaskStatus,
        trim_candidate_text=_trim_candidate_text,
        safe_float=_safe_float,
        record_growth_event=_record_growth_event,
        record_member_experience_journal=_record_member_experience_journal,
        list_platform_strategy_promotions=_list_platform_strategy_promotions,
        find_review_item_signature=_find_review_item_signature,
        task_evaluation_score=task_evaluation_score,
        get_platform_shared_root=_get_platform_shared_root,
        build_review_item_signature=_build_review_item_signature,
        load_review_queue=_load_review_queue,
        save_review_queue=_save_review_queue,
        task_strategy_id=task_strategy_id,
        task_evaluation_verdict=task_evaluation_verdict,
        generate_review_draft=generate_review_draft,
        generate_review_experiment_plan=generate_review_experiment_plan,
        run_review_experiment=run_review_experiment,
        build_strategy_upgrade_candidate=build_strategy_upgrade_candidate,
        maybe_auto_accept_upgrade_candidate=maybe_auto_accept_upgrade_candidate,
        refresh_review_queue_experiment_runs=refresh_review_queue_experiment_runs,
        advance_background_research_for_tenant=advance_background_research_for_tenant,
        summarize_experiment_run=_summarize_experiment_run,
        record_experiment_run_validations=_record_experiment_run_validations,
        update_upgrade_candidate_decision=update_upgrade_candidate_decision,
        rollback_strategy_override=rollback_strategy_override,
        enqueue_strategy_review=enqueue_strategy_review,
        auto_enqueue_review_cases=auto_enqueue_review_cases,
        auto_prepare_review_entries=auto_prepare_review_entries,
        auto_promote_review_entries=auto_promote_review_entries,
        classify_review_case=_classify_review_case,
        recommend_actions=_recommend_actions,
        build_operation_experience_timeline=build_operation_experience_timeline,
        load_autonomy_runtime=_load_autonomy_runtime,
        load_learning_tasks=_load_learning_tasks,
        normalize_child_members_runtime=_normalize_child_members_runtime,
        normalize_feedback_monitor_runtime=_normalize_feedback_monitor_runtime,
        save_autonomy_runtime=_save_autonomy_runtime,
        save_learning_tasks=_save_learning_tasks,
        discover_javascript_research_samples=discover_javascript_research_samples,
        auto_submit_javascript_research_tasks=auto_submit_javascript_research_tasks,
        diagnose_research_sample=_diagnose_research_sample,
        auto_draft_stable_experience_skills=_auto_draft_stable_experience_skills,
        advance_background_self_media_autonomy_for_tenant=advance_background_self_media_autonomy_for_tenant,
        get_self_media_git_export_status=lambda tenant_id: _get_self_media_git_export_status(tenant_id),
        advance_background_feedback_monitor_for_tenant=advance_background_feedback_monitor_for_tenant,
        make_learning_task_id=_make_learning_task_id,
        build_diagnosis_signature=_build_diagnosis_signature,
        score_signature_similarity=_score_signature_similarity,
        latest_sample_task=latest_sample_task,
        parse_iso_datetime=_parse_iso_datetime,
        draft_learning_signature=_draft_learning_signature,
        build_task_comparison=_build_task_comparison,
        record_replay_validation=_record_replay_validation,
        build_snapshot_signature=_build_snapshot_signature,
    )
    _self_media = intelligence_runtime["self_media"]
    _strategy = intelligence_runtime["strategy"]
    _build_evolution_overview = intelligence_runtime["build_evolution_overview"]
    _background_runtime = intelligence_runtime["background_runtime"]
    _mission_app_runtime = intelligence_runtime["mission_app_runtime"]
    _git_knowledge = intelligence_runtime["git_knowledge"]
    _external_learning = intelligence_runtime["external_learning"]
    _learning = intelligence_runtime["learning"]
    _platform_shared_seed_recommendations = intelligence_runtime["evolution_runtime"]["platform_shared_seed_recommendations"]
    _apply_platform_shared_seeds = intelligence_runtime["evolution_runtime"]["apply_platform_shared_seeds"]
    _build_mission_next_cycle_plan = _mission_app_runtime["build_mission_next_cycle_plan"]
    _build_mission_growth_timeline = _mission_app_runtime["build_mission_growth_timeline"]
    _sanitize_repo_name = _git_knowledge["sanitize_repo_name"]
    _resolve_git_runtime_config = _git_knowledge["resolve_git_runtime_config"]
    _get_git_provider_instance = _git_knowledge["get_git_provider_instance"]
    _get_tenant_git_repo = _git_knowledge["get_tenant_git_repo"]
    _build_tenant_knowledge_containers = _git_knowledge["build_tenant_knowledge_containers"]
    _normalize_git_knowledge_payload = _git_knowledge["normalize_git_knowledge_payload"]
    _load_enterprise_repo_index = _git_knowledge["load_enterprise_repo_index"]
    _save_enterprise_repo_index = _git_knowledge["save_enterprise_repo_index"]
    _summarize_enterprise_repo_index = _git_knowledge["summarize_enterprise_repo_index"]
    _scan_enterprise_repo_contents = _git_knowledge["scan_enterprise_repo_contents"]
    _build_enterprise_repo_index_template = _git_knowledge["build_enterprise_repo_index_template"]
    _build_external_learning_plan = _external_learning["build_external_learning_plan"]
    _execute_learning_task = _external_learning["execute_learning_task"]
    _refresh_runtime_learning_tasks = _learning["refresh_runtime_learning_tasks"]
    _build_historical_learning_tasks = _learning["build_historical_learning_tasks"]
    _trigger_learning_task_validation = _learning["trigger_learning_task_validation"]
    _refresh_learning_task = _learning["refresh_learning_task"]
    _background_javascript_research_loop = _background_runtime["background_javascript_research_loop"]
    _probe_toutiao_connector = _self_media["probe_toutiao_connector"]
    _run_toutiao_analytics = _self_media["run_toutiao_analytics"]
    _run_toutiao_executor_cli = _self_media["run_toutiao_executor_cli"]
    _describe_toutiao_executor_registry = _self_media["describe_toutiao_executor_registry"]
    _load_recent_toutiao_automation_experiences = _self_media["load_recent_toutiao_automation_experiences"]
    _extract_feedback_entries_from_result = _self_media["extract_feedback_entries_from_result"]
    _safe_percent_value = _self_media["safe_percent_value"]
    _pick_top_distribution_item = _self_media["pick_top_distribution_item"]
    _top_region_entries = _self_media["top_region_entries"]
    _run_toutiao_comment_list = _self_media["run_toutiao_comment_list"]
    _run_toutiao_comment_reply = _self_media["run_toutiao_comment_reply"]
    _get_toutiao_account_identity = _self_media["get_toutiao_account_identity"]
    _list_toutiao_accounts = _self_media["list_toutiao_accounts"]
    _begin_toutiao_account_login = _self_media["begin_toutiao_account_login"]
    _launch_toutiao_account_login = _self_media["launch_toutiao_account_login"]
    _get_toutiao_login_session = _self_media["get_toutiao_login_session"]
    _list_toutiao_login_sessions = _self_media["list_toutiao_login_sessions"]
    _confirm_toutiao_account_login = _self_media["confirm_toutiao_account_login"]
    _update_toutiao_account = _self_media["update_toutiao_account"]
    _logout_toutiao_account = _self_media["logout_toutiao_account"]

    autonomy_stop_event = threading.Event()
    autonomy_thread = threading.Thread(
        target=_background_javascript_research_loop,
        args=(workspace, task_queue, plugin_summary, tenant_manager, autonomy_stop_event),
        daemon=True,
        name="evo-js-research-loop",
    )

    def _sanitize_git_slug(value: str, fallback: str) -> str:
        safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "").strip())
        while "--" in safe:
            safe = safe.replace("--", "-")
        safe = safe.strip("-")
        return safe or fallback

    def _resolve_self_media_git_repo(tenant_id: str) -> tuple[str, str, str, str]:
        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        repos = git_knowledge.get("repos", {}) if isinstance(git_knowledge, dict) else {}
        repo_key = next(
            (
                key for key in ("toutiao", "reports", "experiences", "config")
                if isinstance(repos, dict) and isinstance(repos.get(key), dict) and repos.get(key, {}).get("full_name")
            ),
            "knowledge",
        )
        target_repo, target_url = _get_tenant_git_repo(
            tenant_manager,
            tenant_id,
            repo_key,
            config.knowledge.full_name,
            config.knowledge.url,
        )
        branch = "master"
        if isinstance(repos, dict) and isinstance(repos.get(repo_key), dict):
            branch = str(repos.get(repo_key, {}).get("branch") or "master").strip() or "master"
        return repo_key, target_repo, target_url, branch

    def _get_self_media_git_export_status(tenant_id: str) -> dict:
        token = _get_background_gitee_token()
        if not token or token == "your_real_token_here":
            return {
                "status": "blocked",
                "reason": "missing_gitee_token",
                "token_available": False,
                "repo_key": None,
                "target_repo": None,
                "branch": None,
                "next_action": "先绑定 Gitee 个人令牌，或配置服务端 GITEE_TOKEN",
            }
        repo_key, target_repo, target_url, branch = _resolve_self_media_git_repo(tenant_id)
        if not target_repo:
            return {
                "status": "blocked",
                "reason": "missing_git_repo",
                "token_available": True,
                "repo_key": repo_key,
                "target_repo": None,
                "branch": None,
                "next_action": "先初始化租户 Git knowledge 仓库，建议补齐 toutiao 仓",
            }
        return {
            "status": "ready",
            "reason": None,
            "token_available": True,
            "repo_key": repo_key,
            "target_repo": target_repo,
            "target_url": target_url,
            "branch": branch,
            "next_action": "环境就绪，允许自媒体产物自动入库",
        }

    def _build_self_media_git_exports(task, result: dict) -> list[dict]:
        if not isinstance(result, dict):
            return []
        payload = task.payload if isinstance(task.payload, dict) else {}
        task_type = str(getattr(task, "type", "") or "").strip()
        now = datetime.now()
        date_prefix = now.strftime("%Y%m%d")
        stamp = now.strftime("%Y%m%d_%H%M%S")
        account_id = str(result.get("account") or payload.get("account_id") or "default").strip() or "default"
        exports: list[dict] = []

        if task_type == "operation_publish_draft":
            publish_result = result.get("result", {}) if isinstance(result.get("result"), dict) else {}
            article_title = str(result.get("article_title") or payload.get("article_title") or payload.get("topic") or "toutiao-article").strip()
            article_slug = _sanitize_git_slug(article_title, f"article-{task.id}")
            article_path = str(publish_result.get("article_path") or "").strip()
            draft_path = str(publish_result.get("draft_path") or "").strip()
            for local_path in (article_path, draft_path):
                if not local_path:
                    continue
                source_path = Path(local_path)
                if not source_path.is_file():
                    continue
                remote_dir = "articles" if source_path.suffix.lower() == ".md" else "drafts"
                exports.append({
                    "file_path": f"{remote_dir}/{date_prefix}/{source_path.name}",
                    "content": source_path.read_text(encoding="utf-8"),
                })
            metadata = {
                "task_id": task.id,
                "task_type": task_type,
                "tenant_id": str(task.tenant_id or "default"),
                "account_id": account_id,
                "article_title": result.get("article_title"),
                "publish_content_type": result.get("publish_content_type"),
                "insight_summary": result.get("insight_summary") or result.get("message"),
                "draft_generation": result.get("draft_generation"),
                "result": publish_result,
                "exported_at": now.isoformat(),
            }
            exports.append({
                "file_path": f"exports/publish/{date_prefix}/{stamp}_{article_slug}.json",
                "content": json.dumps(metadata, indent=2, ensure_ascii=False),
            })
            return exports

        if task_type in {"operation_analytics", "operation_feedback_collect", "operation_feedback_review"}:
            kind = "analytics" if task_type == "operation_analytics" else "feedback"
            suffix = _sanitize_git_slug(
                str(result.get("analytics_type") or payload.get("analytics_type") or task_type),
                task_type,
            )
            metadata = {
                "task_id": task.id,
                "task_type": task_type,
                "tenant_id": str(task.tenant_id or "default"),
                "account_id": account_id,
                "payload": payload,
                "result": result,
                "exported_at": now.isoformat(),
            }
            exports.append({
                "file_path": f"{kind}/{date_prefix}/{stamp}_{suffix}_{task.id}.json",
                "content": json.dumps(metadata, indent=2, ensure_ascii=False),
            })
        return exports

    def _build_self_media_git_index_entries(task, result: dict, exports: list[dict]) -> list[dict]:
        payload = task.payload if isinstance(task.payload, dict) else {}
        task_type = str(getattr(task, "type", "") or "").strip()
        account_id = str(result.get("account") or payload.get("account_id") or "default").strip() or "default"
        summary = str(result.get("insight_summary") or result.get("message") or "").strip()
        entries: list[dict] = []
        for item in exports:
            file_path = str(item.get("file_path") or "").strip()
            if not file_path:
                continue
            entry_type = "article" if file_path.endswith(".md") else ("report" if file_path.endswith(".json") else "artifact")
            title = str(result.get("article_title") or payload.get("topic") or task_type).strip() or task_type
            if "analytics/" in file_path:
                title = f"Toutiao analytics / {str(result.get('analytics_type') or payload.get('analytics_type') or 'summary')}"
                entry_type = "analytics"
            elif "feedback/" in file_path:
                title = f"Toutiao feedback / {task_type}"
                entry_type = "feedback"
            entries.append({
                "id": f"self_media:{task.id}:{file_path}",
                "type": entry_type,
                "title": title,
                "summary": summary or f"Toutiao {task_type}",
                "keywords": [
                    item for item in [
                        "toutiao",
                        task_type,
                        payload.get("publish_content_type"),
                        payload.get("topic"),
                        result.get("analytics_type"),
                        account_id,
                    ]
                    if isinstance(item, str) and item.strip()
                ][:8],
                "path": file_path,
                "source": "self_media_autonomy",
            })
        return entries

    def _export_self_media_artifacts_to_git(task, result: dict) -> dict | None:
        if str(getattr(task, "type", "") or "").strip() not in {
            "operation_publish_draft",
            "operation_analytics",
            "operation_feedback_collect",
            "operation_feedback_review",
        }:
            return None
        token = _get_background_gitee_token()
        if not token or token == "your_real_token_here":
            return {
                "status": "skipped",
                "reason": "missing_gitee_token",
            }
        tenant_id = str(getattr(task, "tenant_id", None) or "default")
        git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
        provider = _get_git_provider_instance(config, git_knowledge)
        repo_key, target_repo, target_url, branch = _resolve_self_media_git_repo(tenant_id)
        exports = _build_self_media_git_exports(task, result)
        if not exports:
            return {
                "status": "skipped",
                "reason": "no_exportable_artifacts",
                "repo_key": repo_key,
            }
        index_entries = _build_self_media_git_index_entries(task, result, exports)

        async def _run_export():
            for item in exports:
                await provider.upsert_text_file(
                    token=token,
                    repo_full_name=target_repo,
                    file_path=str(item["file_path"]),
                    content=str(item["content"]),
                    message=f"Export self media artifact: {task.type} / {task.id}",
                    branch=branch,
                )

            current_index_text = await provider.read_text_file(
                token=token,
                repo_full_name=target_repo,
                file_path="evo/index.json",
                branch=branch,
            )
            current_index = {}
            if current_index_text:
                try:
                    current_index = json.loads(current_index_text)
                except Exception:
                    current_index = {}
            existing_entries = current_index.get("entries", []) if isinstance(current_index.get("entries"), list) else []
            entry_map = {
                str(item.get("id") or ""): item
                for item in existing_entries
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            }
            for item in index_entries:
                entry_map[str(item.get("id") or "")] = item
            merged_entries = list(entry_map.values())
            merged_entries.sort(key=lambda item: str(item.get("path") or ""), reverse=True)
            next_index = {
                "schema_version": "1.0",
                "tenant_id": tenant_id,
                "generated_at": datetime.now().isoformat(),
                "description": "Evo self media autonomous outputs.",
                "entries": merged_entries[:200],
            }
            await provider.upsert_text_file(
                token=token,
                repo_full_name=target_repo,
                file_path="evo/index.json",
                content=json.dumps(next_index, indent=2, ensure_ascii=False),
                message=f"Update self media index: {task.type} / {task.id}",
                branch=branch,
            )
            return next_index

        try:
            next_index = asyncio.run(_run_export())
            repo_index = _load_enterprise_repo_index(workspace, tenant_id)
            repos_state = repo_index.get("repos", {}) if isinstance(repo_index.get("repos"), dict) else {}
            repos_state[repo_key] = {
                "full_name": target_repo,
                "branch": branch,
                "url": target_url,
                "scanned_at": datetime.now().isoformat(),
                "index_path": "evo/index.json",
                "entries": next_index.get("entries", []) if isinstance(next_index, dict) else [],
                "entry_count": len(next_index.get("entries", []) if isinstance(next_index, dict) else []),
            }
            repo_index["repos"] = repos_state
            _save_enterprise_repo_index(workspace, tenant_id, repo_index)
            return {
                "status": "exported",
                "repo_key": repo_key,
                "repo_full_name": target_repo,
                "repo_url": target_url,
                "branch": branch,
                "files": [str(item.get("file_path") or "") for item in exports],
            }
        except Exception as exc:
            reason = str(exc)
            if exports:
                return export_self_media_artifacts_locally(
                    workspace,
                    tenant_id=tenant_id,
                    task_id=str(getattr(task, "id", "") or "unknown"),
                    task_type=str(getattr(task, "type", "") or ""),
                    exports=exports,
                    index_entries=index_entries,
                    remote_reason=reason,
                )
            return {
                "status": "failed",
                "reason": reason,
                "repo_key": repo_key,
                "repo_full_name": target_repo,
            }

    def finalize_operation_result(task, result: dict) -> dict:
        finalized = record_operation_experience(
            workspace,
            task,
            result,
            trim_candidate_text=_trim_candidate_text,
            summarize_analytics_result=lambda payload, analytics_result: summarize_toutiao_analytics_result(
                payload,
                analytics_result,
                safe_float=_safe_float,
                safe_percent_value=_safe_percent_value,
                pick_top_distribution_item=_pick_top_distribution_item,
                top_region_entries=_top_region_entries,
                trim_candidate_text=_trim_candidate_text,
            ),
        )
        if getattr(task, "type", "") == "operation_analytics":
            finance_snapshot = upsert_finance_from_analytics(
                workspace,
                tenant_id=str(getattr(task, "tenant_id", None) or "default"),
                payload=task.payload if isinstance(getattr(task, "payload", None), dict) else {},
                result=finalized,
                analytics_summary=finalized.get("analytics_summary")
                if isinstance(finalized.get("analytics_summary"), dict)
                else None,
            )
            if finance_snapshot:
                finalized["finance_snapshot"] = finance_snapshot
        git_export = _export_self_media_artifacts_to_git(task, finalized)
        if git_export:
            finalized["git_export"] = git_export
        # Commercial intake: mirror worker artifacts onto intake + formal task for workspace UI
        try:
            from admin.intake_runtime import attach_operation_artifacts_to_intake

            tenant_id = str(getattr(task, "tenant_id", None) or "default").strip() or "default"
            autonomy_runtime = _load_autonomy_runtime(workspace, tenant_id)
            attach_info = attach_operation_artifacts_to_intake(
                workspace=workspace,
                runtime=autonomy_runtime,
                queue_task=task,
                operation_result=finalized,
            )
            if attach_info:
                _save_autonomy_runtime(workspace, autonomy_runtime, tenant_id)
                finalized["intake_fulfillment_attach"] = {
                    "intake_id": attach_info.get("intake_id"),
                    "artifact_count": attach_info.get("artifact_count"),
                    "fulfillment_status": attach_info.get("fulfillment_status"),
                }
        except Exception as exc:  # noqa: BLE001 — never fail worker finalize on attach
            finalized["intake_fulfillment_attach_error"] = str(exc)[:200]
        return finalized

    _worker_bootstrap = create_worker_bootstrap_runtime_bindings(
        task_queue=task_queue,
        workspace=workspace,
        decision_engine=decision_engine,
        extract_task_diagnostics=_extract_task_diagnostics,
        finalize_operation_result=finalize_operation_result,
        run_probe_toutiao_connector=_probe_toutiao_connector,
        run_toutiao_analytics=_run_toutiao_analytics,
        run_toutiao_executor_cli=lambda current_workspace, args, payload=None: _run_toutiao_executor_cli(
            current_workspace,
            args,
            timeout=90,
            payload=payload,
        ),
        load_recent_automation_experiences=_load_recent_toutiao_automation_experiences,
        trim_candidate_text=_trim_candidate_text,
        run_comment_list=_run_toutiao_comment_list,
        run_comment_reply=_run_toutiao_comment_reply,
        get_account_identity=_get_toutiao_account_identity,
    )
    worker_runtime = _worker_bootstrap["worker_runtime"]

    @app.on_event("startup")
    async def start_background_research():
        purge_preset_finance_data(workspace)
        purge_preset_project_packages(workspace)
        if not autonomy_thread.is_alive():
            autonomy_thread.start()

    @app.on_event("shutdown")
    async def stop_background_research():
        autonomy_stop_event.set()
        if autonomy_thread.is_alive():
            autonomy_thread.join(timeout=3)
        task_queue.stop()
    
    _default_session_secret = "evo-session-secret-change-in-production"
    _session_secret = str(os.getenv("SESSION_SECRET") or _default_session_secret).strip()
    _secure_cookies = (
        str(os.getenv("EVO_SECURE_COOKIES") or "").strip().lower() in {"1", "true", "yes"}
        or str(os.getenv("EVO_ENV") or "").strip().lower() == "production"
    )
    _spa_dist_index = repo_workspace / "admin-ui" / "dist" / "index.html"

    # ========== 健康检查 ==========
    @app.get("/health")
    async def health():
        warnings: list[str] = []
        if _session_secret == _default_session_secret:
            warnings.append("SESSION_SECRET uses default value")
        if not _spa_dist_index.is_file():
            warnings.append("admin-ui dist not built; run: cd admin-ui && npm run build")
        status = "ok" if not warnings else "degraded"
        return {
            "status": status,
            "service": "evo-admin",
            "version": "2.0.0",
            "checks": {
                "task_queue": bool(task_queue),
                "mysql": bool(MYSQL_AVAILABLE),
                "spa_static": _spa_dist_index.is_file(),
                "secure_cookies": _secure_cookies,
            },
            "warnings": warnings,
        }

    # 统一响应格式
    def success_response(data: dict = None, message: str = "操作成功"):
        return {"code": 0, "success": True, "message": message, "data": data or {}}
    
    def error_response(message: str, code: int = 400):
        return JSONResponse(
            status_code=code,
            content={"code": code, "success": False, "message": message, "data": None}
        )

    @app.get("/api/system/readiness")
    async def system_readiness():
        payload = await health()
        ready = payload["status"] == "ok" and payload["checks"].get("spa_static")
        return success_response({**payload, "ready_for_launch": ready}, "ok")

    def create_session_response(user: dict, message: str = "登录成功") -> JSONResponse:
        session_id = _create_session(user)

        response = JSONResponse(success_response({
            **_serialize_user(user),
            "token": session_id,
        }, message))
        response.set_cookie(
            key="session",
            value=session_id,
            httponly=True,
            samesite="lax",
            secure=_secure_cookies,
            path="/",
            max_age=7 * 24 * 60 * 60,
        )
        return response

    _mission_execution = create_mission_execution_bindings(
        load_learning_tasks=_load_learning_tasks,
        save_learning_tasks=_save_learning_tasks,
        collect_task_verified_skills=_collect_task_verified_skills,
        skill_ids_from_items=_skill_ids_from_items,
        infer_framework_hint_from_delivery=_infer_framework_hint_from_delivery,
        create_mission_delivery_skill_candidate=_create_mission_delivery_skill_candidate,
        safe_float=_safe_float,
        trim_candidate_text=_trim_candidate_text,
        record_growth_event=_record_growth_event,
        build_snapshot_signature=_build_snapshot_signature,
        normalize_string_list=_normalize_string_list,
        build_external_learning_plan=_build_external_learning_plan,
        execute_learning_task=_execute_learning_task,
        make_learning_task_id=_make_learning_task_id,
        extract_task_snapshot=_extract_task_snapshot,
        resolve_effective_growth_policy=_resolve_effective_growth_policy,
        growth_policy_decision_label=_growth_policy_decision_label,
        effective_platform_promotion_status=_effective_platform_promotion_status,
        mission_post_action_handlers=register_builtin_worker_mission_post_action_handlers(workspace=workspace),
        mission_summary_handlers=register_builtin_worker_mission_summary_handlers(workspace=workspace),
    )
    _refresh_mission_run_runtime = _mission_execution["refresh_mission_run"]

    register_system_runtime_routes(
        app,
        workspace=workspace,
        tenant_manager=tenant_manager,
        task_queue=task_queue,
        plugin_summary=plugin_summary,
        worker_runtime=worker_runtime,
        builtin_worker_manifests=builtin_worker_manifests,
        load_worker_registry_config=load_worker_registry_config,
        save_worker_registry_config=save_worker_registry_config,
        load_autonomy_runtime=_load_autonomy_runtime,
        create_employee_member_runtime=_create_employee_member_runtime,
        normalize_parent_profile_runtime=_normalize_parent_profile_runtime,
        normalize_child_agent_runtime=_normalize_child_agent_runtime,
        normalize_child_members_runtime=_normalize_child_members_runtime,
        normalize_feedback_monitor_runtime=_normalize_feedback_monitor_runtime,
        save_autonomy_runtime=_save_autonomy_runtime,
        refresh_runtime_learning_tasks=_refresh_runtime_learning_tasks,
        build_historical_learning_tasks=_build_historical_learning_tasks,
        trigger_learning_task_validation=_trigger_learning_task_validation,
        describe_toutiao_executor_registry=_describe_toutiao_executor_registry,
        get_toutiao_account_identity=_get_toutiao_account_identity,
        get_user_gitee_token=_get_user_gitee_token,
        get_git_provider_instance=_get_git_provider_instance,
        get_tenant_git_repo=_get_tenant_git_repo,
        config=config,
        load_mission_runs=load_mission_runs,
        load_review_queue=_load_review_queue,
        list_platform_strategy_promotions=_list_platform_strategy_promotions,
        record_member_experience_journal=_record_member_experience_journal,
        build_evolution_overview=_build_evolution_overview,
        success_response=success_response,
        error_response=error_response,
    )

    register_git_knowledge_routes(
        app,
        workspace=workspace,
        config=config,
        tenant_manager=tenant_manager,
        task_queue=task_queue,
        plugin_summary=plugin_summary,
        get_user_gitee_token=_get_user_gitee_token,
        get_git_provider_instance=_get_git_provider_instance,
        resolve_git_runtime_config=_resolve_git_runtime_config,
        load_enterprise_repo_index=_load_enterprise_repo_index,
        save_enterprise_repo_index=_save_enterprise_repo_index,
        summarize_enterprise_repo_index=_summarize_enterprise_repo_index,
        build_tenant_knowledge_containers=_build_tenant_knowledge_containers,
        build_enterprise_repo_index_template=_build_enterprise_repo_index_template,
        scan_enterprise_repo_contents=_scan_enterprise_repo_contents,
        normalize_git_knowledge_payload=_normalize_git_knowledge_payload,
        sanitize_repo_name=_sanitize_repo_name,
        get_tenant_git_repo=_get_tenant_git_repo,
        load_autonomy_runtime=_load_autonomy_runtime,
        build_evolution_overview=_build_evolution_overview,
        success_response=success_response,
        error_response=error_response,
    )

    register_catalog_routes(
        app,
        workspace=workspace,
        plugin_summary=plugin_summary,
        capability_registry=capability_registry,
        capability_type_label=capability_type_label,
        capability_type_catalog=capability_type_catalog,
        mission_kind_templates=MISSION_KIND_TEMPLATES,
        load_project_packages=load_project_packages,
        save_project_packages=save_project_packages,
        load_work_types=load_work_types,
        save_work_types=save_work_types,
        builtin_worker_manifests=builtin_worker_manifests,
        load_worker_registry_config=load_worker_registry_config,
        build_project_package_runtime_entries=build_project_package_runtime_entries,
        build_work_type_runtime_index=build_work_type_runtime_index,
        success_response=success_response,
    )

    register_tenant_policy_routes(
        app,
        tenant_manager=tenant_manager,
        plugin_summary=plugin_summary,
        success_response=success_response,
        error_response=error_response,
    )

    register_task_tool_routes(
        app,
        workspace=workspace,
        task_queue=task_queue,
        task_priority_cls=TaskPriority,
        build_task_comparison=_build_task_comparison,
        record_replay_validation=_record_replay_validation,
        success_response=success_response,
        error_response=error_response,
    )

    register_auth_routes(
        app,
        db=db,
        mysql_available=MYSQL_AVAILABLE,
        task_queue=task_queue,
        sessions=_sessions,
        create_session_response=create_session_response,
        get_session_user=lambda request: _serialize_user(_get_session_user(request)) if _get_session_user(request) else None,
        delete_session=_delete_session,
        persist_sessions=_persist_sessions,
        success_response=success_response,
        error_response=error_response,
    )

    register_evolution_strategy_routes(
        app,
        workspace=workspace,
        task_queue=task_queue,
        tenant_manager=tenant_manager,
        plugin_summary=plugin_summary,
        build_evolution_overview=_build_evolution_overview,
        load_review_queue=_load_review_queue,
        enqueue_strategy_review=_strategy["enqueue_strategy_review"],
        generate_review_draft=_strategy["generate_review_draft"],
        generate_review_experiment_plan=_strategy["generate_review_experiment_plan"],
        run_review_experiment=_strategy["run_review_experiment"],
        update_upgrade_candidate_decision=_strategy["update_upgrade_candidate_decision"],
        promote_review_entry_to_platform=_strategy["promote_review_entry_to_platform"],
        save_review_queue=_save_review_queue,
        list_platform_strategy_promotions=_list_platform_strategy_promotions,
        platform_shared_seed_recommendations=_platform_shared_seed_recommendations,
        apply_platform_shared_seeds=_apply_platform_shared_seeds,
        rollback_strategy_override=_strategy["rollback_strategy_override"],
        success_response=success_response,
        error_response=error_response,
    )

    def _append_member_reflection_message(
        relationship_center: dict,
        *,
        member_id: str,
        content: str,
        mission_run_id: str,
        signature: str,
    ) -> None:
        threads = relationship_center.get("conversation_threads")
        if not isinstance(threads, list):
            threads = []
        thread_id = f"trainer:{member_id}"
        thread = next(
            (
                item for item in threads
                if isinstance(item, dict) and str(item.get("thread_id") or "") == thread_id
            ),
            None,
        )
        if thread is None:
            thread = {
                "thread_id": thread_id,
                "participants": ["talent_development_officer", member_id],
                "messages": [],
            }
            threads.append(thread)
        messages = thread.get("messages")
        if not isinstance(messages, list):
            messages = []
        if any(
            isinstance(item, dict)
            and str(item.get("sender_member_id") or "") == member_id
            and str((item.get("metadata") or {}).get("source_mission_run_id") or "") == mission_run_id
            and str((item.get("metadata") or {}).get("mission_sync_signature") or "") == signature
            for item in messages
        ):
            relationship_center["conversation_threads"] = threads[-40:]
            return
        messages.append({
            "message_id": f"{thread_id}:{int(datetime.now().timestamp() * 1000)}",
            "sender_member_id": member_id,
            "sender_role": "child_domain_expert",
            "message_type": "mission_reflection",
            "content": content,
            "metadata": {
                "source": "mission_runtime_sync",
                "source_mission_run_id": mission_run_id,
                "mission_sync_signature": signature,
            },
            "created_at": datetime.now().isoformat(),
        })
        thread["messages"] = messages[-40:]
        relationship_center["conversation_threads"] = threads[-40:]

    def _append_trainer_growth_comment(
        relationship_center: dict,
        *,
        member: dict,
        mission_run: dict,
        signature: str,
        stage_from: str,
        stage_to: str,
        next_action: str,
        current_focus: str,
    ) -> None:
        member_id = str(member.get("member_id") or "").strip()
        if not member_id:
            return
        threads = relationship_center.get("conversation_threads")
        if not isinstance(threads, list):
            threads = []
        thread_id = f"trainer:{member_id}"
        thread = next(
            (
                item for item in threads
                if isinstance(item, dict) and str(item.get("thread_id") or "") == thread_id
            ),
            None,
        )
        if thread is None:
            thread = {
                "thread_id": thread_id,
                "participants": ["talent_development_officer", member_id],
                "messages": [],
            }
            threads.append(thread)
        messages = thread.get("messages")
        if not isinstance(messages, list):
            messages = []
        if any(
            isinstance(item, dict)
            and str(item.get("sender_member_id") or "") == "talent_development_officer"
            and str((item.get("metadata") or {}).get("source_mission_run_id") or "") == str(mission_run.get("mission_run_id") or "")
            and str((item.get("metadata") or {}).get("mission_sync_signature") or "") == signature
            and str(item.get("message_type") or "") == "trainer_growth_comment"
            for item in messages
        ):
            relationship_center["conversation_threads"] = threads[-40:]
            return
        role_label = str(
            (member.get("persona", {}) if isinstance(member.get("persona"), dict) else {}).get("role_label")
            or member.get("primary_role")
            or "子女成员"
        ).strip() or "子女成员"
        mission_status = str(mission_run.get("status") or "").strip() or "unknown"
        if mission_status in {"completed", "improved"}:
            content = (
                f"这轮我看到你作为 {role_label} 已经把任务推进到了 {mission_status}，训练阶段也从 {stage_from or '--'} 调整到 {stage_to or '--'}。"
                f" 先别急着换方向，下一轮继续盯住：{next_action or current_focus or '保持当前专业主线'}。"
            )
            policy = "growth_coach_reinforce"
        elif mission_status in {"partially_completed", "validating"}:
            content = (
                f"这轮说明你已经有真实推进，只是还没完全稳定。"
                f" 我先把你的训练阶段推进到 {stage_to or '--'}，接下来重点不是铺新东西，而是把 {current_focus or next_action or '当前主线'} 再验证一轮。"
            )
            policy = "growth_coach_stabilize"
        elif mission_status in {"needs_learning", "regressed", "failed", "blocked"}:
            content = (
                f"这轮我先不否定你的专业方向，但会把它当成一次训练信号。"
                f" 你现在先回到 {stage_to or '--'} 阶段，把问题压缩到一个最小可验证点，再继续推进：{next_action or current_focus or '当前主线'}。"
            )
            policy = "growth_coach_correct"
        else:
            content = (
                f"我已经记录下你这轮的岗位进展。"
                f" 当前训练阶段是 {stage_to or '--'}，下一步继续做：{next_action or current_focus or '当前专业主线'}。"
            )
            policy = "growth_coach_steady"
        messages.append({
            "message_id": f"{thread_id}:{int(datetime.now().timestamp() * 1000)}",
            "sender_member_id": "talent_development_officer",
            "sender_role": "talent_development",
            "message_type": "trainer_growth_comment",
            "content": content,
            "metadata": {
                "source": "mission_runtime_sync",
                "source_mission_run_id": str(mission_run.get("mission_run_id") or ""),
                "mission_sync_signature": signature,
                "reply_policy": policy,
                "training_stage_from": stage_from,
                "training_stage_to": stage_to,
                "mission_status": mission_status,
            },
            "created_at": datetime.now().isoformat(),
        })
        thread["messages"] = messages[-40:]
        relationship_center["conversation_threads"] = threads[-40:]

    def _build_member_reflection_from_mission(mission_run: dict, member: dict) -> dict | None:
        if not isinstance(mission_run, dict) or not isinstance(member, dict):
            return None
        status = str(mission_run.get("status") or "").strip()
        if status in {"planning_only", "submitted", "running"}:
            return None
        summary = mission_run.get("summary", {}) if isinstance(mission_run.get("summary"), dict) else {}
        next_cycle_plan = summary.get("next_cycle_plan", {}) if isinstance(summary.get("next_cycle_plan"), dict) else {}
        worker_summary = summary.get("worker_summary", {}) if isinstance(summary.get("worker_summary"), dict) else {}
        role_reflection = worker_summary.get("role_reflection", {}) if isinstance(worker_summary.get("role_reflection"), dict) else {}
        role_summary = str(role_reflection.get("summary") or "").strip()
        role_experiment = str(role_reflection.get("next_experiment") or "").strip()
        focus_points = [
            str(item).strip()
            for item in (next_cycle_plan.get("focus_points", []) if isinstance(next_cycle_plan.get("focus_points"), list) else [])
            if str(item).strip()
        ]
        next_steps = [
            str(item).strip()
            for item in (next_cycle_plan.get("next_steps", []) if isinstance(next_cycle_plan.get("next_steps"), list) else [])
            if str(item).strip()
        ]
        recommended_next_actions = [
            str(item).strip()
            for item in (worker_summary.get("recommended_next_actions", []) if isinstance(worker_summary.get("recommended_next_actions"), list) else [])
            if str(item).strip()
        ]
        evidence_parts: list[str] = []
        if status:
            evidence_parts.append(f"mission状态 {status}")
        if focus_points:
            evidence_parts.append("当前关注 " + "；".join(focus_points[:2]))
        if role_summary:
            evidence_parts.append("岗位判断 " + role_summary)
        if role_experiment:
            evidence_parts.append("岗位实验 " + role_experiment)
        if next_steps:
            evidence_parts.append("下一步 " + "；".join(next_steps[:2]))
        elif recommended_next_actions:
            evidence_parts.append("下一步 " + "；".join(recommended_next_actions[:2]))
        if not evidence_parts:
            return None
        content = "这轮 mission 结束后，我对自己的岗位实践做了复盘：" + "；".join(evidence_parts) + "。"
        signature = hashlib.sha1(
            "|".join([
                str(mission_run.get("mission_run_id") or ""),
                status,
                role_summary,
                role_experiment,
                "||".join(focus_points[:2]),
                "||".join(next_steps[:2]),
                "||".join(recommended_next_actions[:2]),
            ]).encode("utf-8")
        ).hexdigest()[:16]
        next_action = role_experiment or (next_steps[0] if next_steps else "") or (recommended_next_actions[0] if recommended_next_actions else "")
        current_focus = role_summary or (focus_points[0] if focus_points else "") or str(member.get("primary_role") or "").strip()
        return {
            "content": content,
            "signature": signature,
            "next_action": next_action,
            "current_focus": current_focus,
        }

    def _resolve_member_for_mission(mission_run: dict, members: list[dict]) -> dict | None:
        if not isinstance(mission_run, dict):
            return None
        context = mission_run.get("context", {}) if isinstance(mission_run.get("context"), dict) else {}
        runtime_route = mission_run.get("runtime_route", {}) if isinstance(mission_run.get("runtime_route"), dict) else {}
        explicit_member_id = str(
            context.get("member_id")
            or context.get("child_member_id")
            or context.get("target_member_id")
            or ""
        ).strip()
        if explicit_member_id:
            matched = next(
                (item for item in members if isinstance(item, dict) and str(item.get("member_id") or "").strip() == explicit_member_id),
                None,
            )
            if isinstance(matched, dict):
                return matched
        role_hint = str(
            (mission_run.get("work_type", {}) if isinstance(mission_run.get("work_type"), dict) else {}).get("work_type_id")
            or runtime_route.get("primary_worker_id")
            or context.get("runtime_primary_worker_id")
            or ""
        ).strip()
        if role_hint:
            matched = next(
                (
                    item for item in members
                    if isinstance(item, dict)
                    and str(item.get("status") or "active").strip() != "archived"
                    and str(item.get("primary_role") or "").strip() == role_hint
                ),
                None,
            )
            if isinstance(matched, dict):
                return matched
        return None

    def _sync_autonomy_runtime_from_missions(*, workspace: Path, mission_runs: list[dict]) -> list[dict]:
        if not isinstance(mission_runs, list) or not mission_runs:
            return mission_runs
        runtime = _load_autonomy_runtime(workspace)
        runtime_tenant_id = str(runtime.get("tenant_id") or "default").strip() or "default"
        child_members = _normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        members = [item for item in (child_members.get("items") if isinstance(child_members.get("items"), list) else []) if isinstance(item, dict)]
        if not members:
            return mission_runs
        relationship_center = runtime.get("relationship_center", {}) if isinstance(runtime.get("relationship_center"), dict) else {}
        changed = False

        for mission_run in mission_runs:
            if not isinstance(mission_run, dict):
                continue
            member = _resolve_member_for_mission(mission_run, members)
            if not isinstance(member, dict):
                continue
            reflection = _build_member_reflection_from_mission(mission_run, member)
            if not isinstance(reflection, dict):
                continue
            signature = str(reflection.get("signature") or "").strip()
            if signature and signature == str(mission_run.get("member_reflection_sync_signature") or "").strip():
                continue
            member_id = str(member.get("member_id") or "").strip()
            if not member_id:
                continue
            _append_member_reflection_message(
                relationship_center,
                member_id=member_id,
                content=str(reflection.get("content") or "").strip(),
                mission_run_id=str(mission_run.get("mission_run_id") or ""),
                signature=signature,
            )
            growth_state = member.get("growth_state", {}) if isinstance(member.get("growth_state"), dict) else {}
            training_plan = member.get("training_plan", {}) if isinstance(member.get("training_plan"), dict) else {}
            current_jobs = member.get("current_jobs", []) if isinstance(member.get("current_jobs"), list) else []
            next_action = str(reflection.get("next_action") or "").strip()
            current_focus = str(reflection.get("current_focus") or "").strip()
            stage_from = str(training_plan.get("stage") or "").strip() or "profile_initialized"
            stage_to = _member_training_stage_from_mission_status(mission_run.get("status"))
            member["growth_state"] = {
                **growth_state,
                "current_focus": current_focus or growth_state.get("current_focus"),
                "next_goal": next_action or growth_state.get("next_goal"),
                "last_reflection_at": datetime.now().isoformat(),
            }
            member["training_plan"] = {
                **training_plan,
                "stage": stage_to,
                "next_action": next_action or training_plan.get("next_action"),
                "review_after": (datetime.now() + timedelta(hours=24)).isoformat(),
            }
            updated_jobs: list[dict] = []
            matched_job = False
            role_hint = str(member.get("primary_role") or "").strip()
            for job in current_jobs:
                if not isinstance(job, dict):
                    continue
                if str(job.get("job_id") or "").strip() == role_hint:
                    matched_job = True
                    updated_jobs.append({
                        **job,
                        "status": mission_run.get("status") or job.get("status"),
                        "target_outcome": next_action or job.get("target_outcome"),
                    })
                else:
                    updated_jobs.append(job)
            if matched_job:
                member["current_jobs"] = updated_jobs
            if (
                signature != str(mission_run.get("member_growth_event_signature") or "").strip()
                or stage_from != stage_to
            ):
                _record_member_growth_event(
                    workspace,
                    runtime_tenant_id,
                    member=member,
                    mission_run=mission_run,
                    stage_from=stage_from,
                    stage_to=stage_to,
                    summary=str(reflection.get("content") or "").strip(),
                    signature=signature,
                    next_action=next_action,
                    current_focus=current_focus,
                )
            _append_trainer_growth_comment(
                relationship_center,
                member=member,
                mission_run=mission_run,
                signature=signature,
                stage_from=stage_from,
                stage_to=stage_to,
                next_action=next_action,
                current_focus=current_focus,
            )
            mission_run["member_reflection_synced_at"] = datetime.now().isoformat()
            mission_run["member_reflection_sync_signature"] = signature
            mission_run["member_growth_event_signature"] = signature
            mission_run["member_reflection_member_id"] = member_id
            changed = True

        if changed:
            runtime["relationship_center"] = relationship_center
            runtime["child_members"] = {
                "selected_member_id": child_members.get("selected_member_id"),
                "items": members,
            }
            runtime["primary_child_member_id"] = child_members.get("selected_member_id")
            _save_autonomy_runtime(workspace, runtime)
        return mission_runs

    def _resolve_mission_member_context(
        *,
        tenant_id: str,
        work_type_id: str | None,
        mission_kind: str | None,
        context: dict,
    ) -> dict:
        if not isinstance(context, dict):
            context = {}
        existing_member_id = str(
            context.get("member_id")
            or context.get("child_member_id")
            or context.get("target_member_id")
            or ""
        ).strip()
        if existing_member_id:
            return {}
        runtime = _load_autonomy_runtime(workspace)
        child_members = _normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        members = [
            item for item in (child_members.get("items") if isinstance(child_members.get("items"), list) else [])
            if isinstance(item, dict) and str(item.get("status") or "active").strip() != "archived"
        ]
        if not members:
            return {}
        role_hint = str(
            work_type_id
            or context.get("work_type_id")
            or context.get("runtime_primary_worker_id")
            or ""
        ).strip()
        selected_member_id = str(
            runtime.get("primary_child_member_id")
            or child_members.get("selected_member_id")
            or ""
        ).strip()
        selected_member = next(
            (item for item in members if str(item.get("member_id") or "").strip() == selected_member_id),
            None,
        )
        target_member = None
        if role_hint:
            target_member = next(
                (
                    item for item in members
                    if str(item.get("primary_role") or "").strip() == role_hint
                ),
                None,
            )
        if target_member is None and isinstance(selected_member, dict) and str(selected_member.get("primary_role") or "").strip() != "talent_development":
            target_member = selected_member
        if target_member is None:
            target_member = next(
                (
                    item for item in members
                    if str(item.get("primary_role") or "").strip() != "talent_development"
                ),
                None,
            )
        if not isinstance(target_member, dict):
            return {}
        member_id = str(target_member.get("member_id") or "").strip()
        if not member_id:
            return {}
        return {
            "member_id": member_id,
            "member_name": str(target_member.get("name") or "").strip() or None,
            "member_primary_role": str(target_member.get("primary_role") or "").strip() or None,
            "member_resolution_source": (
                "role_match"
                if role_hint and str(target_member.get("primary_role") or "").strip() == role_hint
                else "selected_member"
                if isinstance(selected_member, dict) and str(selected_member.get("member_id") or "").strip() == member_id
                else "first_active_domain_member"
            ),
            "tenant_id": tenant_id,
            "mission_kind": mission_kind or None,
        }

    _mission_bootstrap = create_mission_bootstrap_runtime_bindings(
        workspace=workspace,
        task_queue=task_queue,
        tenant_manager=tenant_manager,
        mission_planner=mission_planner,
        upsert_plan_learning_tasks=_upsert_plan_learning_tasks,
        error_response=error_response,
        build_mission_actions=_mission_action_runtime_ref["build_mission_actions"],
        refresh_runtime_learning_tasks=_refresh_runtime_learning_tasks,
        refresh_mission_run=_refresh_mission_run_runtime,
        build_mission_next_cycle_plan=_build_mission_next_cycle_plan,
        build_mission_growth_timeline=_build_mission_growth_timeline,
        resolve_work_type_context=resolve_work_type_context,
        summarize_work_type=summarize_work_type,
        validate_work_type_request=validate_work_type_request,
        resolve_runtime_route=resolve_runtime_route,
        load_work_types=load_work_types,
        builtin_worker_manifests=builtin_worker_manifests,
        load_worker_registry_config=load_worker_registry_config,
        build_project_package_runtime_entries=build_project_package_runtime_entries,
        sync_autonomy_runtime_from_missions=_sync_autonomy_runtime_from_missions,
        resolve_mission_member_context=_resolve_mission_member_context,
    )
    _prepare_mission_work_type_bundle = _mission_bootstrap["prepare_mission_work_type_bundle"]
    _refresh_mission_runs = _mission_bootstrap["refresh_mission_runs"]
    _start_mission = _mission_bootstrap["start_mission"]

    register_mission_routes(
        app,
        workspace=workspace,
        task_queue=task_queue,
        tenant_manager=tenant_manager,
        prepare_mission_work_type_bundle=_prepare_mission_work_type_bundle,
        mission_planner=mission_planner,
        upsert_plan_learning_tasks=_upsert_plan_learning_tasks,
        refresh_mission_runs=_refresh_mission_runs,
        start_mission=_start_mission,
        find_mission_run=find_mission_run,
        derive_follow_up_goal=derive_follow_up_goal,
        derive_follow_up_context=derive_follow_up_context,
        success_response=success_response,
        error_response=error_response,
    )

    register_self_media_routes(
        app,
        workspace=workspace,
        task_queue=task_queue,
        task_priority_normal=TaskPriority.NORMAL,
        list_toutiao_accounts=_list_toutiao_accounts,
        get_toutiao_account_identity=_get_toutiao_account_identity,
        begin_toutiao_account_login=_begin_toutiao_account_login,
        launch_toutiao_account_login=_launch_toutiao_account_login,
        get_toutiao_login_session=_get_toutiao_login_session,
        list_toutiao_login_sessions=_list_toutiao_login_sessions,
        confirm_toutiao_account_login=_confirm_toutiao_account_login,
        update_toutiao_account=_update_toutiao_account,
        logout_toutiao_account=_logout_toutiao_account,
        success_response=success_response,
        error_response=error_response,
    )

    register_finance_routes(
        app,
        workspace=workspace,
        success_response=success_response,
        error_response=error_response,
    )

    spa_enabled = register_spa_static(app, repo_root=repo_workspace)
    if spa_enabled:
        print("✅ 已托管 admin-ui 生产构建 (admin-ui/dist)")
    else:
        @app.get("/")
        async def root_fallback():
            return RedirectResponse(url="/docs", status_code=307)
        print("ℹ️ 未找到 admin-ui/dist，开发模式请使用 Vite :5173 或先 npm run build")

    return app


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
