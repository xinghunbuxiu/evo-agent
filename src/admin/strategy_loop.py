"""
策略自治循环：实验结果刷新与后台推进。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from core.tenant import TenantManager


def refresh_review_queue_experiment_runs(
    workspace: Path,
    tenant_id: str,
    task_queue,
    *,
    load_review_queue: Callable[[Path, str], list[dict]],
    save_review_queue: Callable[[Path, str, list[dict]], None],
    summarize_experiment_run: Callable[[object, dict], dict],
    record_experiment_run_validations: Callable[[Path, str, object, dict], None],
    build_strategy_upgrade_candidate: Callable[[dict, dict], dict | None],
    maybe_auto_accept_upgrade_candidate: Callable[[Path, str, dict], bool],
) -> list[dict]:
    items = load_review_queue(workspace, tenant_id)
    changed = False

    for item in items:
        runs = item.get("experiment_runs")
        if not isinstance(runs, list):
            continue

        latest_status = None
        for run in runs:
            if not isinstance(run, dict):
                continue
            summary = summarize_experiment_run(task_queue, run)
            if isinstance(run.get("summary"), dict):
                summary["sample_count_actual"] = run.get("sample_count_actual", summary.get("completed", 0))
            if run.get("summary") != summary:
                run["summary"] = summary
                changed = True
            validation_ids_before = list(run.get("validation_ids", [])) if isinstance(run.get("validation_ids"), list) else []
            record_experiment_run_validations(workspace, tenant_id, task_queue, run)
            if run.get("validation_ids") != validation_ids_before:
                changed = True
            latest_status = summary.get("status")

        if latest_status == "running":
            next_status = "running_experiment"
        elif latest_status == "improved":
            next_status = "experiment_improved"
        elif latest_status == "regressed":
            next_status = "experiment_regressed"
        elif latest_status == "mixed":
            next_status = "experiment_mixed"
        else:
            next_status = item.get("status")

        if next_status != item.get("status"):
            item["status"] = next_status
            changed = True

        latest_run = runs[0] if runs else None
        upgrade_candidate = item.get("upgrade_candidate")
        generated_candidate = (
            build_strategy_upgrade_candidate(item, latest_run)
            if isinstance(latest_run, dict)
            else None
        )
        if generated_candidate:
            if not isinstance(upgrade_candidate, dict) or upgrade_candidate.get("decision") == "pending":
                item["upgrade_candidate"] = {
                    **generated_candidate,
                    "decision": (
                        upgrade_candidate.get("decision")
                        if isinstance(upgrade_candidate, dict) and upgrade_candidate.get("decision")
                        else "pending"
                    ),
                    "decision_note": (
                        upgrade_candidate.get("decision_note")
                        if isinstance(upgrade_candidate, dict) and upgrade_candidate.get("decision_note")
                        else generated_candidate.get("decision_note")
                    ),
                    "decided_at": (
                        upgrade_candidate.get("decided_at")
                        if isinstance(upgrade_candidate, dict)
                        else None
                    ),
                }
                changed = True

        if maybe_auto_accept_upgrade_candidate(workspace, tenant_id, item):
            changed = True

    if changed:
        save_review_queue(workspace, tenant_id, items)
    return items


def advance_background_research_for_tenant(
    workspace: Path,
    tenant_id: str,
    task_queue,
    plugin_summary,
    tenant_manager: TenantManager,
    *,
    build_evolution_overview: Callable[..., dict],
    load_review_queue: Callable[[Path, str], list[dict]],
    generate_review_draft_fn: Callable[[Path, str, str], dict | None],
    generate_review_experiment_plan_fn: Callable[[Path, str, str], dict | None],
    run_review_experiment_fn: Callable[[Path, str, str, object], dict | None],
    refresh_review_queue_experiment_runs_fn: Callable[[Path, str, object], list[dict]],
    auto_promote_review_entries_fn: Callable[[Path, str, TenantManager], list[dict]],
) -> dict:
    overview = build_evolution_overview(
        workspace=workspace,
        tenant_id=tenant_id,
        task_queue=task_queue,
        plugin_summary=plugin_summary,
        tenant_manager=tenant_manager,
    )
    review_queue = load_review_queue(workspace, tenant_id)
    started_runs: list[str] = []

    for item in review_queue:
        if not isinstance(item, dict):
            continue
        review_id = str(item.get("id") or "")
        if not review_id:
            continue
        if item.get("reason") != "auto_review_case":
            continue
        if not isinstance(item.get("draft"), dict):
            generated = generate_review_draft_fn(workspace, tenant_id, review_id)
            if isinstance(generated, dict):
                item = generated
        if isinstance(item.get("draft"), dict) and not isinstance(item.get("experiment_plan"), dict):
            generated = generate_review_experiment_plan_fn(workspace, tenant_id, review_id)
            if isinstance(generated, dict):
                item = generated
        has_runs = isinstance(item.get("experiment_runs"), list) and bool(item.get("experiment_runs"))
        if isinstance(item.get("experiment_plan"), dict) and not has_runs:
            try:
                generated = run_review_experiment_fn(workspace, tenant_id, review_id, task_queue)
                if isinstance(generated, dict):
                    started_runs.append(review_id)
            except ValueError:
                pass

    refresh_review_queue_experiment_runs_fn(workspace, tenant_id, task_queue)
    promoted_entries = auto_promote_review_entries_fn(workspace, tenant_id, tenant_manager)
    return {
        "tenant_id": tenant_id,
        "review_queue_size": len(review_queue),
        "started_experiments": started_runs,
        "auto_promoted_reviews": [
            str(item.get("id") or item.get("strategy_id") or "")
            for item in promoted_entries
            if isinstance(item, dict)
        ],
        "summary": overview.get("summary", {}),
    }
