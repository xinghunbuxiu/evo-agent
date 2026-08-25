"""成员克隆：模式 A（同岗位换账号 / 换内容方向）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from admin.runtime_state import create_employee_member_runtime, normalize_child_members_runtime
from admin.task_center_runtime import has_open_formal_task, upsert_task_recommendation
from admin.worker_route_runtime import resolve_work_type_id
from work_types import get_work_type

CLONE_MODE_ACCOUNT_VARIANT = "account_variant"

ORG_DEPARTMENT_PRESETS: dict[str, str] = {
    "operations": "运营",
    "rnd": "研发",
}


def resolve_department_from_work_type(work_type: dict | None) -> tuple[str | None, str | None]:
    if not isinstance(work_type, dict):
        return None, None
    department_id = str(work_type.get("department_id") or "").strip() or None
    department_label = str(work_type.get("department_label") or "").strip() or None
    if department_id and not department_label:
        department_label = ORG_DEPARTMENT_PRESETS.get(department_id)
    return department_id, department_label


def _find_member(child_members: dict, member_id: str) -> dict | None:
    items = child_members.get("items") if isinstance(child_members.get("items"), list) else []
    target = str(member_id or "").strip()
    if not target:
        return None
    return next(
        (
            item for item in items
            if isinstance(item, dict) and str(item.get("member_id") or "").strip() == target
        ),
        None,
    )


def _collect_used_account_ids(child_members: dict, *, exclude_member_id: str | None = None) -> set[str]:
    excluded = str(exclude_member_id or "").strip()
    used: set[str] = set()
    items = child_members.get("items") if isinstance(child_members.get("items"), list) else []
    for member in items:
        if not isinstance(member, dict):
            continue
        member_id = str(member.get("member_id") or "").strip()
        if excluded and member_id == excluded:
            continue
        jobs = member.get("current_jobs") if isinstance(member.get("current_jobs"), list) else []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            account_id = str(job.get("account_id") or "").strip()
            if account_id:
                used.add(account_id)
    return used


def _resolve_source_task(runtime: dict, source_member_id: str) -> dict | None:
    task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
    items = task_center.get("items") if isinstance(task_center.get("items"), list) else []
    open_tasks = [
        item for item in items
        if isinstance(item, dict)
        and str(item.get("member_id") or "").strip() == source_member_id
        and str(item.get("status") or "").strip() in {"assigned", "submitted"}
    ]
    if open_tasks:
        return open_tasks[-1]
    member_tasks = [
        item for item in items
        if isinstance(item, dict) and str(item.get("member_id") or "").strip() == source_member_id
    ]
    if not member_tasks:
        return None
    return member_tasks[-1]


def build_clone_first_task_recommendation(
    *,
    source_member: dict,
    target_member: dict,
    source_task: dict | None,
    content_direction: str,
) -> dict:
    target_member_id = str(target_member.get("member_id") or "").strip() or "member"
    target_name = str(target_member.get("name") or target_member_id).strip() or target_member_id
    source_name = str(source_member.get("name") or source_member.get("member_id") or "源员工").strip()
    direction = str(content_direction or "").strip() or "新内容方向"
    source_title = str(source_task.get("title") or "").strip() if isinstance(source_task, dict) else ""
    source_objective = str(source_task.get("objective") or "").strip() if isinstance(source_task, dict) else ""
    now_iso = datetime.now().isoformat()
    return {
        "recommendation_id": f"recommendation:{target_member_id}:{int(datetime.now().timestamp() * 1000)}:clone",
        "member_id": target_member_id,
        "source_task_id": str(source_task.get("task_id") or "").strip() or None if isinstance(source_task, dict) else None,
        "title": f"{target_name} 首轮任务（复制自 {source_name}）",
        "objective": (
            source_objective
            or f"沿用 {source_name} 已验证的岗位打法，在「{direction}」方向完成首轮最小可验证交付。"
        ),
        "deliverables": [
            f"明确「{direction}」方向的首轮内容/交付目标",
            "沿用源员工已跑通的执行节奏，完成一次真实交付",
            "说明与源账号相比刻意调整了哪些方向变量",
            "提交结果与复盘，供育成官确认",
        ],
        "reason": (
            f"由模式 A 复制建档：技能与工种相同，账号与内容方向独立。"
            f" 参考任务：{source_title or '源员工当前任务线'}。"
            f" 新方向：{direction}。"
        ),
        "status": "suggested",
        "created_at": now_iso,
        "adopted_at": None,
        "metadata": {
            "source": "account_variant_clone",
            "clone_mode": CLONE_MODE_ACCOUNT_VARIANT,
            "cloned_from_member_id": str(source_member.get("member_id") or "").strip() or None,
            "content_direction": direction,
            "reference_task_title": source_title or None,
        },
    }


def clone_account_variant_member(
    *,
    workspace: Path,
    runtime: dict,
    source_member_id: str,
    name: str,
    account_id: str,
    content_direction: str,
    tenant_id: str = "default",
    trainer_member_id: str = "talent_development_officer",
    prefill_first_task: bool = True,
) -> tuple[dict, dict[str, Any]]:
    child_members = normalize_child_members_runtime(
        runtime.get("child_members"),
        legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
    )
    source = _find_member(child_members, source_member_id)
    if not source:
        raise ValueError(f"源员工 {source_member_id} 不存在")

    source_role = str(source.get("primary_role") or "").strip()
    if source_role == "talent_development":
        raise ValueError("育成师不能作为复制源")

    work_type_id = resolve_work_type_id(source)
    if not work_type_id:
        raise ValueError("源员工未绑定工种，无法复制同岗位")

    work_type = get_work_type(workspace, work_type_id)
    if not work_type:
        raise ValueError(f"源员工工种 {work_type_id} 未在平台注册")

    normalized_name = str(name or "").strip()
    normalized_account_id = str(account_id or "").strip()
    normalized_direction = str(content_direction or "").strip()
    if not normalized_name:
        raise ValueError("请填写新员工名称")
    if not normalized_account_id:
        raise ValueError("请填写新账号 account_id")
    if not normalized_direction:
        raise ValueError("请填写内容方向")

    used_accounts = _collect_used_account_ids(child_members)
    if normalized_account_id in used_accounts:
        raise ValueError(f"账号 {normalized_account_id} 已被其他员工使用，请换一个")

    department_id, department_label = resolve_department_from_work_type(work_type)
    work_type_title = str(work_type.get("title") or work_type_id).strip()
    goal_schema = work_type.get("goal_schema") if isinstance(work_type.get("goal_schema"), dict) else {}
    work_type_default_goal = str(goal_schema.get("default_goal") or "").strip() or None

    source_persona = source.get("persona") if isinstance(source.get("persona"), dict) else {}
    source_role_memory = source.get("role_memory") if isinstance(source.get("role_memory"), dict) else {}
    source_operating = source.get("operating_contract") if isinstance(source.get("operating_contract"), dict) else {}
    source_training = source.get("training_plan") if isinstance(source.get("training_plan"), dict) else {}

    direction_goal = (
        f"在「{normalized_direction}」方向独立承担 {work_type_title} 岗位目标，"
        f"沿用 {str(source.get('name') or source_member_id).strip()} 已验证的方法论。"
    )

    employee = create_employee_member_runtime(
        tenant_id=tenant_id,
        name=normalized_name,
        role_label=work_type_title,
        role_key=work_type_id,
        self_description=str(source_persona.get("self_description") or "").strip(),
        long_term_goal=direction_goal or str(source_role_memory.get("long_term_goal") or "").strip(),
        created_by_member_id=trainer_member_id,
        training_owner_member_id=trainer_member_id,
        work_type_id=work_type_id,
        work_type_title=work_type_title,
        work_type_default_goal=work_type_default_goal,
        account_id=normalized_account_id,
        department_id=department_id,
        department_label=department_label,
        content_direction=normalized_direction,
        cloned_from_member_id=source_member_id,
        clone_mode=CLONE_MODE_ACCOUNT_VARIANT,
        persona_overrides={
            "tone": source_persona.get("tone"),
            "speaking_style": source_persona.get("speaking_style"),
            "interaction_style": source_persona.get("interaction_style"),
        },
        role_memory_overrides={
            "strengths": source_role_memory.get("strengths"),
            "shortcomings": source_role_memory.get("shortcomings"),
            "preferred_domains": source_role_memory.get("preferred_domains"),
        },
        operating_contract_overrides={
            "autonomy_mode": source_operating.get("autonomy_mode"),
            "learning_strategy": source_operating.get("learning_strategy"),
            "allow_external_learning": source_operating.get("allow_external_learning"),
            "allow_shared_knowledge": source_operating.get("allow_shared_knowledge"),
            "must_record_experience": source_operating.get("must_record_experience"),
        },
        training_plan_overrides={
            "curriculum": source_training.get("curriculum"),
            "milestones": source_training.get("milestones"),
            "next_action": f"确认「{normalized_direction}」方向画像后，由育成官分配首轮正式任务",
        },
    )

    existing_ids = {
        str(item.get("member_id") or "").strip()
        for item in child_members.get("items", [])
        if isinstance(item, dict)
    }
    new_member_id = str(employee.get("member_id") or "").strip()
    if new_member_id in existing_ids:
        raise ValueError("同名员工实例已存在，请修改名称")

    clone_meta: dict[str, Any] = {
        "clone_mode": CLONE_MODE_ACCOUNT_VARIANT,
        "source_member_id": source_member_id,
        "prefill_first_task": bool(prefill_first_task),
        "recommendation": None,
    }

    if prefill_first_task and not has_open_formal_task(runtime.get("task_center", {}), new_member_id):
        source_task = _resolve_source_task(runtime, source_member_id)
        recommendation = build_clone_first_task_recommendation(
            source_member=source,
            target_member=employee,
            source_task=source_task,
            content_direction=normalized_direction,
        )
        task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
        upsert_task_recommendation(task_center, recommendation)
        runtime["task_center"] = task_center
        clone_meta["recommendation"] = recommendation

    return employee, clone_meta


__all__ = [
    "CLONE_MODE_ACCOUNT_VARIANT",
    "ORG_DEPARTMENT_PRESETS",
    "build_clone_first_task_recommendation",
    "clone_account_variant_member",
    "resolve_department_from_work_type",
]
