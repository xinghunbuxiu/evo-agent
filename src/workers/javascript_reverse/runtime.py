from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Callable

from core import Experience, ExperienceStore
from core.task_queue import TaskPriority
from core.tenant import TenantManager


def resolve_javascript_mission_context(context: dict) -> dict:
    if not isinstance(context, dict):
        return {}

    resolved = dict(context)
    raw_candidates = [
        context.get("bundle_path"),
        context.get("source_path"),
        context.get("path"),
        context.get("source_dir"),
    ]

    file_candidate: Path | None = None
    dir_candidates: list[Path] = []
    for value in raw_candidates:
        if not value:
            continue
        candidate = Path(str(value)).expanduser()
        if candidate.is_file():
            file_candidate = candidate
            break
        if candidate.is_dir():
            dir_candidates.append(candidate)

    if file_candidate is None:
        for directory in dir_candidates:
            search_roots = [directory]
            input_root = directory / "input"
            if input_root.is_dir():
                search_roots.append(input_root)
            for root in search_roots:
                matches = sorted(root.rglob("assets/main-*.js"))
                if matches:
                    file_candidate = matches[0]
                    break
            if file_candidate is not None:
                break

    if file_candidate is not None:
        try:
            resolved["bundle_path"] = str(file_candidate.resolve())
        except FileNotFoundError:
            resolved["bundle_path"] = str(file_candidate)
        resolved["source_path"] = resolved["bundle_path"]
        resolved["path"] = resolved["bundle_path"]
        inferred_source_dir = file_candidate.parent.parent if file_candidate.parent.name == "assets" else file_candidate.parent
        resolved["source_dir"] = str(inferred_source_dir)
    elif dir_candidates:
        resolved["source_dir"] = str(dir_candidates[0])

    return resolved


def handle_javascript_reverse_mission_node(
    *,
    task_queue,
    tenant_id: str,
    mission_run_id: str,
    plan: dict,
    node: dict,
    resolved_context: dict,
    work_type: dict,
    work_type_summary: dict,
    counts: dict,
    actions: list[dict],
    submitted_task_ids: list[str],
    matched_skill_ids: list[str],
    matched_skills: list[dict],
    append_action: Callable[..., None],
    task_priority_cls,
) -> bool:
    task_type = str(node.get("task_type") or "plan")
    if task_type not in {"analyze", "reconstruct"}:
        return False

    node_id = str(node.get("id") or "node")
    role_reflection_context = (
        node.get("role_reflection_context", {})
        if isinstance(node.get("role_reflection_context"), dict)
        else {}
    )
    role_reflection_summary = str(role_reflection_context.get("summary") or "").strip()
    role_reflection_experiment = str(role_reflection_context.get("next_experiment") or "").strip()
    source_path = str(
        resolved_context.get("source_path")
        or resolved_context.get("path")
        or resolved_context.get("bundle_path")
        or ""
    ).strip()
    source_dir = str(resolved_context.get("source_dir") or source_path or "").strip()

    if not source_path and not source_dir:
        counts["needs_input"] += 1
        append_action(
            actions=actions,
            node_id=node_id,
            title=node.get("title"),
            action_type="needs_input",
            status="blocked",
            detail="缺少 source_path/source_dir，暂时不能提交真实任务",
            matched_skill_ids=matched_skill_ids,
            matched_skills=matched_skills,
            work_type=work_type,
            work_type_summary=work_type_summary,
            extra={"role_reflection_context": role_reflection_context},
        )
        return True

    payload = {
        "path": source_path or source_dir,
        "source_dir": source_dir or source_path,
        "preferred_tags": ["javascript"],
        "domain_hint": "javascript",
        "_mission_run_id": mission_run_id,
        "_mission_node_id": node_id,
        "_mission_kind": plan.get("mission_kind"),
        "_goal": plan.get("goal"),
        "_role_reflection_context": role_reflection_context,
        "_role_reflection_summary": role_reflection_summary,
        "_role_reflection_experiment": role_reflection_experiment,
    }
    created = task_queue.submit(
        task_type=task_type,
        payload=payload,
        priority=task_priority_cls.HIGH if task_type == "analyze" else task_priority_cls.NORMAL,
        tenant_id=tenant_id,
    )
    submitted_task_ids.append(created.id)
    counts["submitted"] += 1
    append_action(
        actions=actions,
        node_id=node_id,
        title=node.get("title"),
        action_type="task_submitted",
        status="submitted",
        detail=(
            f"已提交 {task_type} 任务，参考岗位实验：{role_reflection_experiment}"
            if role_reflection_experiment
            else f"已提交 {task_type} 任务"
        ),
        matched_skill_ids=matched_skill_ids,
        matched_skills=matched_skills,
        work_type=work_type,
        work_type_summary=work_type_summary,
        extra={
            "task_type": task_type,
            "task_id": created.id,
            "role_reflection_context": role_reflection_context,
        },
    )
    return True


def handle_javascript_reverse_post_action(
    *,
    workspace,
    tenant_id: str,
    mission_run: dict,
    action: dict,
    successful_task_actions: list[dict],
    task_queue,
    collect_task_verified_skills: Callable[[list], list[dict]],
    skill_ids_from_items: Callable[[list[dict] | None], list[str]],
    extract_task_snapshot: Callable[[object], dict],
    resolve_effective_growth_policy: Callable[..., dict],
    infer_framework_hint_from_delivery: Callable[[dict], str],
    safe_float: Callable[[object, float], float],
    create_mission_delivery_skill_candidate: Callable[..., dict | None],
    build_snapshot_signature: Callable[..., str],
    record_growth_event: Callable[..., None],
    growth_policy_decision_label: Callable[[dict], str],
    effective_platform_promotion_status: Callable[[dict], str],
) -> dict:
    if not isinstance(action, dict):
        return action

    node_id = str(action.get("node_id") or "")
    task_ids = [
        str(item.get("task_id") or "")
        for item in successful_task_actions
        if isinstance(item, dict) and item.get("task_id")
    ]
    successful_tasks = [task_queue.get_task(task_id) for task_id in task_ids]
    successful_tasks = [task for task in successful_tasks if task]
    reconstruct_task = next((task for task in successful_tasks if task.type == "reconstruct"), None)
    analyze_task = next((task for task in successful_tasks if task.type == "analyze"), None)
    inherited_skills = collect_task_verified_skills([analyze_task, reconstruct_task])

    if node_id == "validate_result":
        return complete_javascript_reverse_validation_action(
            mission_run=mission_run,
            action=action,
            analyze_task=analyze_task,
            reconstruct_task=reconstruct_task,
            inherited_skills=inherited_skills,
            skill_ids_from_items=skill_ids_from_items,
            extract_task_snapshot=extract_task_snapshot,
        )
    if node_id == "promote_knowledge":
        return complete_javascript_reverse_promotion_action(
            workspace=workspace,
            tenant_id=tenant_id,
            mission_run=mission_run,
            action=action,
            analyze_task=analyze_task,
            reconstruct_task=reconstruct_task,
            inherited_skills=inherited_skills,
            skill_ids_from_items=skill_ids_from_items,
            extract_task_snapshot=extract_task_snapshot,
            resolve_effective_growth_policy=resolve_effective_growth_policy,
            infer_framework_hint_from_delivery=infer_framework_hint_from_delivery,
            safe_float=safe_float,
            create_mission_delivery_skill_candidate=create_mission_delivery_skill_candidate,
            build_snapshot_signature=build_snapshot_signature,
            record_growth_event=record_growth_event,
            growth_policy_decision_label=growth_policy_decision_label,
            effective_platform_promotion_status=effective_platform_promotion_status,
        )
    return action


def build_javascript_reverse_mission_summary(
    *,
    mission_run: dict,
    refreshed_actions: list[dict],
) -> dict:
    summary = {
        "domain": "javascript",
        "analyze": {},
        "reconstruct": {},
        "validation": {},
        "promotion": {},
        "growth_updates": [],
        "recommended_next_actions": [],
        "role_reflection": {},
    }
    recommended_next_actions: list[str] = []

    for action in refreshed_actions:
        if not isinstance(action, dict):
            continue
        task_type = str(action.get("task_type") or "").strip()
        task_result = action.get("task_result", {}) if isinstance(action.get("task_result"), dict) else {}
        next_actions = action.get("next_actions", []) if isinstance(action.get("next_actions"), list) else []
        for item in next_actions:
            text = str(item).strip()
            if text and text not in recommended_next_actions:
                recommended_next_actions.append(text)
        role_reflection_context = action.get("role_reflection_context", {}) if isinstance(action.get("role_reflection_context"), dict) else {}
        if role_reflection_context and not summary["role_reflection"]:
            summary["role_reflection"] = role_reflection_context

        if task_type == "analyze":
            summary["analyze"] = {
                "status": action.get("status"),
                "detail": action.get("detail"),
                "summary": task_result.get("summary"),
                "strategy_id": task_result.get("strategy_id"),
                "capability_id": task_result.get("capability_id"),
                "evaluation_score": task_result.get("evaluation_score"),
            }
        elif task_type == "reconstruct":
            summary["reconstruct"] = {
                "status": action.get("status"),
                "detail": action.get("detail"),
                "summary": task_result.get("summary"),
                "strategy_id": task_result.get("strategy_id"),
                "capability_id": task_result.get("capability_id"),
                "evaluation_verdict": task_result.get("evaluation_verdict"),
                "evaluation_score": task_result.get("evaluation_score"),
                "evaluation_metrics": task_result.get("evaluation_metrics", {}) if isinstance(task_result.get("evaluation_metrics"), dict) else {},
            }

        validation_summary = action.get("validation_summary", {}) if isinstance(action.get("validation_summary"), dict) else {}
        if validation_summary:
            summary["validation"] = validation_summary

        promotion = action.get("promotion", {}) if isinstance(action.get("promotion"), dict) else {}
        if promotion:
            summary["promotion"] = promotion

        growth_update = task_result.get("growth_update", {}) if isinstance(task_result.get("growth_update"), dict) else {}
        if growth_update:
            summary["growth_updates"].append(growth_update)

    summary["growth_updates"] = summary["growth_updates"][:6]
    role_reflection_experiment = str(summary["role_reflection"].get("next_experiment") or "").strip() if isinstance(summary["role_reflection"], dict) else ""
    if role_reflection_experiment and role_reflection_experiment not in recommended_next_actions:
        recommended_next_actions.insert(0, role_reflection_experiment)
    summary["recommended_next_actions"] = recommended_next_actions[:8]
    return summary


def complete_javascript_reverse_validation_action(
    *,
    mission_run: dict,
    action: dict,
    analyze_task,
    reconstruct_task,
    inherited_skills: list[dict] | None = None,
    skill_ids_from_items: Callable[[list[dict] | None], list[str]],
    extract_task_snapshot: Callable[[object], dict],
) -> dict:
    current = dict(action)
    if not reconstruct_task:
        return current
    inherited_skills = inherited_skills if isinstance(inherited_skills, list) else []
    role_reflection_context = (
        mission_run.get("context", {}).get("role_reflection_context", {})
        if isinstance(mission_run.get("context"), dict)
        else {}
    )
    role_reflection_summary = str(role_reflection_context.get("summary") or "").strip()
    role_reflection_experiment = str(role_reflection_context.get("next_experiment") or "").strip()

    reconstruct_snapshot = extract_task_snapshot(reconstruct_task)
    analyze_snapshot = extract_task_snapshot(analyze_task) if analyze_task else {}
    metrics = reconstruct_snapshot.get("evaluation_metrics", {}) if isinstance(reconstruct_snapshot.get("evaluation_metrics"), dict) else {}
    components = int(metrics.get("components", 0) or 0)
    has_target_dir = bool(metrics.get("has_target_dir"))
    verdict = reconstruct_snapshot.get("evaluation_verdict") or "unknown"
    validation_status = "completed" if verdict == "pass" and has_target_dir else "needs_learning"

    current["status"] = validation_status
    current["detail"] = (
        (
            f"已根据最新 analyze/reconstruct 结果完成自动验证，并继续沿岗位实验“{role_reflection_experiment}”推进"
            if role_reflection_experiment
            else "已根据最新 analyze/reconstruct 结果完成自动验证"
        )
        if validation_status == "completed"
        else (
            f"已生成自动验证结论，但当前结果还未达到稳定交付标准；下一步继续验证岗位实验“{role_reflection_experiment}”"
            if role_reflection_experiment
            else "已生成自动验证结论，但当前结果还未达到稳定交付标准"
        )
    )
    current["validation_summary"] = {
        "mission_run_id": mission_run.get("mission_run_id"),
        "verdict": verdict,
        "components": components,
        "has_target_dir": has_target_dir,
        "framework_summary": analyze_snapshot.get("summary"),
        "reconstruct_summary": reconstruct_snapshot.get("summary"),
        "evaluation_score": reconstruct_snapshot.get("evaluation_score"),
        "task_ids": {
            "analyze": analyze_snapshot.get("task_id"),
            "reconstruct": reconstruct_snapshot.get("task_id"),
        },
        "role_reflection_summary": role_reflection_summary,
        "role_reflection_experiment": role_reflection_experiment,
        "validated_at": datetime.now().isoformat(),
    }
    current["matched_verified_skill_ids"] = skill_ids_from_items(inherited_skills)
    current["matched_verified_skills"] = inherited_skills[:3]
    current["next_actions"] = (
        [
            *( [f"继续验证岗位实验：{role_reflection_experiment}"] if role_reflection_experiment else [] ),
            "继续沉淀本轮验证结论，形成可复用经验",
            "补充更多样本做交叉验证，确认当前结果不是偶发",
        ]
        if validation_status == "completed"
        else [
            *( [f"优先围绕岗位实验补样本：{role_reflection_experiment}"] if role_reflection_experiment else [] ),
            "继续补强组件恢复与关键页面映射",
            "补更多样本验证当前骨架是否稳定",
        ]
    )
    return current


def complete_javascript_reverse_promotion_action(
    *,
    workspace,
    tenant_id: str,
    mission_run: dict,
    action: dict,
    analyze_task,
    reconstruct_task,
    inherited_skills: list[dict] | None = None,
    skill_ids_from_items: Callable[[list[dict] | None], list[str]],
    extract_task_snapshot: Callable[[object], dict],
    resolve_effective_growth_policy: Callable[..., dict],
    infer_framework_hint_from_delivery: Callable[[dict], str],
    safe_float: Callable[[object, float], float],
    create_mission_delivery_skill_candidate: Callable[..., dict | None],
    build_snapshot_signature: Callable[..., str],
    record_growth_event: Callable[..., None],
    growth_policy_decision_label: Callable[[dict], str],
    effective_platform_promotion_status: Callable[[dict], str],
) -> dict:
    current = dict(action)
    if not reconstruct_task:
        return current
    inherited_skills = inherited_skills if isinstance(inherited_skills, list) else []
    tenant_manager = TenantManager(workspace)
    work_type_policy = (
        mission_run.get("work_type_summary", {}).get("knowledge_policy", {})
        if isinstance(mission_run.get("work_type_summary"), dict)
        else {}
    )
    effective_growth_policy = resolve_effective_growth_policy(
        tenant_manager=tenant_manager,
        tenant_id=tenant_id,
        work_type_policy=work_type_policy,
    )

    reconstruct_snapshot = extract_task_snapshot(reconstruct_task)
    analyze_snapshot = extract_task_snapshot(analyze_task) if analyze_task else {}
    metrics = reconstruct_snapshot.get("evaluation_metrics", {}) if isinstance(reconstruct_snapshot.get("evaluation_metrics"), dict) else {}
    framework_hint = infer_framework_hint_from_delivery({
        "summary": f"{analyze_snapshot.get('summary') or ''} {reconstruct_snapshot.get('summary') or ''}",
    })
    experience_id = f"mission_delivery_{mission_run.get('mission_run_id')}"

    exp = Experience(
        id=experience_id,
        domain="javascript",
        task_type="mission_delivery",
        input_summary=str(mission_run.get("goal") or mission_run.get("context", {}).get("source_path") or ""),
        output_summary=str(reconstruct_snapshot.get("summary") or "mission delivery completed"),
        quality_score=max(0.0, safe_float(reconstruct_snapshot.get("evaluation_score"), 0.0)),
        capability_type="javascript_reverse",
        metadata={
            "mission_delivery": {
                "mission_run_id": mission_run.get("mission_run_id"),
                "goal": mission_run.get("goal"),
                "context": mission_run.get("context"),
                "analyze_task_id": analyze_snapshot.get("task_id"),
                "reconstruct_task_id": reconstruct_snapshot.get("task_id"),
                "strategy_id": reconstruct_snapshot.get("strategy_id"),
                "capability_id": reconstruct_snapshot.get("capability_id"),
                "framework_hint": infer_framework_hint_from_delivery({
                    "framework_hint": framework_hint,
                    "summary": f"{analyze_snapshot.get('summary') or ''} {reconstruct_snapshot.get('summary') or ''}",
                }),
                "evaluation_verdict": reconstruct_snapshot.get("evaluation_verdict"),
                "evaluation_score": reconstruct_snapshot.get("evaluation_score"),
                "evaluation_metrics": metrics,
                "promoted_at": datetime.now().isoformat(),
                "effective_growth_policy": effective_growth_policy,
                "role_reflection_context": mission_run.get("context", {}).get("role_reflection_context") if isinstance(mission_run.get("context"), dict) else {},
            }
        },
    )
    ExperienceStore(workspace, tenant_id).save(exp)
    skill_candidate = create_mission_delivery_skill_candidate(
        workspace=workspace,
        tenant_id=tenant_id,
        mission_run=mission_run,
        analyze_snapshot=analyze_snapshot,
        reconstruct_snapshot=reconstruct_snapshot,
        safe_float=safe_float,
        build_snapshot_signature=build_snapshot_signature,
        record_growth_event=record_growth_event,
    )

    current["status"] = "completed"
    role_reflection_context = (
        mission_run.get("context", {}).get("role_reflection_context", {})
        if isinstance(mission_run.get("context"), dict)
        else {}
    )
    role_reflection_experiment = str(role_reflection_context.get("next_experiment") or "").strip()
    current["detail"] = (
        f"已把本轮 mission 结果沉淀为经验资产，并保留岗位实验“{role_reflection_experiment}”的上下文"
        if role_reflection_experiment
        else "已把本轮 mission 结果沉淀为经验资产，可供后续自治复用"
    )
    current["promotion"] = {
        "experience_id": experience_id,
        "domain": "javascript",
        "task_type": "mission_delivery",
        "quality_score": exp.quality_score,
        "promoted_at": datetime.now().isoformat(),
        "skill_candidate": skill_candidate,
        "matched_verified_skill_ids": skill_ids_from_items(inherited_skills),
        "effective_growth_policy": effective_growth_policy,
        "sharing_decision": growth_policy_decision_label(effective_growth_policy),
        "platform_promotion_status": effective_platform_promotion_status(effective_growth_policy),
    }
    current["matched_verified_skill_ids"] = skill_ids_from_items(inherited_skills)
    current["matched_verified_skills"] = inherited_skills[:3]
    current["next_actions"] = [
        *( [f"后续同类 mission 继续先验证岗位实验：{role_reflection_experiment}"] if role_reflection_experiment else [] ),
        "后续同类 mission 可直接复用这条经验资产",
        "如果后续多轮稳定通过，再考虑晋升为技能或策略规则",
    ]
    return current


def discover_javascript_research_samples(workspace: Path) -> list[dict]:
    input_root = workspace / "input"
    if not input_root.is_dir():
        return []

    samples: list[dict] = []
    seen_source_dirs: set[str] = set()
    for bundle_path in sorted(input_root.rglob("assets/main-*.js")):
        source_dir = bundle_path.parent.parent
        if not source_dir.is_dir():
            continue
        source_key = str(source_dir.resolve())
        if source_key in seen_source_dirs:
            continue
        seen_source_dirs.add(source_key)

        observed_files = [bundle_path]
        pages_dir = source_dir / "pages"
        assets_dir = source_dir / "assets"
        observed_files.extend(sorted(pages_dir.glob("*.html")) if pages_dir.is_dir() else [])
        observed_files.extend(sorted(assets_dir.glob("*.js")) if assets_dir.is_dir() else [])
        observed_files.extend(sorted(assets_dir.glob("*.css")) if assets_dir.is_dir() else [])

        latest_mtime = 0.0
        signature_parts = [source_key]
        for item in observed_files:
            try:
                stat = item.stat()
            except FileNotFoundError:
                continue
            latest_mtime = max(latest_mtime, stat.st_mtime)
            signature_parts.append(f"{item.name}:{int(stat.st_mtime)}:{stat.st_size}")

        sample_signature = hashlib.sha1("|".join(signature_parts).encode("utf-8")).hexdigest()
        samples.append({
            "bundle_path": str(bundle_path),
            "source_dir": str(source_dir),
            "sample_signature": sample_signature,
            "latest_mtime": latest_mtime,
            "pages_count": len(list(pages_dir.glob("*.html"))) if pages_dir.is_dir() else 0,
        })
    return samples


def task_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def task_matches_research_sample(task, sample: dict, task_type: str) -> bool:
    if task.type != task_type:
        return False
    payload = task.payload or {}
    if payload.get("source_dir") and payload.get("source_dir") != sample.get("source_dir") and task_type == "reconstruct":
        return False
    if payload.get("path") and payload.get("path") != sample.get("bundle_path"):
        return False

    task_signature = payload.get("_sample_signature")
    if task_signature and task_signature == sample.get("sample_signature"):
        return True

    completed_at = task_datetime(task.completed_at or task.started_at or task.created_at)
    if completed_at and completed_at.timestamp() >= float(sample.get("latest_mtime") or 0.0):
        return True
    return False


def find_recent_sample_task(task_queue, tenant_id: str, sample: dict, task_type: str):
    tasks = task_queue.list_tasks(tenant_id=tenant_id, limit=300)
    for task in tasks:
        if task_matches_research_sample(task, sample, task_type):
            return task
    return None


def latest_sample_task(task_queue, tenant_id: str, sample: dict, task_type: str):
    tasks = task_queue.list_tasks(tenant_id=tenant_id, limit=300)
    matches = [task for task in tasks if task_matches_research_sample(task, sample, task_type)]
    if not matches:
        return None
    matches.sort(key=lambda item: task_datetime(item.completed_at or item.started_at or item.created_at) or datetime.min, reverse=True)
    return matches[0]


def auto_submit_javascript_research_tasks(tenant_id: str, task_queue, sample: dict) -> dict:
    record = {
        "tenant_id": tenant_id,
        "bundle_path": sample.get("bundle_path"),
        "source_dir": sample.get("source_dir"),
        "sample_signature": sample.get("sample_signature"),
        "submitted": [],
    }
    analyze_task = find_recent_sample_task(task_queue, tenant_id, sample, "analyze")
    if not analyze_task or analyze_task.status.value in {"failed", "cancelled"}:
        created = task_queue.submit(
            task_type="analyze",
            payload={
                "path": sample["bundle_path"],
                "preferred_tags": ["javascript", "reverse"],
                "domain_hint": "javascript",
                "signals": {
                    "autonomy_loop": True,
                    "background_research": True,
                    "pages_count": sample.get("pages_count", 0),
                },
                "_sample_signature": sample["sample_signature"],
                "_autonomy_source": "background_js_research",
            },
            priority=TaskPriority.HIGH,
            tenant_id=tenant_id,
        )
        record["submitted"].append({"task_type": "analyze", "task_id": created.id})

    reconstruct_task = find_recent_sample_task(task_queue, tenant_id, sample, "reconstruct")
    if not reconstruct_task or reconstruct_task.status.value in {"failed", "cancelled"}:
        created = task_queue.submit(
            task_type="reconstruct",
            payload={
                "path": sample["bundle_path"],
                "source_dir": sample["source_dir"],
                "preferred_tags": ["javascript", "reverse"],
                "domain_hint": "javascript",
                "signals": {
                    "autonomy_loop": True,
                    "background_research": True,
                    "pages_count": sample.get("pages_count", 0),
                },
                "_sample_signature": sample["sample_signature"],
                "_autonomy_source": "background_js_research",
            },
            priority=TaskPriority.HIGH,
            tenant_id=tenant_id,
        )
        record["submitted"].append({"task_type": "reconstruct", "task_id": created.id})

    return record


def infer_pre_execution_hints(
    task_queue,
    tenant_id: str,
    *,
    bundle_path: str | None,
    source_dir: str | None,
    task_type: str,
    extract_task_diagnostics: Callable[[object, dict], dict],
) -> dict:
    sample = {
        "bundle_path": bundle_path,
        "source_dir": source_dir,
        "sample_signature": None,
        "latest_mtime": 0.0,
    }
    relevant_task = latest_sample_task(task_queue, tenant_id, sample, task_type)
    if not relevant_task and task_type == "reconstruct":
        relevant_task = latest_sample_task(task_queue, tenant_id, sample, "analyze")
    if not relevant_task:
        return {}

    plugin_policy = {"enabled": [], "disabled": []}
    snapshot = extract_task_diagnostics(relevant_task, plugin_policy)
    metrics = snapshot.get("evaluation_metrics", {}) if isinstance(snapshot.get("evaluation_metrics"), dict) else {}
    hints = {
        "issue_category": snapshot.get("issue_category"),
        "previous_strategy_id": snapshot.get("strategy_id"),
        "previous_capability_id": snapshot.get("capability_id"),
        "previous_evaluation_verdict": snapshot.get("evaluation_verdict"),
        "previous_evaluation_score": snapshot.get("evaluation_score"),
        "previous_metrics": metrics,
    }
    if "confidence" in metrics:
        hints["confidence"] = metrics.get("confidence")
    if "pattern_count" in metrics:
        hints["pattern_count"] = metrics.get("pattern_count")
    if "framework_count" in metrics:
        hints["framework_count"] = metrics.get("framework_count")
    if "components" in metrics:
        hints["components"] = metrics.get("components")
    if "has_target_dir" in metrics:
        hints["has_target_dir"] = metrics.get("has_target_dir")
    return {key: value for key, value in hints.items() if value is not None}


def create_analyze_handler(
    *,
    workspace: Path,
    task_queue,
    decision_engine,
    extract_task_diagnostics: Callable[[object, dict], dict],
):
    def handle_analyze(task):
        path = task.payload.get("path")
        if not path:
            raise ValueError("Missing path")
        pre_execution_hints = infer_pre_execution_hints(
            task_queue,
            task.tenant_id,
            bundle_path=path,
            source_dir=task.payload.get("source_dir"),
            task_type="analyze",
            extract_task_diagnostics=extract_task_diagnostics,
        )
        result = decision_engine.execute(
            task_type="analyze",
            workspace=workspace,
            tenant_id=task.tenant_id,
            input_path=Path(path),
            capability_id=task.payload.get("capability_id"),
            parameters={
                "save_experience": True,
                "preferred_tags": task.payload.get("preferred_tags", ["javascript"]),
                "domain_hint": task.payload.get("domain_hint", "javascript"),
                "issue_category": pre_execution_hints.get("issue_category"),
                "pre_execution_hints": pre_execution_hints,
                "role_reflection_context": task.payload.get("_role_reflection_context", {}),
                "role_reflection_summary": task.payload.get("_role_reflection_summary"),
                "role_reflection_experiment": task.payload.get("_role_reflection_experiment"),
            },
            signals={
                **(task.payload.get("signals", {}) or {}),
                **pre_execution_hints,
                **({
                    "role_reflection_summary": task.payload.get("_role_reflection_summary"),
                    "role_reflection_experiment": task.payload.get("_role_reflection_experiment"),
                } if task.payload.get("_role_reflection_summary") or task.payload.get("_role_reflection_experiment") else {}),
            },
        )
        return result.to_dict()

    return handle_analyze


def create_reconstruct_handler(
    *,
    workspace: Path,
    task_queue,
    decision_engine,
    extract_task_diagnostics: Callable[[object, dict], dict],
):
    def handle_reconstruct(task):
        path = task.payload.get("path")
        source_dir = task.payload.get("source_dir") or path
        if not source_dir:
            raise ValueError("Missing source_dir/path")
        pre_execution_hints = infer_pre_execution_hints(
            task_queue,
            task.tenant_id,
            bundle_path=path,
            source_dir=source_dir,
            task_type="reconstruct",
            extract_task_diagnostics=extract_task_diagnostics,
        )
        result = decision_engine.execute(
            task_type="reconstruct",
            workspace=workspace,
            tenant_id=task.tenant_id,
            input_path=Path(path) if path else None,
            source_dir=Path(source_dir),
            capability_id=task.payload.get("capability_id"),
            parameters={
                "analysis_result": task.payload.get("analysis_result", {}),
                "preferred_tags": task.payload.get("preferred_tags", ["javascript"]),
                "domain_hint": task.payload.get("domain_hint", "javascript"),
                "issue_category": pre_execution_hints.get("issue_category"),
                "pre_execution_hints": pre_execution_hints,
                "role_reflection_context": task.payload.get("_role_reflection_context", {}),
                "role_reflection_summary": task.payload.get("_role_reflection_summary"),
                "role_reflection_experiment": task.payload.get("_role_reflection_experiment"),
            },
            signals={
                **(task.payload.get("signals", {}) or {}),
                **pre_execution_hints,
                **({
                    "role_reflection_summary": task.payload.get("_role_reflection_summary"),
                    "role_reflection_experiment": task.payload.get("_role_reflection_experiment"),
                } if task.payload.get("_role_reflection_summary") or task.payload.get("_role_reflection_experiment") else {}),
            },
        )
        return result.to_dict()

    return handle_reconstruct


def register_javascript_reverse_handlers(
    *,
    task_queue,
    workspace: Path,
    decision_engine,
    extract_task_diagnostics: Callable[[object, dict], dict],
) -> dict[str, Callable]:
    handlers = {
        "analyze": create_analyze_handler(
            workspace=workspace,
            task_queue=task_queue,
            decision_engine=decision_engine,
            extract_task_diagnostics=extract_task_diagnostics,
        ),
        "reconstruct": create_reconstruct_handler(
            workspace=workspace,
            task_queue=task_queue,
            decision_engine=decision_engine,
            extract_task_diagnostics=extract_task_diagnostics,
        ),
    }
    for task_type, handler in handlers.items():
        task_queue.register_handler(task_type, handler)
    return handlers
