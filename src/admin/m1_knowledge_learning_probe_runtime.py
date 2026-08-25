"""M1 供给环学习探测：模型补知识候选 → training_plan + experience_journal 写回。"""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from admin.knowledge_learning_runtime import (
    sync_member_knowledge_learning_writeback,
    trigger_member_knowledge_learning_validation,
)
from admin.runtime_state import (
    create_employee_member_runtime,
    load_autonomy_runtime,
    load_learning_tasks,
    normalize_child_members_runtime,
    save_autonomy_runtime,
    save_learning_tasks,
)
from core.tenant import TenantManager


def run_knowledge_learning_probe(workspace: Path, *, tenant_id: str = "default") -> dict[str, Any]:
    normalized_tenant_id = str(tenant_id or "default").strip() or "default"
    baseline_runtime = deepcopy(load_autonomy_runtime(workspace, normalized_tenant_id))
    learning_baseline = load_learning_tasks(workspace)
    tenant_manager = TenantManager(workspace)
    baseline_policy = tenant_manager.get_external_learning_policy(normalized_tenant_id)
    live_model = str(os.getenv("EVO_M1_LIVE_MODEL") or "").strip().lower() in {"1", "true", "yes"}
    keep_member = str(os.getenv("EVO_M1_KEEP_PROBE_MEMBER") or "").strip().lower() in {"1", "true", "yes"}

    result: dict[str, Any] = {
        "ok": False,
        "mode": None,
        "member_id": None,
        "task_id": None,
        "journal_card_ok": False,
        "live_model": live_model,
        "kept": False,
    }
    previous_mock = os.environ.get("EVO_MODEL_PROVIDER_MOCK")
    if live_model:
        os.environ.pop("EVO_MODEL_PROVIDER_MOCK", None)
    else:
        os.environ["EVO_MODEL_PROVIDER_MOCK"] = "1"
    try:
        if live_model:
            provider = (
                baseline_policy.get("model_provider")
                if isinstance(baseline_policy.get("model_provider"), dict)
                else {}
            )
            if not (
                provider.get("enabled")
                and provider.get("base_url")
                and provider.get("api_key")
                and provider.get("model")
            ):
                result["detail"] = "live_model_requires_configured_model_provider"
                return result
            tenant_manager.set_external_learning_policy(
                normalized_tenant_id,
                allow_ai_assist=True,
                allow_web_research=bool(baseline_policy.get("allow_web_research", True)),
                allow_enterprise_sources=bool(baseline_policy.get("allow_enterprise_sources", True)),
                source_priority=list(baseline_policy.get("source_priority") or []),
                validation_required=bool(baseline_policy.get("validation_required", True)),
                model_provider=provider,
            )
        else:
            tenant_manager.set_external_learning_policy(
                normalized_tenant_id,
                allow_ai_assist=True,
                allow_web_research=bool(baseline_policy.get("allow_web_research", True)),
                allow_enterprise_sources=bool(baseline_policy.get("allow_enterprise_sources", True)),
                source_priority=list(baseline_policy.get("source_priority") or []),
                validation_required=bool(baseline_policy.get("validation_required", True)),
                model_provider={
                    "enabled": True,
                    "label": "openai_compatible",
                    "base_url": "https://api.example.invalid",
                    "api_key": "m1-probe-key",
                    "model": "mock-chat",
                },
            )

        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        child_members = normalize_child_members_runtime(
            runtime.get("child_members"),
            legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
        )
        employee = create_employee_member_runtime(
            tenant_id=normalized_tenant_id,
            name="M1 Knowledge Learner",
            role_label="M1 Knowledge Learner",
            role_key="m1_knowledge_learner",
            self_description="probe knowledge learning writeback",
            long_term_goal="validate model-assisted knowledge learning",
            work_type_id=None,
            work_type_title=None,
            department_id="operations",
        )
        member_id = str(employee.get("member_id") or "").strip()
        result["member_id"] = member_id
        items = child_members.get("items") if isinstance(child_members.get("items"), list) else []
        items.append(employee)
        child_members["items"] = items
        runtime["child_members"] = child_members

        task_id = f"learning:m1_knowledge:{member_id}"
        learning_state = load_learning_tasks(workspace)
        tasks = learning_state.get("tasks") if isinstance(learning_state.get("tasks"), dict) else {}
        tasks[task_id] = {
            "task_id": task_id,
            "tenant_id": normalized_tenant_id,
            "member_id": member_id,
            "source": "memory_hub_auto",
            "title": "M1 补知识探测",
            "goal": "学会整理可执行岗位方法",
            "queries": ["岗位方法", "最小验证"],
            "status": "needs_learning",
            "role_label": "M1 Knowledge Learner",
        }
        save_learning_tasks(workspace, {"tasks": tasks})
        employee["training_plan"] = {
            **(employee.get("training_plan") if isinstance(employee.get("training_plan"), dict) else {}),
            "knowledge_learning_task_id": task_id,
            "stage": "knowledge_supplementing",
        }
        # re-upsert member with training plan link
        next_items = []
        for item in items:
            if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id:
                next_items.append(employee)
            else:
                next_items.append(item)
        child_members["items"] = next_items
        runtime["child_members"] = child_members
        save_autonomy_runtime(workspace, runtime, normalized_tenant_id)

        def _refresh_runtime_learning_tasks(**_kwargs):
            return {"tasks": load_learning_tasks(workspace).get("tasks") or {}}

        validate = trigger_member_knowledge_learning_validation(
            workspace=workspace,
            tenant_id=normalized_tenant_id,
            task_id=task_id,
            refresh_runtime_learning_tasks=_refresh_runtime_learning_tasks,
            tenant_manager=tenant_manager,
            task_queue=None,
        ) or {}
        result["mode"] = validate.get("mode")
        result["task_id"] = task_id
        result["status"] = validate.get("status")

        runtime = load_autonomy_runtime(workspace, normalized_tenant_id)
        runtime = sync_member_knowledge_learning_writeback(
            workspace=workspace,
            runtime=runtime,
            tenant_id=normalized_tenant_id,
            normalize_child_members_runtime=normalize_child_members_runtime,
        )
        grown = None
        members = runtime.get("child_members") if isinstance(runtime.get("child_members"), dict) else {}
        for item in (members.get("items") if isinstance(members.get("items"), list) else []):
            if isinstance(item, dict) and str(item.get("member_id") or "").strip() == member_id:
                grown = item
                break
        journal = grown.get("experience_journal") if isinstance(grown, dict) and isinstance(grown.get("experience_journal"), dict) else {}
        cards = journal.get("cards") if isinstance(journal.get("cards"), list) else []
        has_learning_card = any(
            isinstance(card, dict) and str(card.get("signature") or "").startswith("knowledge_learning:")
            for card in cards
        )
        training = grown.get("training_plan") if isinstance(grown, dict) and isinstance(grown.get("training_plan"), dict) else {}
        result["journal_card_ok"] = has_learning_card
        result["training_status"] = training.get("knowledge_learning_status")

        # One approved formal task + knowledge card should unlock independence readiness
        from admin.formal_task_evolution_runtime import evaluate_independence_readiness
        from admin.task_center_runtime import upsert_task

        task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
        upsert_task(task_center, {
            "task_id": f"task:{member_id}:m1_knowledge_indep",
            "member_id": member_id,
            "title": "M1 knowledge independence seed",
            "status": "approved",
            "assigned_at": training.get("knowledge_learning_updated_at"),
            "approved_at": training.get("knowledge_learning_updated_at"),
        })
        runtime["task_center"] = task_center
        indep = evaluate_independence_readiness(member=grown or {}, task_center=task_center)
        result["independence_ready"] = bool(indep.get("ready_for_independence"))
        result["independence_met"] = indep.get("met_criteria_count")
        result["ok"] = (
            str(validate.get("mode") or "") == "knowledge_learning_model_provider"
            and str(validate.get("status") or "") == "candidate_found"
            and has_learning_card
            and bool(result["independence_ready"])
        )
        if keep_member and result["ok"]:
            save_autonomy_runtime(workspace, runtime, normalized_tenant_id)
            result["kept"] = True
        return result
    finally:
        if previous_mock is None:
            os.environ.pop("EVO_MODEL_PROVIDER_MOCK", None)
        else:
            os.environ["EVO_MODEL_PROVIDER_MOCK"] = previous_mock
        if not keep_member:
            save_autonomy_runtime(workspace, baseline_runtime, normalized_tenant_id)
            save_learning_tasks(workspace, learning_baseline if isinstance(learning_baseline, dict) else {"tasks": {}})
        tenant_manager.set_external_learning_policy(
            normalized_tenant_id,
            allow_ai_assist=bool(baseline_policy.get("allow_ai_assist", True)),
            allow_web_research=bool(baseline_policy.get("allow_web_research", True)),
            allow_enterprise_sources=bool(baseline_policy.get("allow_enterprise_sources", True)),
            source_priority=list(baseline_policy.get("source_priority") or []),
            validation_required=bool(baseline_policy.get("validation_required", True)),
            model_provider=baseline_policy.get("model_provider") if isinstance(baseline_policy.get("model_provider"), dict) else None,
        )
