"""
Mission run 构建时的通用组装逻辑。
"""

from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path
from typing import Callable


def create_mission_run_builder(
    *,
    build_mission_actions: Callable[..., dict],
) -> Callable[..., dict]:
    def build_mission_run(
        *,
        workspace: Path,
        task_queue,
        tenant_id: str,
        plan: dict,
        context: dict,
    ) -> dict:
        mission_run_id = f"mission_{tenant_id}_{secrets.token_hex(6)}"
        mission_kind = str(plan.get("mission_kind") or "")
        work_type = plan.get("work_type", {}) if isinstance(plan.get("work_type"), dict) else {}
        work_type_summary = plan.get("work_type_summary", {}) if isinstance(plan.get("work_type_summary"), dict) else {}
        work_type_validation = plan.get("work_type_validation", {}) if isinstance(plan.get("work_type_validation"), dict) else {}
        runtime_route = plan.get("runtime_route", {}) if isinstance(plan.get("runtime_route"), dict) else {}

        action_state = build_mission_actions(
            task_queue=task_queue,
            tenant_id=tenant_id,
            mission_run_id=mission_run_id,
            plan=plan,
            context=context,
            work_type=work_type,
            work_type_summary=work_type_summary,
        )
        resolved_context = action_state.get("resolved_context", {})
        if not isinstance(resolved_context, dict):
            resolved_context = dict(context)

        autonomy_session_id = str(
            resolved_context.get("autonomy_session_id")
            or mission_run_id
        ).strip() or mission_run_id
        root_mission_run_id = str(
            resolved_context.get("root_mission_run_id")
            or resolved_context.get("previous_mission_run_id")
            or mission_run_id
        ).strip() or mission_run_id
        parent_mission_run_id = str(
            resolved_context.get("previous_mission_run_id")
            or ""
        ).strip() or None
        resolved_context["autonomy_session_id"] = autonomy_session_id
        resolved_context["root_mission_run_id"] = root_mission_run_id

        submitted_task_ids = action_state.get("submitted_task_ids", [])
        if not isinstance(submitted_task_ids, list):
            submitted_task_ids = []
        actions = action_state.get("actions", [])
        if not isinstance(actions, list):
            actions = []
        counts = action_state.get("counts", {})
        if not isinstance(counts, dict):
            counts = {"submitted": 0, "needs_learning": 0, "needs_input": 0, "planned_only": 0}
        overall_status = str(action_state.get("status") or "planning_only")
        mission_skill_ids = action_state.get("matched_verified_skill_ids", [])
        if not isinstance(mission_skill_ids, list):
            mission_skill_ids = []

        return {
            "mission_run_id": mission_run_id,
            "autonomy_session_id": autonomy_session_id,
            "root_mission_run_id": root_mission_run_id,
            "parent_mission_run_id": parent_mission_run_id,
            "tenant_id": tenant_id,
            "goal": plan.get("goal"),
            "mission_kind": mission_kind,
            "title": plan.get("title"),
            "work_type": work_type,
            "work_type_summary": work_type_summary,
            "work_type_validation": work_type_validation,
            "runtime_route": runtime_route,
            "created_at": datetime.now().isoformat(),
            "status": overall_status,
            "context": resolved_context,
            "counts": counts,
            "matched_verified_skill_ids": mission_skill_ids,
            "submitted_task_ids": submitted_task_ids,
            "actions": actions,
            "plan": plan,
        }

    return build_mission_run


__all__ = ["create_mission_run_builder"]
