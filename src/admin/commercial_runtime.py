"""
可商业化视角：经营就绪度与演示闭环检查。
"""

from __future__ import annotations

from pathlib import Path

from admin.finance_runtime import get_finance_overview
from admin.runtime_state import load_autonomy_runtime, load_learning_tasks
from work_types import load_work_types
from workers.registry import load_worker_registry_config


def _count_active_knowledge_learning(workspace: Path) -> int:
    state = load_learning_tasks(workspace)
    tasks = state.get("tasks") if isinstance(state.get("tasks"), dict) else {}
    terminal = {"resolved", "validated_unchanged", "validated_improved"}
    count = 0
    for payload in tasks.values():
        if not isinstance(payload, dict):
            continue
        if str(payload.get("source") or "").strip() != "memory_hub_auto":
            continue
        if str(payload.get("status") or "").strip() in terminal:
            continue
        count += 1
    return count


def build_weekly_briefing(workspace: Path, *, tenant_id: str = "default") -> dict:
    finance = get_finance_overview(workspace)
    readiness = get_commercial_readiness(workspace, tenant_id=tenant_id)
    runtime = load_autonomy_runtime(workspace, tenant_id)
    task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
    formal_tasks = task_center.get("items") if isinstance(task_center.get("items"), list) else []
    approved = sum(
        1 for item in formal_tasks
        if isinstance(item, dict) and str(item.get("status") or "") in {"approved", "completed"}
    )
    submitted = sum(
        1 for item in formal_tasks
        if isinstance(item, dict) and str(item.get("status") or "") == "submitted"
    )
    knowledge_active = _count_active_knowledge_learning(workspace)
    training_review = runtime.get("training_review") if isinstance(runtime.get("training_review"), dict) else {}
    commercial = finance.get("commercial_verdict") if isinstance(finance.get("commercial_verdict"), dict) else {}
    primary = finance.get("primary") if isinstance(finance.get("primary"), dict) else {}
    latest_decision = finance.get("latest_decision") if isinstance(finance.get("latest_decision"), dict) else None

    bullets: list[str] = []
    if str(commercial.get("headline") or "").strip():
        bullets.append(str(commercial.get("headline")))
    if readiness.get("member_count", 0) > 0:
        bullets.append(f"当前在带 {readiness.get('member_count')} 位岗位员工")
    if approved:
        bullets.append(f"本周已有 {approved} 轮正式任务完成确认")
    if submitted:
        bullets.append(f"{submitted} 个任务待育成师确认")
    if knowledge_active:
        bullets.append(f"{knowledge_active} 个补知识任务进行中")
    if latest_decision:
        bullets.append(f"最近经营决策：{latest_decision.get('action')}（净收益 ¥{float(latest_decision.get('net') or 0):.2f}）")
    if not bullets:
        bullets.append("系统已就绪，请从公司设置添加工种开始第一条业务线验证。")

    next_actions = list(commercial.get("next_actions") or [])
    next_step = readiness.get("next_step")
    if isinstance(next_step, dict) and next_step.get("label"):
        next_actions.insert(0, f"优先完成：{next_step.get('label')}（{next_step.get('hint') or ''}）")

    headline = str(commercial.get("headline") or "").strip()
    if not headline:
        headline = str(readiness.get("stage_label") or "经营简报")

    return {
        "period_label": "本周经营",
        "generated_at": finance.get("primary", {}).get("updated_at") or "",
        "headline": headline,
        "bullets": bullets[:6],
        "next_actions": next_actions[:5],
        "finance_verdict": commercial,
        "readiness_score": readiness.get("score", 0),
        "readiness_stage": readiness.get("stage_label", ""),
        "operations": {
            "members": readiness.get("member_count", 0),
            "work_types": readiness.get("work_type_count", 0),
            "tasks_approved": approved,
            "tasks_submitted": submitted,
            "knowledge_learning_active": knowledge_active,
            "training_reviews": int(training_review.get("changed_count") or 0),
        },
    }


def _user_members(runtime: dict) -> list[dict]:
    child_members = runtime.get("child_members") if isinstance(runtime.get("child_members"), dict) else {}
    items = child_members.get("items") if isinstance(child_members.get("items"), list) else []
    return [
        item for item in items
        if isinstance(item, dict)
        and str(item.get("primary_role") or "") != "talent_development"
        and str(item.get("status") or "active") != "archived"
        and not item.get("system_managed")
    ]


def _enabled_workers(workspace: Path) -> list[str]:
    registry = load_worker_registry_config(workspace)
    workers = registry.get("workers") if isinstance(registry.get("workers"), dict) else {}
    enabled: list[str] = []
    for worker_id, config in workers.items():
        if isinstance(config, dict) and config.get("enabled"):
            enabled.append(str(worker_id))
    return enabled


def get_commercial_readiness(workspace: Path, *, tenant_id: str = "default") -> dict:
    work_types_payload = load_work_types(workspace)
    work_type_items = work_types_payload.get("items") if isinstance(work_types_payload.get("items"), list) else []
    work_type_count = len([item for item in work_type_items if isinstance(item, dict)])

    enabled_workers = _enabled_workers(workspace)
    runtime = load_autonomy_runtime(workspace, tenant_id)
    members = _user_members(runtime)

    task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
    formal_tasks = task_center.get("items") if isinstance(task_center.get("items"), list) else []
    has_task_activity = any(
        isinstance(item, dict) and str(item.get("status") or "") in {"assigned", "submitted", "approved", "completed"}
        for item in formal_tasks
    )

    intake_center = runtime.get("intake_center") if isinstance(runtime.get("intake_center"), dict) else {}
    intake_items = intake_center.get("items") if isinstance(intake_center.get("items"), list) else []
    has_intake = any(isinstance(item, dict) and str(item.get("intake_id") or "").strip() for item in intake_items)
    has_intake_settled = any(
        isinstance(item, dict) and str(item.get("status") or "") == "settled"
        for item in intake_items
    )

    finance = get_finance_overview(workspace)
    primary = finance.get("primary") if isinstance(finance.get("primary"), dict) else {}
    has_finance = bool(str(primary.get("updated_at") or "").strip()) or has_intake_settled
    latest_decision = finance.get("latest_decision")
    has_decision = isinstance(latest_decision, dict)

    steps = [
        {
            "key": "work_type",
            "label": "已添加工种",
            "done": work_type_count > 0,
            "hint": "公司设置 → 岗位工种",
            "route": "/organization/parent/workspace?section=worktypes",
        },
        {
            "key": "worker",
            "label": "已启用执行器",
            "done": len(enabled_workers) > 0,
            "hint": "保存后需重启 Admin",
            "route": "/organization/parent/workspace?section=worktypes",
        },
        {
            "key": "member",
            "label": "已建档员工",
            "done": len(members) > 0,
            "hint": "育成师 → 画像建档",
            "route": "/organization/trainer/talent_development_officer/workspace?mode=portrait&portraitTab=summary",
        },
        {
            "key": "intake",
            "label": "商业接单已接入",
            "done": has_intake,
            "hint": "接单台录入外包/经营任务",
            "route": "/organization/intake?section=create",
        },
        {
            "key": "task",
            "label": "正式任务已流转",
            "done": has_task_activity,
            "hint": "接单分派或育成派任务 → 员工提交 → 确认",
            "route": "/organization/intake",
        },
        {
            "key": "finance",
            "label": "财务数据已落盘",
            "done": has_finance,
            "hint": "接单结算或 analytics 落盘",
            "route": "/organization/finance",
        },
        {
            "key": "decision",
            "label": "已记录经营决策",
            "done": has_decision,
            "hint": "财务页记录继续投入/调整/收缩",
            "route": "/organization/finance",
        },
    ]
    met = sum(1 for step in steps if step.get("done"))
    total = len(steps)
    score = int(round((met / total) * 100)) if total else 0

    if score >= 85 and has_finance and has_decision:
        stage = "monetizing"
        stage_label = "可对外演示经营闭环"
    elif score >= 50:
        stage = "operating"
        stage_label = "运营验证中"
    else:
        stage = "setup"
        stage_label = "基础配置阶段"

    blockers = [step["label"] for step in steps if not step.get("done")]
    next_step = next((step for step in steps if not step.get("done")), None)

    return {
        "score": score,
        "stage": stage,
        "stage_label": stage_label,
        "steps": steps,
        "met_count": met,
        "total_steps": total,
        "blockers": blockers,
        "next_step": next_step,
        "enabled_workers": enabled_workers,
        "work_type_count": work_type_count,
        "member_count": len(members),
    }
