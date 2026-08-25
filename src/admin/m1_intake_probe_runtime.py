"""M1 商业接单闭环探测：create → analyze → assign → submit/approve 钩子 → settle。

不绑定具体平台名；临时工种与 runtime 变更在 finally 中恢复。
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from admin.intake_runtime import (
    analyze_intake,
    assign_intake,
    attach_operation_artifacts_to_intake,
    create_intake,
    load_routing_feedback,
    mark_intake_delivered_from_task,
    mark_intake_in_progress_from_task,
    settle_intake,
)
from admin.runtime_state import (
    create_employee_member_runtime,
    load_autonomy_runtime,
    normalize_child_members_runtime,
    save_autonomy_runtime,
)
from admin.task_center_runtime import upsert_task
from work_types import load_work_types, save_work_types

M1_INTAKE_PROBE_WORK_TYPE_ID = "__m1_intake_probe__"


def run_intake_commercial_probe(workspace: Path, *, tenant_id: str = "default") -> dict[str, Any]:
    """Run a disposable intake→settle loop and restore baseline runtime/work_types."""
    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
    baseline_runtime = deepcopy(load_autonomy_runtime(workspace, normalized_tenant_id))
    wt_payload = load_work_types(workspace)
    baseline_wt_items = [
        item for item in (wt_payload.get("items") if isinstance(wt_payload.get("items"), list) else [])
        if isinstance(item, dict)
        and str(item.get("work_type_id") or "").strip() != M1_INTAKE_PROBE_WORK_TYPE_ID
    ]
    version = int(wt_payload.get("version") or 1) if isinstance(wt_payload, dict) else 1

    probe_work_type = {
        "work_type_id": M1_INTAKE_PROBE_WORK_TYPE_ID,
        "title": "M1 Intake Probe",
        "status": "active",
        "enabled": True,
        "capability_type": "content_ops",
        "department_id": "operations",
        "finance_project_id": "m1_intake_probe_project",
        "collaboration": {
            "can_provide_capabilities": ["content_draft", "channel_publish", "content_ops"],
        },
        "intake": {
            "default_capabilities": ["content_draft"],
        },
    }
    save_work_types(
        workspace,
        {
            "version": version,
            "items": [*baseline_wt_items, probe_work_type],
        },
    )

    finance_path = workspace / ".admin" / "finance" / "m1_intake_probe_project.json"
    finance_existed = finance_path.is_file()
    finance_backup = finance_path.read_text(encoding="utf-8") if finance_existed else None
    feedback_path = workspace / ".admin" / "intake_routing_feedback.json"
    feedback_existed = feedback_path.is_file()
    feedback_backup = feedback_path.read_text(encoding="utf-8") if feedback_existed else None

    result: dict[str, Any] = {
        "member_id": None,
        "intake_id": None,
        "task_id": None,
        "settled": False,
        "project_id": None,
    }
    try:
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        child_members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        employee = create_employee_member_runtime(
            tenant_id=normalized_tenant_id,
            name="M1 Intake Probe",
            role_label="M1 Intake Probe",
            role_key="m1_intake_probe",
            self_description="m1 intake commercial probe",
            long_term_goal="validate intake settle loop",
            work_type_id=M1_INTAKE_PROBE_WORK_TYPE_ID,
            work_type_title="M1 Intake Probe",
            department_id="operations",
        )
        member_id = str(employee.get("member_id") or "").strip()
        result["member_id"] = member_id
        items = child_members.get("items") if isinstance(child_members.get("items"), list) else []
        items.append(employee)
        child_members["items"] = items
        runtime["child_members"] = child_members
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)

        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        intake = create_intake(
            workspace=workspace,
            runtime=runtime,
            title="M1 商业接单探测",
            description="需要内容草稿与发布类交付，用于验证消费环结算",
            expected_deliverables=["内容草稿摘要", "复盘"],
            needed_capabilities=["content"],
            source="outsourcing",
            budget=1200,
            quoted_amount=1500,
            currency="CNY",
            client_label="m1_probe_client",
            auto_analyze=True,
        )
        result["intake_id"] = intake.get("intake_id")
        if str(intake.get("status") or "") == "received":
            intake = analyze_intake(
                workspace=workspace,
                runtime=runtime,
                intake_id=str(intake.get("intake_id")),
            )
        assigned = assign_intake(
            workspace=workspace,
            runtime=runtime,
            intake_id=str(intake.get("intake_id")),
            member_id=member_id,
        )
        task = assigned.get("task") if isinstance(assigned.get("task"), dict) else {}
        result["task_id"] = task.get("task_id")
        if not result["task_id"]:
            raise RuntimeError("assign_intake 未返回 task_id")

        # Simulate operation_* finalize → artifact attach (no real worker / platform)
        draft_file = workspace / ".admin" / "m1_probe_artifacts" / "content_draft.md"
        draft_file.parent.mkdir(parents=True, exist_ok=True)
        draft_file.write_text("# M1 probe draft\n\ncommercial intake fulfillment attach\n", encoding="utf-8")

        class _ProbeQueueTask:
            id = "job:m1_intake_probe_op"
            type = "operation_content_draft"
            payload = {
                "_source": "intake_fulfillment",
                "intake_id": str(result.get("intake_id") or ""),
                "member_id": member_id,
            }

        attach_info = attach_operation_artifacts_to_intake(
            workspace=workspace,
            runtime=runtime,
            queue_task=_ProbeQueueTask(),
            operation_result={
                "message": "probe draft ready",
                "result": {"draft_path": str(draft_file)},
            },
        )
        result["artifact_attach_ok"] = bool(attach_info and int(attach_info.get("artifact_count") or 0) >= 1)
        result["artifact_count"] = (attach_info or {}).get("artifact_count")
        result["fulfillment_status"] = (attach_info or {}).get("fulfillment_status")

        task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
        # Prefer post-attach formal task so fulfillment.artifacts are preserved
        for item in (task_center.get("items") if isinstance(task_center.get("items"), list) else []):
            if isinstance(item, dict) and str(item.get("task_id") or "").strip() == str(result.get("task_id") or ""):
                task = item
                break
        task = upsert_task(task_center, {
            **task,
            "status": "submitted",
            "result_summary": str(task.get("result_summary") or "探测交付物已完成"),
            "reflection": "接单消费环探测复盘",
            "submitted_at": task.get("assigned_at"),
        })
        runtime["task_center"] = task_center
        mark_intake_in_progress_from_task(runtime=runtime, task=task)

        task = upsert_task(task_center, {
            **task,
            "status": "approved",
            "review_note": "探测验收通过",
            "approved_at": task.get("submitted_at") or task.get("assigned_at"),
        })
        runtime["task_center"] = task_center
        mark_intake_delivered_from_task(runtime=runtime, task=task)

        settled = settle_intake(
            workspace=workspace,
            runtime=runtime,
            intake_id=str(intake.get("intake_id")),
            settled_amount=1500,
            note="M1 intake probe settle",
        )
        settled_intake = settled.get("intake") if isinstance(settled.get("intake"), dict) else {}
        result["settled"] = str(settled_intake.get("status") or "") == "settled"
        result["project_id"] = settled_intake.get("project_id")
        result["settled_amount"] = settled_intake.get("settled_amount")
        result["growth_member_id"] = settled.get("growth_member_id")
        # Demo gap: settle must be visible in finance store / overview
        from admin.finance_runtime import get_finance_summary, list_finance_projects

        project_id = str(result.get("project_id") or "").strip()
        finance_projects = list_finance_projects(workspace)
        summary = get_finance_summary(workspace, project_id=project_id) if project_id else {}
        revenue = summary.get("revenue") if isinstance(summary, dict) else None
        try:
            revenue_f = float(revenue) if revenue is not None else 0.0
        except (TypeError, ValueError):
            revenue_f = 0.0
        result["finance_visible_ok"] = bool(project_id and project_id in finance_projects and revenue_f >= 1500)
        result["finance_revenue"] = revenue_f
        result["finance_projects"] = finance_projects
        # Inspect in-memory growth before restore (supply writeback)
        grown = None
        members = runtime.get("child_members") if isinstance(runtime.get("child_members"), dict) else {}
        for item in (members.get("items") if isinstance(members.get("items"), list) else []):
            if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id:
                grown = item
                break
        growth = grown.get("growth_state") if isinstance(grown, dict) and isinstance(grown.get("growth_state"), dict) else {}
        journal = grown.get("experience_journal") if isinstance(grown, dict) and isinstance(grown.get("experience_journal"), dict) else {}
        cards = journal.get("cards") if isinstance(journal.get("cards"), list) else []
        has_commercial_card = any(
            isinstance(card, dict) and str(card.get("signature") or "").startswith("commercial_intake:")
            for card in cards
        )
        result["supply_growth_ok"] = (
            int(growth.get("commercial_settled_count") or 0) >= 1 and has_commercial_card
        )
        result["commercial_settled_count"] = growth.get("commercial_settled_count")
        result["pending_git_export"] = bool(growth.get("pending_git_export"))
        result["git_export_status"] = growth.get("last_git_export_status")
        result["git_export_path"] = growth.get("last_git_export_path")
        export_path = str(growth.get("last_git_export_path") or "").strip()
        export_root = Path(str(growth.get("last_git_export_root") or ""))
        result["git_export_ok"] = (
            str(growth.get("last_git_export_status") or "") in {"local_exported", "exported", "local_only"}
            and bool(export_path)
            and (export_root / export_path).is_file()
        )
        # cleanup probe local export artifact (keep directory structure)
        if result["git_export_ok"] and (export_root / export_path).is_file():
            try:
                (export_root / export_path).unlink()
            except Exception:
                pass
        feedback_items = load_routing_feedback(workspace)
        settle_feedback = any(
            isinstance(item, dict)
            and str(item.get("event_type") or "") == "settle_success"
            and str(item.get("outcome") or "") == "settled"
            and str(item.get("member_id") or "").strip() == member_id
            and str(item.get("intake_id") or "") == str(result.get("intake_id") or "")
            for item in feedback_items
        )
        result["routing_feedback_ok"] = settle_feedback

        # Second analyze should surface feedback_bonus for the settled member
        follow = create_intake(
            workspace=workspace,
            runtime=runtime,
            title="M1 路由反馈加权探测",
            description="二次分析应命中历史商业结算加权",
            expected_deliverables=["复盘"],
            needed_capabilities=["content"],
            source="outsourcing",
            budget=800,
            quoted_amount=900,
            currency="CNY",
            client_label="m1_probe_client_follow",
            auto_analyze=True,
        )
        if str(follow.get("status") or "") == "received":
            follow = analyze_intake(
                workspace=workspace,
                runtime=runtime,
                intake_id=str(follow.get("intake_id")),
            )
        routing = follow.get("routing") if isinstance(follow.get("routing"), dict) else {}
        candidates = routing.get("candidates") if isinstance(routing.get("candidates"), list) else []
        bonus = 0
        journal_bonus = 0
        for cand in candidates:
            if isinstance(cand, dict) and str(cand.get("member_id") or "").strip() == member_id:
                bonus = int(cand.get("feedback_bonus") or 0)
                journal_bonus = int(cand.get("journal_bonus") or 0)
                break
        result["feedback_bonus"] = bonus
        result["feedback_bonus_ok"] = bonus > 0
        result["journal_bonus"] = journal_bonus
        result["journal_bonus_ok"] = journal_bonus > 0
        # Do not persist probe runtime; finally restores baseline.
        return result
    finally:
        save_work_types(workspace, {"version": version, "items": baseline_wt_items})
        save_autonomy_runtime(workspace, baseline_runtime, normalized_tenant_id)
        if finance_backup is not None:
            finance_path.parent.mkdir(parents=True, exist_ok=True)
            finance_path.write_text(finance_backup, encoding="utf-8")
        elif finance_path.is_file():
            finance_path.unlink()
        if feedback_backup is not None:
            feedback_path.parent.mkdir(parents=True, exist_ok=True)
            feedback_path.write_text(feedback_backup, encoding="utf-8")
        elif feedback_path.is_file():
            feedback_path.unlink()
        probe_draft = workspace / ".admin" / "m1_probe_artifacts" / "content_draft.md"
        if probe_draft.is_file():
            try:
                probe_draft.unlink()
            except Exception:
                pass
        probe_dir = workspace / ".admin" / "m1_probe_artifacts"
        if probe_dir.is_dir() and not any(probe_dir.iterdir()):
            try:
                probe_dir.rmdir()
            except Exception:
                pass


M1_SECOND_WORK_TYPE_A = "__m1_wt_content__"
M1_SECOND_WORK_TYPE_B = "__m1_wt_research__"


def run_second_work_type_routing_probe(workspace: Path, *, tenant_id: str = "default") -> dict[str, Any]:
    """Prove a second work type routes by config only (no intake_runtime code branches)."""
    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
    baseline_runtime = deepcopy(load_autonomy_runtime(workspace, normalized_tenant_id))
    wt_payload = load_work_types(workspace)
    baseline_wt_items = [
        item for item in (wt_payload.get("items") if isinstance(wt_payload.get("items"), list) else [])
        if isinstance(item, dict)
        and str(item.get("work_type_id") or "").strip()
        not in {M1_SECOND_WORK_TYPE_A, M1_SECOND_WORK_TYPE_B, M1_INTAKE_PROBE_WORK_TYPE_ID}
    ]
    version = int(wt_payload.get("version") or 1) if isinstance(wt_payload, dict) else 1
    result: dict[str, Any] = {
        "ok": False,
        "recommended_member_id": None,
        "expected_member_id": None,
    }
    try:
        save_work_types(
            workspace,
            {
                "version": version,
                "items": [
                    *baseline_wt_items,
                    {
                        "work_type_id": M1_SECOND_WORK_TYPE_A,
                        "title": "M1 Content WT",
                        "status": "active",
                        "enabled": True,
                        "capability_type": "content_ops",
                        "department_id": "operations",
                        "collaboration": {
                            "can_provide_capabilities": ["content_draft", "content_ops"],
                        },
                    },
                    {
                        "work_type_id": M1_SECOND_WORK_TYPE_B,
                        "title": "M1 Research WT",
                        "status": "active",
                        "enabled": True,
                        "capability_type": "research_ops",
                        "department_id": "research",
                        "collaboration": {
                            "can_provide_capabilities": ["research_brief", "research_ops"],
                        },
                    },
                ],
            },
        )
        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        child_members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        content_member = create_employee_member_runtime(
            tenant_id=normalized_tenant_id,
            name="M1 Content Emp",
            role_label="M1 Content Emp",
            role_key="m1_content_emp",
            self_description="content",
            long_term_goal="content delivery",
            work_type_id=M1_SECOND_WORK_TYPE_A,
            work_type_title="M1 Content WT",
            department_id="operations",
        )
        research_member = create_employee_member_runtime(
            tenant_id=normalized_tenant_id,
            name="M1 Research Emp",
            role_label="M1 Research Emp",
            role_key="m1_research_emp",
            self_description="research",
            long_term_goal="research delivery",
            work_type_id=M1_SECOND_WORK_TYPE_B,
            work_type_title="M1 Research WT",
            department_id="research",
        )
        content_id = str(content_member.get("member_id") or "").strip()
        research_id = str(research_member.get("member_id") or "").strip()
        result["expected_member_id"] = research_id
        items = child_members.get("items") if isinstance(child_members.get("items"), list) else []
        items.extend([content_member, research_member])
        child_members["items"] = items
        runtime["child_members"] = child_members
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)

        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        intake = create_intake(
            workspace=workspace,
            runtime=runtime,
            title="M1 第二工种路由探测",
            description="需要研究简报类能力，不应路由到内容工种员工",
            expected_deliverables=["研究简报"],
            needed_capabilities=["research_brief"],
            source="outsourcing",
            budget=500,
            quoted_amount=500,
            currency="CNY",
            client_label="m1_second_wt",
            auto_analyze=True,
        )
        if str(intake.get("status") or "") == "received":
            intake = analyze_intake(
                workspace=workspace,
                runtime=runtime,
                intake_id=str(intake.get("intake_id")),
            )
        routing = intake.get("routing") if isinstance(intake.get("routing"), dict) else {}
        recommended = str(routing.get("recommended_member_id") or "").strip()
        result["recommended_member_id"] = recommended or None
        result["intake_id"] = intake.get("intake_id")
        candidates = routing.get("candidates") if isinstance(routing.get("candidates"), list) else []
        candidate_ids = [
            str(c.get("member_id") or "").strip()
            for c in candidates
            if isinstance(c, dict)
        ]
        result["candidate_ids"] = candidate_ids
        # Research employee must win; content employee must not be sole/top recommendation
        result["ok"] = bool(recommended and recommended == research_id and research_id in candidate_ids)
        result["content_member_id"] = content_id
        return result
    finally:
        save_work_types(workspace, {"version": version, "items": baseline_wt_items})
        save_autonomy_runtime(workspace, baseline_runtime, normalized_tenant_id)
