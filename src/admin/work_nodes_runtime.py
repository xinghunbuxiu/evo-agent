"""工作节点聚合与按节点 Gitee 归档（M2）。"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from admin.worker_route_runtime import resolve_work_type_id
from core import ExperienceStore, GitProviderError
from core.capability_types import infer_capability_type, legacy_domains_for_capability_type


PHASE_LABELS = {
    "thinking": "思考决策",
    "assigned": "任务分配",
    "execution": "执行协作",
    "submitted": "提交复盘",
    "approved": "育成确认",
    "experience": "经验沉淀",
    "archive": "Gitee 归档",
}

INTEGRATION_PHASE_LABELS = {
    "waiting_assignment": "等待育成师指派",
    "waiting_delivery": "等待提供方交付",
    "ready_to_integrate": "可对接",
    "integrated": "已对接",
}


def _normalize(value: Any) -> str:
    return str(value or "").strip()


def _sanitize_path_segment(value: str) -> str:
    normalized = _normalize(value).replace("node:", "")
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", normalized) or "unknown"


def _format_task_status_label(status: str) -> str:
    if status == "assigned":
        return "待提交"
    if status == "submitted":
        return "待确认"
    if status == "approved":
        return "已完成"
    return status or "--"


def _format_integration_phase(phase: str) -> str:
    return INTEGRATION_PHASE_LABELS.get(phase, phase or "--")


def _find_member(runtime: dict, member_id: str) -> dict | None:
    center = runtime.get("child_members") if isinstance(runtime.get("child_members"), dict) else {}
    items = center.get("items") if isinstance(center.get("items"), list) else []
    for item in items:
        if isinstance(item, dict) and _normalize(item.get("member_id")) == member_id:
            return item
    return None


def _work_type_title_map(workspace: Path, work_types_payload: list[dict] | None = None) -> dict[str, str]:
    titles: dict[str, str] = {"__unbound__": "未绑定工种"}
    if isinstance(work_types_payload, list):
        for item in work_types_payload:
            if not isinstance(item, dict):
                continue
            wt_id = _normalize(item.get("work_type_id"))
            if wt_id:
                titles[wt_id] = _normalize(item.get("title")) or wt_id
    else:
        try:
            from work_types import load_work_types

            for item in load_work_types(workspace).get("items", []):
                if isinstance(item, dict):
                    wt_id = _normalize(item.get("work_type_id"))
                    if wt_id:
                        titles[wt_id] = _normalize(item.get("title")) or wt_id
        except Exception:
            pass
    return titles


def _match_experience_cards(member: dict | None, task: dict) -> list[dict]:
    journal = member.get("experience_journal") if isinstance(member, dict) and isinstance(member.get("experience_journal"), dict) else {}
    cards = journal.get("cards") if isinstance(journal.get("cards"), list) else []
    task_id = _normalize(task.get("task_id"))
    task_title = _normalize(task.get("title"))
    matched: list[dict] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        reflections = card.get("source_reflections") if isinstance(card.get("source_reflections"), list) else []
        if task_id and any(task_id in _normalize(ref) for ref in reflections):
            matched.append(card)
            continue
        if task_title and _normalize(card.get("title")) == task_title:
            matched.append(card)
    return matched


def _phase_status(
    phase_key: str,
    task_status: str,
    *,
    has_thinking: bool,
    has_execution: bool,
    has_experience: bool,
    archived: bool,
) -> str:
    if phase_key == "thinking":
        return "skipped" if not has_thinking else "done"
    if phase_key == "assigned":
        return "done" if task_status else "pending"
    if phase_key == "execution":
        if not has_execution:
            return "skipped"
        return "current" if task_status == "assigned" else "done"
    if phase_key == "submitted":
        if task_status in {"submitted", "approved"}:
            return "done"
        return "current" if task_status == "assigned" else "pending"
    if phase_key == "approved":
        if task_status == "approved":
            return "done"
        return "current" if task_status == "submitted" else "pending"
    if phase_key == "experience":
        if has_experience:
            return "done"
        return "current" if task_status == "approved" else "pending"
    if phase_key == "archive":
        if archived:
            return "done"
        return "current" if task_status == "approved" else "pending"
    return "pending"


def _build_phases(task: dict, member: dict | None, experience_cards: list[dict], archived: bool) -> list[dict]:
    task_status = _normalize(task.get("status"))
    memory_hub = member.get("memory_hub") if isinstance(member, dict) and isinstance(member.get("memory_hub"), dict) else {}
    decision_state = memory_hub.get("decision_state") if isinstance(memory_hub.get("decision_state"), dict) else {}
    decision_history = memory_hub.get("decision_history") if isinstance(memory_hub.get("decision_history"), list) else []
    last_decision = decision_history[-1] if decision_history and isinstance(decision_history[-1], dict) else {}
    last_state = last_decision.get("decision_state") if isinstance(last_decision.get("decision_state"), dict) else {}
    last_summary = last_decision.get("decision_summary") if isinstance(last_decision.get("decision_summary"), dict) else {}

    thinking_summary = _normalize(decision_state.get("primary_plan") or last_state.get("primary_plan") or last_summary.get("primary_plan") or memory_hub.get("decision_intent"))
    thinking_detail = "\n".join(
        part for part in [
            f"验证目标：{decision_state.get('verification_goal')}" if decision_state.get("verification_goal") else "",
            f"备选：{decision_state.get('fallback_plan')}" if decision_state.get("fallback_plan") else "",
        ] if part
    )

    integration = task.get("integration_pending") if isinstance(task.get("integration_pending"), dict) else {}
    phase = _normalize(integration.get("phase"))
    has_execution = bool(phase and phase != "integrated")
    has_thinking = bool(thinking_summary or thinking_detail)
    has_experience = bool(experience_cards)

    defs = [
        ("thinking", thinking_summary, thinking_detail, last_decision.get("created_at")),
        ("assigned", _normalize(task.get("objective")), "、".join(task.get("deliverables") or []) if isinstance(task.get("deliverables"), list) else "", task.get("assigned_at")),
        ("execution", _format_integration_phase(phase) if has_execution else "", _normalize(integration.get("collaboration_request_id")), integration.get("updated_at")),
        ("submitted", _normalize(task.get("result_summary")), _normalize(task.get("reflection")), task.get("submitted_at")),
        ("approved", _normalize(task.get("review_note")), "", task.get("approved_at")),
        (
            "experience",
            _normalize(
                ((experience_cards[0] or {}).get("summary") or (experience_cards[0] or {}).get("title"))
                if experience_cards
                else ""
            ),
            _normalize((experience_cards[0] or {}).get("current_pattern") if experience_cards else ""),
            (member or {}).get("experience_journal", {}).get("last_compiled_at") if isinstance(member, dict) else None,
        ),
        ("archive", "已写入经验仓库" if archived else "任务确认后可归档到 Gitee", "", task.get("approved_at") if archived else None),
    ]

    phases: list[dict] = []
    for key, summary, detail, at in defs:
        phases.append({
            "key": key,
            "label": PHASE_LABELS[key],
            "status": _phase_status(
                key,
                task_status,
                has_thinking=has_thinking,
                has_execution=has_execution,
                has_experience=has_experience,
                archived=archived,
            ),
            "summary": summary or None,
            "detail": detail or None,
            "at": at,
        })
    return phases


def build_work_nodes_from_runtime(
    workspace: Path,
    runtime: dict,
    *,
    work_types: list[dict] | None = None,
) -> list[dict]:
    task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
    tasks = task_center.get("items") if isinstance(task_center.get("items"), list) else []
    titles = _work_type_title_map(workspace, work_types)

    nodes: list[dict] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        member_id = _normalize(task.get("member_id"))
        if not member_id:
            continue
        member = _find_member(runtime, member_id)
        if member and _normalize(member.get("primary_role")) == "talent_development":
            continue
        work_type_id = resolve_work_type_id(member) or "__unbound__"
        task_id = _normalize(task.get("task_id")) or f"task:{member_id}"
        task_status = _normalize(task.get("status"))
        experience_cards = _match_experience_cards(member, task)
        archive_meta = task.get("work_node_archive") if isinstance(task.get("work_node_archive"), dict) else {}
        archived = _normalize(archive_meta.get("status")) in {"archived", "exported", "local_only"}
        if archived:
            status = "archived"
        elif task_status == "approved":
            status = "approved"
        elif task_status == "submitted":
            status = "submitted"
        else:
            status = "running"

        node_id = f"node:{task_id}"
        phases = _build_phases(task, member, experience_cards, archived)
        nodes.append({
            "node_id": node_id,
            "task_id": task_id,
            "work_type_id": work_type_id,
            "work_type_title": titles.get(work_type_id, work_type_id),
            "member_id": member_id,
            "member_name": _normalize((member or {}).get("name") or member_id),
            "department_id": _normalize((member or {}).get("organization") or {}).get("department_id") if isinstance((member or {}).get("organization"), dict) else None,
            "department_label": _normalize((member or {}).get("organization") or {}).get("department_label") if isinstance((member or {}).get("organization"), dict) else None,
            "title": _normalize(task.get("title")) or "未命名任务",
            "status": status,
            "status_label": "已归档" if status == "archived" else _format_task_status_label(task_status),
            "updated_at": task.get("approved_at") or task.get("submitted_at") or task.get("assigned_at"),
            "phases": phases,
            "experience_cards": experience_cards,
            "archive": archive_meta or None,
            "archive_hint": archive_meta.get("gitee_path") or archive_meta.get("local_root") or (
                "任务确认并沉淀经验后可归档到 Gitee experiences 仓库"
            ),
            "member_link": f"/organization/child/{member_id}/workspace",
            "trainer_link": f"/organization/trainer/talent_development_officer/workspace?mode=dispatch&member={member_id}",
        })

    nodes.sort(key=lambda item: _normalize(item.get("updated_at")), reverse=True)
    return nodes


def filter_work_nodes(
    nodes: list[dict],
    *,
    work_type_id: str | None = None,
    member_id: str | None = None,
    node_id: str | None = None,
) -> list[dict]:
    result = nodes
    if work_type_id:
        result = [item for item in result if item.get("work_type_id") == work_type_id]
    if member_id:
        result = [item for item in result if item.get("member_id") == member_id]
    if node_id:
        result = [item for item in result if item.get("node_id") == node_id]
    return result


def list_skills_for_scope(
    workspace: Path,
    tenant_id: str,
    *,
    work_type_id: str | None = None,
    member_id: str | None = None,
    limit: int = 40,
) -> list[dict]:
    store = ExperienceStore(workspace, tenant_id)
    domains: list[str] = []
    if work_type_id and work_type_id != "__unbound__":
        try:
            from admin.worker_route_runtime import resolve_runtime_route_for_work_type

            route = resolve_runtime_route_for_work_type(workspace, work_type_id)
            capability = infer_capability_type(
                capability_type=route.get("capability_type"),
                domain=work_type_id,
            )
            domains = list(legacy_domains_for_capability_type(capability)) or [capability]
        except Exception:
            domains = [work_type_id]
    else:
        domains = ["evolution", "operations", "general"]

    seen: set[str] = set()
    skills: list[dict] = []
    for domain in domains:
        for exp in store.load_by_domain(domain, limit=limit):
            meta = exp.metadata if isinstance(exp.metadata, dict) else {}
            if member_id and _normalize(meta.get("member_id")) and _normalize(meta.get("member_id")) != member_id:
                continue
            if work_type_id and work_type_id != "__unbound__":
                meta_wt = _normalize(meta.get("work_type_id") or meta.get("job_id"))
                if meta_wt and meta_wt != work_type_id:
                    continue
            key = exp.id
            if key in seen:
                continue
            seen.add(key)
            skills.append({
                "skill_id": exp.id,
                "domain": exp.domain,
                "capability_type": exp.capability_type,
                "task_type": exp.task_type,
                "title": _normalize(meta.get("title")) or exp.output_summary[:80] or exp.id,
                "summary": exp.output_summary,
                "input_summary": exp.input_summary,
                "quality_score": exp.quality_score,
                "member_id": meta.get("member_id"),
                "task_id": meta.get("task_id"),
                "created_at": exp.created_at,
            })
            if len(skills) >= limit:
                return skills
    return skills


def work_node_storage_prefix(tenant_id: str, work_type_id: str, member_id: str, task_id: str) -> str:
    safe_task = _sanitize_path_segment(task_id)
    safe_wt = _sanitize_path_segment(work_type_id)
    safe_member = _sanitize_path_segment(member_id)
    return f"tenants/{tenant_id}/work_types/{safe_wt}/members/{safe_member}/nodes/{safe_task}"


def _write_local_node_archive(workspace: Path, prefix: str, files: dict[str, str]) -> dict:
    base = workspace / ".admin" / "local_git_exports" / prefix
    saved: list[str] = []
    for rel, content in files.items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        saved.append(f"{prefix}/{rel}")
    return {
        "status": "local_only",
        "local_root": str(base),
        "files": saved,
        "gitee_path": prefix,
    }


async def archive_work_node_to_storage(
    *,
    workspace: Path,
    tenant_id: str,
    runtime: dict,
    task_id: str,
    get_user_gitee_token: Callable,
    tenant_manager,
    config,
    get_git_provider_instance: Callable,
    get_tenant_git_repo: Callable,
    request=None,
) -> dict:
    nodes = build_work_nodes_from_runtime(workspace, runtime)
    node = next((item for item in nodes if item.get("task_id") == task_id or item.get("node_id") == f"node:{task_id}"), None)
    if not node:
        return {"status": "failed", "reason": "node_not_found"}

    task_status = _normalize(next(
        (
            task.get("status")
            for task in (runtime.get("task_center", {}) or {}).get("items", [])
            if isinstance(task, dict) and _normalize(task.get("task_id")) == _normalize(node.get("task_id"))
        ),
        "",
    ))
    if task_status != "approved":
        return {"status": "blocked", "reason": "task_not_approved", "next_action": "请先由育成师确认任务后再归档"}

    prefix = work_node_storage_prefix(
        tenant_id,
        str(node.get("work_type_id") or "__unbound__"),
        str(node.get("member_id") or "unknown"),
        str(node.get("task_id") or "unknown"),
    )
    phase_files = {
        f"phases/{phase['key']}.json": json.dumps(phase, ensure_ascii=False, indent=2)
        for phase in (node.get("phases") or [])
        if isinstance(phase, dict)
    }
    files = {
        "manifest.json": json.dumps(node, ensure_ascii=False, indent=2),
        "skills.json": json.dumps(
            list_skills_for_scope(
                workspace,
                tenant_id,
                work_type_id=str(node.get("work_type_id") or ""),
                member_id=str(node.get("member_id") or ""),
            ),
            ensure_ascii=False,
            indent=2,
        ),
        "archive.meta.json": json.dumps({
            "archived_at": datetime.now().isoformat(),
            "node_id": node.get("node_id"),
            "task_id": node.get("task_id"),
        }, ensure_ascii=False, indent=2),
        **phase_files,
    }

    token = None
    if request is not None:
        token = get_user_gitee_token(request)
    token = token or os.getenv("GITEE_TOKEN")
    if not token or token == "your_real_token_here":
        local = _write_local_node_archive(workspace, prefix, files)
        return {**local, "reason": "missing_gitee_token", "next_action": "已落盘本地，配置 GITEE_TOKEN 后可同步远端"}

    git_knowledge = tenant_manager.get_git_knowledge_config(tenant_id)
    provider = get_git_provider_instance(config, git_knowledge)
    target_repo, target_url = get_tenant_git_repo(
        tenant_manager,
        tenant_id,
        "experiences",
        config.experiences.full_name,
        config.experiences.url,
    )
    repos = git_knowledge.get("repos", {}) if isinstance(git_knowledge, dict) else {}
    branch = "master"
    if isinstance(repos, dict) and isinstance(repos.get("experiences"), dict):
        branch = _normalize(repos.get("experiences", {}).get("branch")) or "master"
    if not target_repo:
        local = _write_local_node_archive(workspace, prefix, files)
        return {**local, "reason": "missing_git_repo", "next_action": "已落盘本地，初始化 experiences 仓后可同步"}

    uploaded: list[str] = []
    try:
        for rel_path, content in files.items():
            full_path = f"{prefix}/{rel_path}"
            await provider.upsert_text_file(
                token=token,
                repo_full_name=target_repo,
                file_path=full_path,
                content=content,
                message=f"Archive work node {node.get('node_id')}",
                branch=branch,
            )
            uploaded.append(full_path)
    except GitProviderError as exc:
        local = _write_local_node_archive(workspace, prefix, files)
        return {
            **local,
            "status": "local_only",
            "reason": str(exc),
            "target_repo": target_repo,
            "branch": branch,
            "next_action": "远端失败，已落盘本地 workspace",
        }

    return {
        "status": "archived",
        "reason": None,
        "gitee_path": prefix,
        "target_repo": target_repo,
        "target_url": target_url,
        "branch": branch,
        "files": uploaded,
        "archived_at": datetime.now().isoformat(),
        "next_action": "节点已写入 Gitee experiences 仓库",
    }


def attach_archive_to_task(runtime: dict, task_id: str, archive_meta: dict) -> bool:
    task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
    items = task_center.get("items") if isinstance(task_center.get("items"), list) else []
    changed = False
    for task in items:
        if not isinstance(task, dict):
            continue
        if _normalize(task.get("task_id")) != _normalize(task_id):
            continue
        task["work_node_archive"] = archive_meta
        pending = task.get("integration_pending") if isinstance(task.get("integration_pending"), dict) else {}
        if archive_meta.get("status") in {"archived", "exported", "local_only"}:
            pending = {**pending, "phase": "integrated"}
            task["integration_pending"] = pending
        changed = True
        break
    return changed
