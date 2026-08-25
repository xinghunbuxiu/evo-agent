"""
知识沉淀运行时：技能草稿、自动验证、经验转技能。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from core import Experience, ExperienceStore, Skill, SkillRegistry, SkillTrustLevel


def collect_task_verified_skills(tasks: list) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for task in tasks:
        if not task:
            continue
        result = task.result if isinstance(getattr(task, "result", None), dict) else {}
        feedback = result.get("feedback", {}) if isinstance(result.get("feedback"), dict) else {}
        candidates = result.get("matched_verified_skills", [])
        if not isinstance(candidates, list) or not candidates:
            candidates = feedback.get("matched_verified_skills", []) if isinstance(feedback, dict) else []
        if not isinstance(candidates, list):
            continue
        for item in candidates:
            if not isinstance(item, dict):
                continue
            skill_id = str(item.get("id") or "").strip()
            if not skill_id or skill_id in seen:
                continue
            items.append(item)
            seen.add(skill_id)
    return items


def skill_ids_from_items(items: list[dict]) -> list[str]:
    if not isinstance(items, list):
        return []
    result: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        skill_id = str(item.get("id") or "").strip()
        if skill_id and skill_id not in result:
            result.append(skill_id)
    return result


def local_skill_dirs(workspace: Path, tenant_id: str) -> tuple[Path, Path]:
    visible_dir = workspace / ".tenants" / tenant_id / "skills" / "draft"
    cache_dir = workspace / ".tenants" / tenant_id / ".skill_cache" / "drafts"
    visible_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return visible_dir, cache_dir


def write_skill_candidate(workspace: Path, tenant_id: str, skill: Skill) -> dict:
    visible_dir, cache_dir = local_skill_dirs(workspace, tenant_id)
    skill_payload = skill.to_dict()
    visible_path = visible_dir / f"{skill.id}.json"
    cache_path = cache_dir / f"{skill.id}.json"
    visible_path.write_text(json.dumps(skill_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    cache_path.write_text(json.dumps(skill_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "skill_id": skill.id,
        "name": skill.name,
        "domain": skill.domain,
        "trust_level": skill.trust_level.value,
        "visible_path": str(visible_path),
        "cache_path": str(cache_path),
    }


def local_verified_skill_dir(workspace: Path, tenant_id: str) -> Path:
    path = workspace / ".tenants" / tenant_id / "skills" / "verified"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_local_skill_payload(workspace: Path, tenant_id: str, skill_id: str) -> dict | None:
    candidates = [
        workspace / ".tenants" / tenant_id / "skills" / "verified" / f"{skill_id}.json",
        workspace / ".tenants" / tenant_id / "skills" / "draft" / f"{skill_id}.json",
        workspace / ".tenants" / tenant_id / ".skill_cache" / "verified" / f"{skill_id}.json",
        workspace / ".tenants" / tenant_id / ".skill_cache" / "drafts" / f"{skill_id}.json",
    ]
    for file_path in candidates:
        if not file_path.is_file():
            continue
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def infer_framework_hint_from_delivery(exp: Experience | dict) -> str:
    if isinstance(exp, Experience):
        metadata = exp.metadata if isinstance(exp.metadata, dict) else {}
        payload = metadata.get("mission_delivery", {}) if isinstance(metadata.get("mission_delivery"), dict) else {}
        framework_hint = str(payload.get("framework_hint") or "").strip().lower()
        summary = f"{exp.output_summary} {exp.input_summary}".lower()
    else:
        payload = exp if isinstance(exp, dict) else {}
        framework_hint = str(payload.get("framework_hint") or "").strip().lower()
        summary = str(payload.get("summary") or "").lower()
    if framework_hint:
        return framework_hint
    if "react" in summary:
        return "react"
    if "vue" in summary:
        return "vue"
    return "javascript"


def matching_mission_delivery_experiences(
    workspace: Path,
    tenant_id: str,
    framework_hint: str,
) -> list[Experience]:
    store = ExperienceStore(workspace, tenant_id)
    matches: list[Experience] = []
    for exp in store.load_by_task("javascript", "mission_delivery", limit=50):
        if infer_framework_hint_from_delivery(exp) != framework_hint:
            continue
        metadata = exp.metadata if isinstance(exp.metadata, dict) else {}
        payload = metadata.get("mission_delivery", {}) if isinstance(metadata.get("mission_delivery"), dict) else {}
        if str(payload.get("evaluation_verdict") or "") != "pass":
            continue
        if not bool((payload.get("evaluation_metrics") or {}).get("has_target_dir")):
            continue
        matches.append(exp)
    return matches


def sync_verified_skill_view(workspace: Path, tenant_id: str, skill_id: str) -> dict | None:
    registry = SkillRegistry(workspace, tenant_id)
    verified_file = registry.local_verified / f"{skill_id}.json"
    if not verified_file.is_file():
        return None
    try:
        payload = json.loads(verified_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    visible_dir = local_verified_skill_dir(workspace, tenant_id)
    visible_path = visible_dir / f"{skill_id}.json"
    visible_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    draft_visible = workspace / ".tenants" / tenant_id / "skills" / "draft" / f"{skill_id}.json"
    if draft_visible.is_file():
        draft_visible.unlink()
    return {
        "skill_id": skill_id,
        "trust_level": payload.get("trust_level", "verified"),
        "verified_path": str(visible_path),
        "success_rate": payload.get("success_rate"),
        "usage_count": payload.get("usage_count"),
    }


def maybe_auto_verify_skill_candidate(
    workspace: Path,
    tenant_id: str,
    skill: Skill,
    framework_hint: str,
) -> dict | None:
    evidences = matching_mission_delivery_experiences(workspace, tenant_id, framework_hint)
    if len(evidences) < 2:
        return None
    test_results = [
        {"success": True, "quality_score": exp.quality_score, "id": exp.id}
        for exp in evidences
    ]
    registry = SkillRegistry(workspace, tenant_id)
    verified = registry.verify_skill(skill.id, test_results, min_success_rate=0.8)
    if not verified:
        return None
    synced = sync_verified_skill_view(workspace, tenant_id, skill.id) or {}
    return {
        "validated_by": "mission_delivery_history",
        "evidence_count": len(evidences),
        **synced,
    }


def should_skip_auto_skill_task_type(task_type: str) -> bool:
    normalized = str(task_type or "").strip().lower()
    return normalized in {"growth_event", "replay_validation", "strategy_governance", "role_reflection"}


def collect_stable_experience_skill_groups(workspace: Path, tenant_id: str) -> list[dict]:
    experiences_root = workspace / ".tenants" / tenant_id / "experiences"
    if not experiences_root.is_dir():
        return []
    store = ExperienceStore(workspace, tenant_id)
    groups: dict[tuple[str, str, str], dict] = {}
    for domain_dir in sorted(item for item in experiences_root.iterdir() if item.is_dir()):
        domain = domain_dir.name
        for exp in store.load_by_domain(domain, limit=80):
            if should_skip_auto_skill_task_type(exp.task_type):
                continue
            if float(exp.quality_score or 0.0) < 0.75:
                continue
            capability_type = str(exp.capability_type or "").strip() or domain
            group_key = (domain, str(exp.task_type or "").strip(), capability_type)
            current = groups.setdefault(group_key, {
                "domain": domain,
                "task_type": str(exp.task_type or "").strip(),
                "capability_type": capability_type,
                "items": [],
            })
            current["items"].append(exp)
    stable_groups: list[dict] = []
    for payload in groups.values():
        items = payload["items"]
        if len(items) < 2:
            continue
        avg_quality = round(sum(float(item.quality_score or 0.0) for item in items) / len(items), 3)
        if avg_quality < 0.82:
            continue
        payload["items"] = sorted(items, key=lambda item: item.created_at, reverse=True)[:6]
        payload["count"] = len(items)
        payload["avg_quality"] = avg_quality
        stable_groups.append(payload)
    stable_groups.sort(key=lambda item: (item["avg_quality"], item["count"]), reverse=True)
    return stable_groups


def maybe_auto_verify_stable_experience_skill_candidate(
    workspace: Path,
    tenant_id: str,
    skill: Skill,
    items: list[Experience],
) -> dict | None:
    if len(items) < 3:
        return None
    avg_quality = round(sum(float(item.quality_score or 0.0) for item in items) / max(len(items), 1), 3)
    if avg_quality < 0.86:
        return None
    registry = SkillRegistry(workspace, tenant_id)
    test_results = [
        {"success": float(item.quality_score or 0.0) >= 0.8, "quality_score": float(item.quality_score or 0.0), "id": item.id}
        for item in items
    ]
    verified = registry.verify_skill(skill.id, test_results, min_success_rate=0.85)
    if not verified:
        return None
    synced = sync_verified_skill_view(workspace, tenant_id, skill.id) or {}
    return {
        "validated_by": "stable_experience_cluster",
        "evidence_count": len(items),
        "avg_quality_score": avg_quality,
        **synced,
    }


def auto_draft_stable_experience_skills(
    workspace: Path,
    tenant_id: str,
    *,
    safe_float: Callable[[object, float], float],
    record_growth_event: Callable[..., object],
) -> list[dict]:
    groups = collect_stable_experience_skill_groups(workspace, tenant_id)
    drafted: list[dict] = []
    for group in groups[:8]:
        domain = str(group.get("domain") or "general")
        task_type = str(group.get("task_type") or "task")
        capability_type = str(group.get("capability_type") or domain)
        skill_id = f"skill_auto_{domain}_{task_type}"
        items = group.get("items", []) if isinstance(group.get("items"), list) else []
        if not items:
            continue
        existing_payload = load_local_skill_payload(workspace, tenant_id, skill_id) or {}
        existing_usage = int(existing_payload.get("usage_count", 0) or 0)
        evidence_ids = [str(item.id) for item in items[:4]]
        summaries = [str(item.output_summary or "").strip() for item in items[:3] if str(item.output_summary or "").strip()]
        existing_params = existing_payload.get("parameters", {}) if isinstance(existing_payload.get("parameters"), dict) else {}
        existing_evidence_ids = existing_params.get("evidence_ids", [])
        existing_avg_quality = safe_float(existing_params.get("avg_quality_score"), 0.0)
        if existing_payload and list(existing_evidence_ids) == evidence_ids and abs(existing_avg_quality - float(group.get("avg_quality") or 0.0)) < 0.001:
            continue
        description = (
            f"基于 {group.get('count')} 条稳定 {domain}/{task_type} 经验自动沉淀的技能草稿，"
            f"当前平均质量分 {group.get('avg_quality'):.2f}。"
        )
        code = "\n".join([
            "1. 读取任务目标与上下文，识别当前输入是否匹配该类稳定经验。",
            f"2. 优先复用 {domain}/{task_type} 历史成功路径与关键检查点。",
            "3. 执行后记录结果，继续补充新的经验与回放验证。",
            "4. 只有多轮稳定后，才从 draft 晋升为 verified 或共享层能力。",
        ])
        skill = Skill(
            id=skill_id,
            name=f"auto_{domain}_{task_type}",
            domain=domain,
            capability_type=capability_type,
            description=description,
            code=code,
            parameters={
                "task_type": task_type,
                "capability_type": capability_type,
                "auto_generated": True,
                "stable_experience_count": int(group.get("count") or 0),
                "avg_quality_score": float(group.get("avg_quality") or 0.0),
                "evidence_ids": evidence_ids,
                "example_outputs": summaries,
            },
            trust_level=SkillTrustLevel(existing_payload.get("trust_level", "draft")),
            source="stable_experience_auto_generated",
            version="1.0.0",
            usage_count=max(existing_usage, int(group.get("count") or 0)),
            success_rate=float(group.get("avg_quality") or 0.0),
        )
        skill_info = write_skill_candidate(workspace, tenant_id, skill)
        verified_info = maybe_auto_verify_stable_experience_skill_candidate(
            workspace=workspace,
            tenant_id=tenant_id,
            skill=skill,
            items=items,
        )
        if isinstance(verified_info, dict):
            skill_info = {**skill_info, **verified_info, "trust_level": "verified"}
        record_growth_event(
            workspace,
            tenant_id,
            strategy_id=f"skill.{skill_id}",
            event_type="stable_experience_skill_verified" if isinstance(verified_info, dict) else "stable_experience_skill_candidate",
            summary=(
                f"{skill.name} verified from stable experience cluster"
                if isinstance(verified_info, dict)
                else f"{skill.name} drafted from stable experience cluster"
            ),
            quality_score=float(group.get("avg_quality") or 0.0),
            task_type=task_type,
            domain=domain,
            metadata={
                "skill_id": skill.id,
                "source": "stable_experience_cluster",
                "evidence_ids": evidence_ids,
                "stable_experience_count": int(group.get("count") or 0),
                "verified": bool(verified_info),
            },
        )
        drafted.append({
            **skill_info,
            "source": "stable_experience_cluster",
            "stable_experience_count": int(group.get("count") or 0),
            "avg_quality_score": float(group.get("avg_quality") or 0.0),
            "evidence_ids": evidence_ids,
        })
    return drafted


def create_mission_delivery_skill_candidate(
    *,
    workspace: Path,
    tenant_id: str,
    mission_run: dict,
    analyze_snapshot: dict,
    reconstruct_snapshot: dict,
    safe_float: Callable[[object, float], float],
    build_snapshot_signature: Callable[[dict], dict],
    record_growth_event: Callable[..., object],
) -> dict:
    metrics = reconstruct_snapshot.get("evaluation_metrics", {}) if isinstance(reconstruct_snapshot.get("evaluation_metrics"), dict) else {}
    components = int(metrics.get("components", 0) or 0)
    framework_hint = "javascript"
    analyze_summary = str(analyze_snapshot.get("summary") or "").lower()
    reconstruct_summary = str(reconstruct_snapshot.get("summary") or "").lower()
    if "react" in analyze_summary or "react" in reconstruct_summary:
        framework_hint = "react"
    elif "vue" in analyze_summary or "vue" in reconstruct_summary:
        framework_hint = "vue"
    skill_id = f"skill_javascript_reverse_{framework_hint}_delivery"
    existing_payload = load_local_skill_payload(workspace, tenant_id, skill_id) or {}
    existing_usage = int(existing_payload.get("usage_count", 0) or 0)
    skill = Skill(
        id=skill_id,
        name=f"mission_delivery_{framework_hint}_reverse",
        domain="javascript",
        capability_type="javascript_reverse",
        description="根据已验证成功的 JS 逆向交付样本自动生成的草稿技能候选。",
        code=(
            "1. 接收工作目录或 bundle 路径。\n"
            "2. 自动解析真正的 assets/main-*.js 入口与 source_dir。\n"
            "3. 执行 analyze 提取框架、打包器、页面与边界线索。\n"
            "4. 执行 reconstruct 生成可接手的项目骨架。\n"
            "5. 根据 evaluation_verdict、components、has_target_dir 自动验证交付质量。\n"
            "6. 将成功结果沉淀为经验、验证摘要与后续成长候选。"
        ),
        parameters={
            "mission_kind": mission_run.get("mission_kind"),
            "framework_hint": framework_hint,
            "components": components,
            "accepted_tasks": ["analyze", "reconstruct"],
            "required_context_keys": ["source_path", "bundle_path", "source_dir"],
            "acceptance": {
                "evaluation_verdict": reconstruct_snapshot.get("evaluation_verdict"),
                "has_target_dir": bool(metrics.get("has_target_dir")),
                "components_min": components,
            },
        },
        trust_level=SkillTrustLevel(existing_payload.get("trust_level", "draft")),
        source="mission_delivery_auto_generated",
        version="1.0.0",
        usage_count=existing_usage + 1,
        success_rate=1.0 if reconstruct_snapshot.get("evaluation_verdict") == "pass" else 0.0,
    )
    skill_info = write_skill_candidate(workspace, tenant_id, skill)
    verified_info = maybe_auto_verify_skill_candidate(
        workspace=workspace,
        tenant_id=tenant_id,
        skill=skill,
        framework_hint=framework_hint,
    )
    if isinstance(verified_info, dict):
        skill_info = {**skill_info, **verified_info, "trust_level": "verified"}
    record_growth_event(
        workspace,
        tenant_id,
        strategy_id=str(reconstruct_snapshot.get("strategy_id") or "mission_delivery"),
        event_type="mission_skill_candidate",
        summary=f"{skill.name} drafted from successful mission delivery",
        quality_score=max(0.1, safe_float(reconstruct_snapshot.get("evaluation_score"), 0.1)),
        task_type="mission_delivery",
        domain="javascript",
        signature=build_snapshot_signature(reconstruct_snapshot),
        metadata={
            "skill_id": skill.id,
            "skill_name": skill.name,
            "mission_run_id": mission_run.get("mission_run_id"),
            "source": "mission_delivery",
            "framework_hint": framework_hint,
            "verified": bool(verified_info),
        },
    )
    return skill_info
