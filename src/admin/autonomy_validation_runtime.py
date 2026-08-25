"""
自治学习验证运行时：研究扩展、自动验证、观察态推进、历史学习任务回放。
"""

from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
from typing import Callable


def create_autonomy_validation_bindings(
    *,
    task_priority_cls,
    load_learning_tasks: Callable,
    save_learning_tasks: Callable,
    load_review_queue: Callable,
    refresh_review_queue_experiment_runs: Callable,
    generate_review_draft: Callable,
    generate_review_experiment_plan: Callable,
    run_review_experiment: Callable,
    latest_sample_task: Callable,
    execute_learning_task: Callable,
    parse_iso_datetime: Callable,
    draft_learning_signature: Callable,
    detect_local_codex: Callable,
    run_local_codex_learning: Callable,
    trim_candidate_text: Callable,
    build_task_comparison: Callable,
    record_replay_validation: Callable,
    record_growth_event: Callable,
    safe_float: Callable[[object, float], float],
    build_snapshot_signature: Callable,
    make_learning_task_id: Callable,
):
    def append_learning_task_status(learning_task: dict, status: str) -> None:
        if not isinstance(learning_task, dict):
            return
        history = learning_task.get("status_history", []) if isinstance(learning_task.get("status_history"), list) else []
        if not history or history[-1].get("status") != status:
            history.append({
                "status": status,
                "at": learning_task.get("updated_at") or datetime.now().isoformat(),
            })
        learning_task["status_history"] = history

    def merge_learning_source_runs(existing_runs: list[dict] | None, new_run: dict) -> list[dict]:
        runs = existing_runs if isinstance(existing_runs, list) else []
        merged: list[dict] = []
        replaced = False
        source_name = str(new_run.get("source") or "")
        for item in runs:
            if not isinstance(item, dict):
                continue
            if str(item.get("source") or "") == source_name:
                merged.append(new_run)
                replaced = True
            else:
                merged.append(item)
        if not replaced:
            merged.append(new_run)
        return merged

    def trigger_historical_review_validation(
        workspace: Path,
        tenant_id: str,
        review_id: str,
        task_queue,
    ) -> dict:
        entry = load_review_queue(workspace, tenant_id)
        target = next((item for item in entry if item.get("id") == review_id), None)
        if not target:
            raise ValueError("历史学习任务不存在")
        if not isinstance(target.get("draft"), dict):
            target = generate_review_draft(workspace, tenant_id, review_id) or target
        if not isinstance(target.get("experiment_plan"), dict):
            target = generate_review_experiment_plan(workspace, tenant_id, review_id) or target
        target = run_review_experiment(workspace, tenant_id, review_id, task_queue)
        if not isinstance(target, dict):
            raise ValueError("历史学习任务尚未准备好实验计划")
        latest_run = (target.get("experiment_runs") or [{}])[0]
        return {
            "mode": "historical_review_experiment",
            "review_id": review_id,
            "status": target.get("status"),
            "created_task_ids": latest_run.get("task_ids", []),
            "source_task_ids": latest_run.get("source_task_ids", []),
            "message": "已基于历史学习档案发起新一轮验证实验",
        }

    def trigger_learning_task_validation(
        workspace: Path,
        tenant_id: str,
        task_id: str,
        task_queue,
    ) -> dict:
        if task_id.startswith(f"historical:{tenant_id}:"):
            review_id = task_id.split(f"historical:{tenant_id}:", 1)[1]
            return trigger_historical_review_validation(workspace, tenant_id, review_id, task_queue)

        learning_state = load_learning_tasks(workspace)
        tasks = learning_state.get("tasks", {}) if isinstance(learning_state, dict) else {}
        payload = tasks.get(task_id)
        if not isinstance(payload, dict):
            raise ValueError("学习任务不存在")

        sample = {
            "bundle_path": payload.get("bundle_path"),
            "source_dir": payload.get("source_dir"),
            "sample_signature": payload.get("sample_signature"),
            "latest_mtime": 0.0,
        }
        reconstruct_task = latest_sample_task(task_queue, tenant_id, sample, "reconstruct")
        analyze_task = latest_sample_task(task_queue, tenant_id, sample, "analyze")
        source_task = reconstruct_task or analyze_task
        if not source_task:
            raise ValueError("当前学习任务还没有可重放的源任务")

        replay_payload = copy.deepcopy(source_task.payload or {})
        replay_payload["_replay_of"] = source_task.id
        replay_payload["_learning_task_id"] = task_id
        created = task_queue.submit(
            task_type=source_task.type,
            payload=replay_payload,
            priority=task_priority_cls.HIGH,
            tenant_id=tenant_id,
        )
        payload["auto_validation"] = {
            "status": "started",
            "source": "manual_validate",
            "triggered_at": datetime.now().isoformat(),
            "created_task_ids": [created.id],
            "source_task_id": source_task.id,
        }
        payload["status"] = "validating"
        payload["updated_at"] = datetime.now().isoformat()
        payload["next_validation_action"] = "已手动发起观察重放，等待比较当前结果与上一轮基线"
        status_history = payload.get("status_history", []) if isinstance(payload.get("status_history"), list) else []
        if not status_history or status_history[-1].get("status") != "validating":
            status_history.append({
                "status": "validating",
                "at": payload["updated_at"],
            })
        payload["status_history"] = status_history
        tasks[task_id] = payload
        save_learning_tasks(workspace, learning_state)
        return {
            "mode": "live_task_replay",
            "source_task_id": source_task.id,
            "task_type": source_task.type,
            "created_task_ids": [created.id],
            "message": "已基于当前学习任务发起重放验证",
        }

    def maybe_expand_mission_plan_learning_task(
        workspace: Path,
        tenant_manager,
        tenant_id: str,
        learning_task: dict,
    ) -> dict:
        if not isinstance(learning_task, dict):
            return learning_task
        if str(learning_task.get("source") or "") != "mission_plan":
            return learning_task

        status = str(learning_task.get("status") or "")
        if status in {"needs_input", "validating", "validated_improved", "validated_unchanged", "resolved", "validated_regressed", "validated_mixed"}:
            return learning_task

        last_research_at = parse_iso_datetime(str(learning_task.get("last_research_at") or ""))
        cooldown_seconds = 300 if status in {"needs_learning", "ready", "researching"} else 900
        if last_research_at and (datetime.now() - last_research_at).total_seconds() < cooldown_seconds:
            return learning_task

        sample = {
            "bundle_path": learning_task.get("bundle_path"),
            "source_dir": learning_task.get("source_dir"),
            "sample_signature": learning_task.get("sample_signature") or draft_learning_signature(learning_task),
        }
        issue_category = str(learning_task.get("issue_category") or learning_task.get("gap_type") or "strategy_gap")
        diagnosis = {
            "bundle_path": sample.get("bundle_path"),
            "source_dir": sample.get("source_dir"),
            "sample_signature": sample.get("sample_signature"),
            "research_state": "planning" if status in {"needs_learning", "ready"} else "researching",
            "stable": False,
            "analyze": {},
            "reconstruct": {
                "issue_category": issue_category,
                "recommended_actions": learning_task.get("next_actions", []),
                "issue_hints": learning_task.get("learning_objectives", []),
            },
        }
        policy = tenant_manager.get_external_learning_policy(tenant_id)
        auto_sources = learning_task.get("preferred_sources", []) if isinstance(learning_task.get("preferred_sources"), list) else policy.get("source_priority", [])
        auto_sources = [
            source for source in auto_sources
            if source in {"local_memory", "platform_shared", "historical_archive", "enterprise_repo"}
        ]
        if not auto_sources:
            auto_sources = ["local_memory", "platform_shared", "historical_archive"]
        learning_plan = {
            "policy": policy,
            "preferred_sources": auto_sources,
            "queries": learning_task.get("queries", []) if isinstance(learning_task.get("queries"), list) else [],
            "validation_gate": learning_task.get("validation_gate") or "候选方案需要经过真实样本或任务验证后才能晋升",
        }

        researched = execute_learning_task(
            workspace=workspace,
            tenant_manager=tenant_manager,
            tenant_id=tenant_id,
            sample=sample,
            diagnosis=diagnosis,
            learning_plan=learning_plan,
        )

        current = copy.deepcopy(learning_task)
        current["status"] = researched.get("status", current.get("status"))
        current["queries"] = researched.get("queries", current.get("queries", []))
        current["preferred_sources"] = researched.get("preferred_sources", current.get("preferred_sources", []))
        current["validation_gate"] = researched.get("validation_gate", current.get("validation_gate"))
        current["source_runs"] = [
            *([item for item in current.get("source_runs", []) if isinstance(item, dict) and item.get("source") == "mission_plan"]),
            *(researched.get("source_runs", []) if isinstance(researched.get("source_runs"), list) else []),
        ]
        researched_candidates = researched.get("candidate_approaches", []) if isinstance(researched.get("candidate_approaches"), list) else []
        current["candidate_approaches"] = researched_candidates or current.get("candidate_approaches", [])
        current["next_validation_action"] = researched.get("next_validation_action") or current.get("next_validation_action")
        current["sample_signature"] = sample.get("sample_signature")
        current["last_research_at"] = datetime.now().isoformat()
        current["research_attempts"] = int(current.get("research_attempts", 0) or 0) + 1
        current["updated_at"] = datetime.now().isoformat()
        if current.get("status") in {"ready_for_validation", "candidate_found"}:
            append_learning_task_status(current, current["status"])
        return current

    def maybe_ai_assist_mission_plan_learning_task(
        workspace: Path,
        tenant_manager,
        tenant_id: str,
        learning_task: dict,
    ) -> dict:
        if not isinstance(learning_task, dict):
            return learning_task
        if str(learning_task.get("source") or "") != "mission_plan":
            return learning_task

        status = str(learning_task.get("status") or "")
        if status not in {"awaiting_connector", "no_match", "needs_learning", "researching"}:
            return learning_task
        if learning_task.get("blockers"):
            return learning_task

        policy = tenant_manager.get_external_learning_policy(tenant_id)
        if not policy.get("allow_ai_assist", True):
            return learning_task

        source_runs = learning_task.get("source_runs", []) if isinstance(learning_task.get("source_runs"), list) else []
        existing_ai_run = next(
            (item for item in source_runs if isinstance(item, dict) and item.get("source") == "ai_assist"),
            None,
        )
        if isinstance(existing_ai_run, dict) and existing_ai_run.get("status") in {"completed", "unavailable", "failed"}:
            return learning_task

        research_attempts = int(learning_task.get("research_attempts", 0) or 0)
        if research_attempts < 2:
            return learning_task

        last_ai_assist_at = parse_iso_datetime(str(learning_task.get("last_ai_assist_at") or ""))
        if last_ai_assist_at and (datetime.now() - last_ai_assist_at).total_seconds() < 1800:
            return learning_task

        codex_info = detect_local_codex()
        if not codex_info.get("available"):
            current = copy.deepcopy(learning_task)
            current["source_runs"] = merge_learning_source_runs(
                source_runs,
                {
                    "source": "ai_assist",
                    "status": "unavailable",
                    "candidate_count": 0,
                    "detail": codex_info.get("reason"),
                },
            )
            current["last_ai_assist_at"] = datetime.now().isoformat()
            current["updated_at"] = datetime.now().isoformat()
            return current

        diagnosis = {
            "bundle_path": learning_task.get("bundle_path"),
            "source_dir": learning_task.get("source_dir"),
            "sample_signature": learning_task.get("sample_signature") or draft_learning_signature(learning_task),
            "research_state": "researching",
            "stable": False,
            "analyze": {},
            "reconstruct": {
                "issue_category": learning_task.get("issue_category") or learning_task.get("gap_type") or "strategy_gap",
                "recommended_actions": learning_task.get("next_actions", []),
                "issue_hints": learning_task.get("learning_objectives", []),
            },
        }
        queries = learning_task.get("queries", []) if isinstance(learning_task.get("queries"), list) else []
        ai_result = run_local_codex_learning(
            workspace=workspace,
            tenant_id=tenant_id,
            diagnosis=diagnosis,
            queries=queries,
        )

        current = copy.deepcopy(learning_task)
        current["source_runs"] = merge_learning_source_runs(
            source_runs,
            {
                "source": "ai_assist",
                "status": ai_result.get("status", "unknown"),
                "candidate_count": 1 if isinstance(ai_result.get("candidate"), dict) else 0,
                "detail": ai_result.get("detail"),
            },
        )

        candidate = ai_result.get("candidate")
        if isinstance(candidate, dict):
            existing_candidates = current.get("candidate_approaches", []) if isinstance(current.get("candidate_approaches"), list) else []
            existing_candidates.append(candidate)
            deduped: list[dict] = []
            seen_keys: set[str] = set()
            for item in sorted(existing_candidates, key=lambda entry: entry.get("confidence", 0.0), reverse=True):
                if not isinstance(item, dict):
                    continue
                key = f"{item.get('source')}::{item.get('title')}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                deduped.append(item)
            current["candidate_approaches"] = deduped[:6]
            current["status"] = "ready_for_validation" if policy.get("validation_required", True) else "candidate_found"
            current["next_validation_action"] = (
                "已得到 AI 辅助候选方案，下一步对真实样本或任务进行验证"
                if policy.get("validation_required", True)
                else "已得到 AI 辅助候选方案，可先进入观察态"
            )
            append_learning_task_status(current, current["status"])

        current["last_ai_assist_at"] = datetime.now().isoformat()
        current["updated_at"] = datetime.now().isoformat()
        return current

    def maybe_auto_validate_mission_plan_learning_task(
        workspace: Path,
        tenant_id: str,
        task_queue,
        learning_task: dict,
    ) -> dict:
        if not isinstance(learning_task, dict):
            return learning_task
        if str(learning_task.get("source") or "") != "mission_plan":
            return learning_task

        status = str(learning_task.get("status") or "")
        if status not in {"ready_for_validation", "candidate_found"}:
            return learning_task

        auto_validation = learning_task.get("auto_validation", {}) if isinstance(learning_task.get("auto_validation"), dict) else {}
        if auto_validation.get("status") in {"started", "running", "completed"}:
            return learning_task

        capability_type = str(learning_task.get("capability_type") or "")
        has_sample = bool(str(learning_task.get("bundle_path") or "").strip() or str(learning_task.get("source_dir") or "").strip())
        channel = str(learning_task.get("channel") or "").strip().lower()

        if capability_type == "javascript_reverse" and has_sample:
            try:
                trigger_learning_task_validation(
                    workspace=workspace,
                    tenant_id=tenant_id,
                    task_id=str(learning_task.get("task_id") or ""),
                    task_queue=task_queue,
                )
            except ValueError:
                return learning_task
            refreshed_state = load_learning_tasks(workspace)
            refreshed_tasks = refreshed_state.get("tasks", {}) if isinstance(refreshed_state, dict) else {}
            refreshed_payload = refreshed_tasks.get(str(learning_task.get("task_id") or ""))
            if isinstance(refreshed_payload, dict):
                return refreshed_payload
            return learning_task

        if capability_type == "automation" and channel == "toutiao":
            task_id = str(learning_task.get("task_id") or "")
            if not task_id:
                return learning_task
            created = task_queue.submit(
                task_type="operation_validate",
                payload={
                    "channel": channel,
                    "account_id": learning_task.get("account_id") or "default",
                    "work_type_id": learning_task.get("work_type_id"),
                    "deliverable_goal": learning_task.get("goal"),
                    "_learning_task_id": task_id,
                },
                priority=task_priority_cls.HIGH,
                tenant_id=tenant_id,
            )
            current = copy.deepcopy(learning_task)
            current["auto_validation"] = {
                "status": "started",
                "source": "connector_probe",
                "triggered_at": datetime.now().isoformat(),
                "created_task_ids": [created.id],
            }
            current["status"] = "validating"
            current["updated_at"] = datetime.now().isoformat()
            current["next_validation_action"] = "已发起 toutiao 连接器探测，等待确认执行器和登录态"
            append_learning_task_status(current, current["status"])
            return current

        current = copy.deepcopy(learning_task)
        current["status"] = "awaiting_connector"
        current["next_validation_action"] = "当前已有候选方案，但该工种还没有可自动执行的验证连接器，需要先接入执行器后再做真实验证"
        current["auto_validation"] = {
            "status": "connector_required",
            "source": "mission_plan",
            "noted_at": datetime.now().isoformat(),
        }
        current["updated_at"] = datetime.now().isoformat()
        append_learning_task_status(current, current["status"])
        return current

    def maybe_auto_validate_learning_task(
        workspace: Path,
        tenant_id: str,
        task_queue,
        learning_task: dict,
    ) -> dict:
        if not isinstance(learning_task, dict):
            return learning_task
        if learning_task.get("status") not in {"ready_for_validation", "candidate_found"}:
            return learning_task

        auto_validation = learning_task.get("auto_validation", {}) if isinstance(learning_task.get("auto_validation"), dict) else {}
        if auto_validation.get("status") in {"started", "running"}:
            return learning_task

        candidates = learning_task.get("candidate_approaches", []) if isinstance(learning_task.get("candidate_approaches"), list) else []
        learning_source = str(learning_task.get("source") or "")
        min_signature_score = 0.42
        min_confidence = 0.72
        if learning_source == "mission_failure":
            min_signature_score = 0.1
            min_confidence = 0.7
        historical = next(
            (
                item for item in candidates
                if isinstance(item, dict)
                and item.get("source") == "historical_archive"
                and isinstance(item.get("metadata"), dict)
                and item.get("metadata", {}).get("review_id")
                and float(item.get("metadata", {}).get("signature_score", 0.0) or 0.0) >= min_signature_score
                and float(item.get("confidence", 0.0) or 0.0) >= min_confidence
            ),
            None,
        )
        if not isinstance(historical, dict):
            return learning_task

        metadata = historical.get("metadata", {}) if isinstance(historical.get("metadata"), dict) else {}
        review_id = str(metadata.get("review_id") or "")
        if not review_id:
            return learning_task

        try:
            result = trigger_historical_review_validation(workspace, tenant_id, review_id, task_queue)
        except ValueError as exc:
            learning_task["auto_validation"] = {
                "status": "failed",
                "reason": str(exc),
                "source": "historical_archive",
                "review_id": review_id,
                "attempted_at": datetime.now().isoformat(),
            }
            return learning_task

        learning_task["auto_validation"] = {
            "status": "started",
            "source": "historical_archive",
            "review_id": review_id,
            "triggered_at": datetime.now().isoformat(),
            "created_task_ids": result.get("created_task_ids", []),
        }
        learning_task["status"] = "validating"
        learning_task["next_validation_action"] = "已自动命中历史成功档案并发起验证实验，等待重放结果"
        return learning_task

    def build_observation_learning_task(
        tenant_id: str,
        sample: dict,
        diagnosis: dict,
    ) -> dict:
        reconstruct = diagnosis.get("reconstruct", {}) if isinstance(diagnosis.get("reconstruct"), dict) else {}
        analyze = diagnosis.get("analyze", {}) if isinstance(diagnosis.get("analyze"), dict) else {}
        issue_category = reconstruct.get("issue_category") or analyze.get("issue_category") or diagnosis.get("research_state")
        is_stable_baseline = issue_category == "stable_verified" and diagnosis.get("research_state") == "stable"
        recommended_actions = reconstruct.get("recommended_actions") or analyze.get("recommended_actions") or []
        hints = reconstruct.get("issue_hints") or analyze.get("issue_hints") or []
        status = "baseline_tracking" if is_stable_baseline else "observing"
        title = "稳定基线观察" if is_stable_baseline else "后台观察任务"
        summary = (
            "当前样本已形成稳定基线，系统将周期性重放验证是否仍然稳定"
            if is_stable_baseline
            else "当前样本仍需持续观察，系统将自动重放并比较恢复质量变化"
        )
        next_action = (
            "系统会按观察节奏自动重放当前样本，持续比较评估分和关键指标"
            if not recommended_actions
            else recommended_actions[0]
        )
        return {
            "task_id": make_learning_task_id(tenant_id, sample),
            "tenant_id": tenant_id,
            "source_dir": sample.get("source_dir"),
            "bundle_path": sample.get("bundle_path"),
            "sample_signature": sample.get("sample_signature"),
            "issue_category": issue_category,
            "queries": [
                *(hints[:2] if isinstance(hints, list) else []),
                *(recommended_actions[:2] if isinstance(recommended_actions, list) else []),
            ],
            "preferred_sources": ["local_memory", "platform_shared", "historical_archive"],
            "validation_gate": "观察任务会自动重放当前样本，只有连续稳定或明显改进后才进入经验/策略晋升。",
            "status": status,
            "source_runs": [
                {"source": "local_memory", "status": "tracking", "candidate_count": 1},
                {"source": "platform_shared", "status": "standby", "candidate_count": 0},
                {"source": "historical_archive", "status": "standby", "candidate_count": 0},
            ],
            "candidate_approaches": [
                {
                    "source": "local_memory",
                    "title": title,
                    "summary": summary,
                    "confidence": 0.82 if is_stable_baseline else 0.74,
                    "evidence": [
                        f"research_state={diagnosis.get('research_state') or '--'}",
                        f"issue_category={issue_category or '--'}",
                        f"task_id={reconstruct.get('task_id') or analyze.get('task_id') or '--'}",
                    ],
                    "next_steps": recommended_actions[:3] if isinstance(recommended_actions, list) and recommended_actions else [
                        next_action,
                        "记录下一次重放与当前基线的差异",
                    ],
                    "metadata": {
                        "mode": "baseline_tracking" if is_stable_baseline else "observation_loop",
                    },
                }
            ],
            "next_validation_action": next_action,
            "updated_at": datetime.now().isoformat(),
        }

    def merge_observation_learning_task(existing: dict, current: dict) -> dict:
        if not isinstance(existing, dict):
            return current

        current["created_at"] = existing.get("created_at") or current.get("created_at") or datetime.now().isoformat()
        current["resolved_at"] = None
        current["status_history"] = existing.get("status_history", []) if isinstance(existing.get("status_history"), list) else []

        auto_validation = existing.get("auto_validation", {}) if isinstance(existing.get("auto_validation"), dict) else {}
        if auto_validation:
            current["auto_validation"] = copy.deepcopy(auto_validation)
        if auto_validation.get("status") in {"started", "running"}:
            current["status"] = "validating"
            current["next_validation_action"] = (
                existing.get("next_validation_action")
                or current.get("next_validation_action")
                or "等待当前观察重放完成后再比较结果"
            )

        comparison_history = existing.get("comparison_history", []) if isinstance(existing.get("comparison_history"), list) else []
        if comparison_history:
            current["comparison_history"] = comparison_history[:]
        if existing.get("last_comparison"):
            current["last_comparison"] = copy.deepcopy(existing.get("last_comparison"))

        current["stable_cycle_count"] = int(existing.get("stable_cycle_count", 0) or 0)
        if existing.get("stable_promoted_at"):
            current["stable_promoted_at"] = existing.get("stable_promoted_at")

        latest_existing = existing.get("candidate_approaches", [])
        if (
            isinstance(latest_existing, list)
            and latest_existing
            and isinstance(latest_existing[0], dict)
            and isinstance(current.get("candidate_approaches"), list)
            and current["candidate_approaches"]
            and isinstance(current["candidate_approaches"][0], dict)
        ):
            existing_candidate = latest_existing[0]
            current_candidate = current["candidate_approaches"][0]
            metadata = current_candidate.get("metadata", {}) if isinstance(current_candidate.get("metadata"), dict) else {}
            existing_metadata = existing_candidate.get("metadata", {}) if isinstance(existing_candidate.get("metadata"), dict) else {}
            current_candidate["metadata"] = {
                **existing_metadata,
                **metadata,
            }
            if existing_candidate.get("confidence") and not current_candidate.get("confidence"):
                current_candidate["confidence"] = existing_candidate.get("confidence")

        if not current["status_history"] or current["status_history"][-1].get("status") != current.get("status"):
            current["status_history"].append({
                "status": current.get("status"),
                "at": current.get("updated_at"),
            })
        return current

    def maybe_auto_progress_observation_task(
        workspace: Path,
        tenant_id: str,
        task_queue,
        learning_task: dict,
    ) -> dict:
        if not isinstance(learning_task, dict):
            return learning_task
        if learning_task.get("status") not in {"observing", "baseline_tracking"}:
            return learning_task

        auto_validation = learning_task.get("auto_validation", {}) if isinstance(learning_task.get("auto_validation"), dict) else {}
        if auto_validation.get("status") in {"started", "running"}:
            return learning_task

        status = learning_task.get("status")
        cooldown_seconds = 6 * 3600 if status == "baseline_tracking" else 15 * 60
        last_trigger = parse_iso_datetime(auto_validation.get("triggered_at") or auto_validation.get("attempted_at"))
        if last_trigger and (datetime.now() - last_trigger).total_seconds() < cooldown_seconds:
            return learning_task

        sample = {
            "bundle_path": learning_task.get("bundle_path"),
            "source_dir": learning_task.get("source_dir"),
            "sample_signature": learning_task.get("sample_signature"),
            "latest_mtime": 0.0,
        }
        reconstruct_task = latest_sample_task(task_queue, tenant_id, sample, "reconstruct")
        analyze_task = latest_sample_task(task_queue, tenant_id, sample, "analyze")
        source_task = reconstruct_task or analyze_task
        if not source_task:
            learning_task["auto_validation"] = {
                "status": "waiting_source_task",
                "attempted_at": datetime.now().isoformat(),
                "reason": "missing_source_task",
            }
            return learning_task

        pending_same_source = [
            task for task in task_queue.list_tasks(tenant_id=tenant_id, limit=200)
            if task.type == source_task.type
            and task.status.value in {"pending", "running"}
            and isinstance(task.payload, dict)
            and (
                task.payload.get("_replay_of") == source_task.id
                or task.payload.get("_learning_task_id") == learning_task.get("task_id")
            )
        ]
        if pending_same_source:
            learning_task["auto_validation"] = {
                "status": "running",
                "source": "observation_loop",
                "triggered_at": datetime.now().isoformat(),
                "created_task_ids": [task.id for task in pending_same_source[:3]],
            }
            return learning_task

        replay_payload = copy.deepcopy(source_task.payload or {})
        replay_payload["_replay_of"] = source_task.id
        replay_payload["_learning_task_id"] = learning_task.get("task_id")
        replay_payload["_autonomy_source"] = "observation_loop"
        replay_payload["_observation_mode"] = status
        created = task_queue.submit(
            task_type=source_task.type,
            payload=replay_payload,
            priority=task_priority_cls.HIGH if status == "observing" else task_priority_cls.NORMAL,
            tenant_id=tenant_id,
        )
        learning_task["auto_validation"] = {
            "status": "started",
            "source": "observation_loop",
            "triggered_at": datetime.now().isoformat(),
            "created_task_ids": [created.id],
        }
        learning_task["status"] = "validating"
        learning_task["next_validation_action"] = "已自动发起观察重放，等待比较本轮结果与当前基线"
        return learning_task

    def finalize_observation_learning_task(
        workspace: Path,
        tenant_id: str,
        task_queue,
        learning_task: dict,
    ) -> dict:
        if not isinstance(learning_task, dict):
            return learning_task

        auto_validation = learning_task.get("auto_validation", {}) if isinstance(learning_task.get("auto_validation"), dict) else {}
        if auto_validation.get("status") not in {"started", "running"}:
            return learning_task
        if str(auto_validation.get("source") or "") != "observation_loop":
            return learning_task
        created_task_ids = auto_validation.get("created_task_ids", []) if isinstance(auto_validation.get("created_task_ids"), list) else []
        if not created_task_ids:
            return learning_task

        finalized_ids = auto_validation.get("finalized_task_ids", []) if isinstance(auto_validation.get("finalized_task_ids"), list) else []
        if finalized_ids == created_task_ids:
            return learning_task

        replay_tasks = []
        for task_id in created_task_ids:
            task = task_queue.get_task(task_id)
            if not task:
                return learning_task
            if task.status.value in {"pending", "running"}:
                auto_validation["status"] = "running"
                learning_task["auto_validation"] = auto_validation
                return learning_task
            replay_tasks.append(task)

        comparisons: list[dict] = []
        outcomes: list[str] = []
        validations: list[str] = []
        for replay_task in replay_tasks:
            replay_of = (replay_task.payload or {}).get("_replay_of")
            if not replay_of:
                continue
            original_task = task_queue.get_task(replay_of)
            if not original_task:
                continue
            comparison = build_task_comparison(original_task, replay_task)
            comparisons.append(comparison)
            outcomes.append(str(comparison.get("diff", {}).get("outcome") or "unchanged"))
            validation = record_replay_validation(workspace, tenant_id, comparison)
            if isinstance(validation, dict) and validation.get("id"):
                validations.append(str(validation["id"]))

        if not comparisons:
            auto_validation["status"] = "failed"
            auto_validation["reason"] = "missing_comparison"
            auto_validation["finalized_at"] = datetime.now().isoformat()
            learning_task["auto_validation"] = auto_validation
            return learning_task

        best = comparisons[0]
        if any(item == "regressed" for item in outcomes):
            observation_result = "regressed"
        elif any(item == "improved" for item in outcomes):
            observation_result = "improved"
        else:
            observation_result = "unchanged"

        history = learning_task.get("comparison_history", []) if isinstance(learning_task.get("comparison_history"), list) else []
        history.append({
            "at": datetime.now().isoformat(),
            "result": observation_result,
            "comparisons": comparisons,
            "validation_ids": validations,
        })
        learning_task["comparison_history"] = history[-8:]

        base_status = "baseline_tracking" if learning_task.get("issue_category") == "stable_verified" else "observing"
        learning_task["status"] = base_status
        learning_task["updated_at"] = datetime.now().isoformat()
        learning_task["last_comparison"] = {
            "result": observation_result,
            "score_delta": best.get("diff", {}).get("score_delta"),
            "outcome": best.get("diff", {}).get("outcome"),
            "replay_task_id": best.get("replay", {}).get("task_id"),
            "original_task_id": best.get("original", {}).get("task_id"),
        }

        stable_cycles = int(learning_task.get("stable_cycle_count", 0) or 0)
        strategy_id = best.get("replay", {}).get("strategy_id") or best.get("original", {}).get("strategy_id")
        if observation_result == "improved":
            learning_task["next_validation_action"] = "观察到正向增益，继续积累样本后可考虑晋升为成长事件"
            learning_task["stable_cycle_count"] = 0
            if strategy_id:
                record_growth_event(
                    workspace,
                    tenant_id,
                    strategy_id=strategy_id,
                    event_type="observation_improved",
                    summary=f"{strategy_id} improved during autonomous observation",
                    quality_score=max(0.3, safe_float(best.get("diff", {}).get("score_delta"), 0.3)),
                    task_type=best.get("replay", {}).get("task_type"),
                    domain="javascript",
                    signature=build_snapshot_signature(best.get("replay", {})),
                    metadata={
                        "source": "observation_loop",
                        "replay_task_id": best.get("replay", {}).get("task_id"),
                        "original_task_id": best.get("original", {}).get("task_id"),
                    },
                )
        elif observation_result == "regressed":
            learning_task["next_validation_action"] = "观察到退化，后续应优先复核最近策略、权重或输入变化"
            learning_task["stable_cycle_count"] = 0
            learning_task["status"] = "observing"
            if strategy_id:
                record_growth_event(
                    workspace,
                    tenant_id,
                    strategy_id=strategy_id,
                    event_type="observation_regressed",
                    summary=f"{strategy_id} regressed during autonomous observation",
                    quality_score=0.15,
                    task_type=best.get("replay", {}).get("task_type"),
                    domain="javascript",
                    signature=build_snapshot_signature(best.get("replay", {})),
                    metadata={
                        "source": "observation_loop",
                        "replay_task_id": best.get("replay", {}).get("task_id"),
                        "original_task_id": best.get("original", {}).get("task_id"),
                    },
                )
        else:
            stable_cycles += 1
            learning_task["stable_cycle_count"] = stable_cycles
            learning_task["next_validation_action"] = f"已连续 {stable_cycles} 轮保持稳定，继续后台观察确认长期可靠性"
            if stable_cycles >= 2 and not learning_task.get("stable_promoted_at") and strategy_id:
                learning_task["stable_promoted_at"] = datetime.now().isoformat()
                record_growth_event(
                    workspace,
                    tenant_id,
                    strategy_id=strategy_id,
                    event_type="observation_stable",
                    summary=f"{strategy_id} remained stable across repeated autonomous observation",
                    quality_score=0.78,
                    task_type=best.get("replay", {}).get("task_type"),
                    domain="javascript",
                    signature=build_snapshot_signature(best.get("replay", {})),
                    metadata={
                        "source": "observation_loop",
                        "stable_cycle_count": stable_cycles,
                        "replay_task_id": best.get("replay", {}).get("task_id"),
                        "original_task_id": best.get("original", {}).get("task_id"),
                    },
                )

        auto_validation["status"] = "completed"
        auto_validation["finalized_at"] = datetime.now().isoformat()
        auto_validation["finalized_task_ids"] = created_task_ids[:]
        if validations:
            auto_validation["validation_ids"] = validations
        learning_task["auto_validation"] = auto_validation
        return learning_task

    def finalize_general_learning_task_validation(
        workspace: Path,
        tenant_id: str,
        task_queue,
        learning_task: dict,
    ) -> dict:
        if not isinstance(learning_task, dict):
            return learning_task

        auto_validation = learning_task.get("auto_validation", {}) if isinstance(learning_task.get("auto_validation"), dict) else {}
        if auto_validation.get("status") not in {"started", "running"}:
            return learning_task

        validation_source = str(auto_validation.get("source") or "")
        if validation_source == "observation_loop":
            return learning_task

        if validation_source == "connector_probe":
            created_task_ids = auto_validation.get("created_task_ids", []) if isinstance(auto_validation.get("created_task_ids"), list) else []
            if not created_task_ids:
                return learning_task
            probe_task = task_queue.get_task(str(created_task_ids[0]))
            if not probe_task:
                return learning_task
            if probe_task.status.value in {"pending", "running"}:
                auto_validation["status"] = "running"
                learning_task["auto_validation"] = auto_validation
                return learning_task

            probe_result = probe_task.result if isinstance(probe_task.result, dict) else {}
            outcome = str(probe_result.get("validation_outcome") or "")
            learning_task["validation_result"] = {
                "mode": "connector_probe",
                "task_id": probe_task.id,
                "result": probe_result,
            }
            learning_task["updated_at"] = datetime.now().isoformat()
            auto_validation["status"] = "completed"
            auto_validation["finalized_at"] = learning_task["updated_at"]
            auto_validation["finalized_task_ids"] = created_task_ids[:]

            if outcome == "passed":
                learning_task["status"] = "resolved"
                learning_task["next_validation_action"] = "连接器与登录态已就绪，可以推进真实运营执行任务"
            elif outcome == "auth_required":
                learning_task["status"] = "needs_input"
                learning_task["next_validation_action"] = "需要先完成头条账号登录，再进入真实执行"
            elif outcome in {"connector_missing", "dependency_missing"}:
                learning_task["status"] = "awaiting_connector"
                learning_task["next_validation_action"] = probe_result.get("message") or "仍需补齐连接器环境"
            else:
                learning_task["status"] = "needs_learning"
                learning_task["next_validation_action"] = probe_result.get("message") or "连接器探测失败，需要继续排查"

            learning_task["auto_validation"] = auto_validation
            append_learning_task_status(learning_task, learning_task["status"])
            return learning_task

        created_task_ids = auto_validation.get("created_task_ids", []) if isinstance(auto_validation.get("created_task_ids"), list) else []
        if not created_task_ids:
            return learning_task

        if validation_source == "historical_archive":
            review_id = str(auto_validation.get("review_id") or "")
            if not review_id:
                return learning_task
            review_items = refresh_review_queue_experiment_runs(workspace, tenant_id, task_queue)
            review_entry = next(
                (item for item in review_items if isinstance(item, dict) and str(item.get("id") or "") == review_id),
                None,
            )
            if not isinstance(review_entry, dict):
                auto_validation["status"] = "failed"
                auto_validation["reason"] = "missing_review_entry"
                auto_validation["finalized_at"] = datetime.now().isoformat()
                learning_task["auto_validation"] = auto_validation
                learning_task["status"] = "needs_learning"
                learning_task["updated_at"] = datetime.now().isoformat()
                append_learning_task_status(learning_task, learning_task["status"])
                return learning_task

            review_status = str(review_entry.get("status") or "")
            latest_run = (review_entry.get("experiment_runs") or [{}])[0] if isinstance(review_entry.get("experiment_runs"), list) and review_entry.get("experiment_runs") else {}
            latest_summary = latest_run.get("summary", {}) if isinstance(latest_run, dict) else {}
            if review_status == "running_experiment" or latest_summary.get("status") == "running":
                auto_validation["status"] = "running"
                learning_task["auto_validation"] = auto_validation
                return learning_task

            result_map = {
                "experiment_improved": "validated_improved",
                "experiment_regressed": "validated_regressed",
                "experiment_mixed": "validated_mixed",
            }
            learning_task["status"] = result_map.get(review_status, "validated_unchanged")
            learning_task["updated_at"] = datetime.now().isoformat()
            learning_task["validation_result"] = {
                "mode": "historical_review_experiment",
                "review_id": review_id,
                "review_status": review_status,
                "summary": latest_summary if isinstance(latest_summary, dict) else {},
            }
            learning_task["next_validation_action"] = (
                "历史档案实验已验证存在提升，可以把方案沉淀到当前能力成长链路"
                if learning_task["status"] == "validated_improved"
                else "历史档案实验没有稳定带来增益，需要继续研究或补充新方案"
            )
            auto_validation["status"] = "completed"
            auto_validation["finalized_at"] = learning_task["updated_at"]
            auto_validation["finalized_task_ids"] = created_task_ids[:]
            learning_task["auto_validation"] = auto_validation
            append_learning_task_status(learning_task, learning_task["status"])
            return learning_task

        finalized_ids = auto_validation.get("finalized_task_ids", []) if isinstance(auto_validation.get("finalized_task_ids"), list) else []
        if finalized_ids == created_task_ids:
            return learning_task

        replay_tasks = []
        for task_id in created_task_ids:
            task = task_queue.get_task(task_id)
            if not task:
                return learning_task
            if task.status.value in {"pending", "running"}:
                auto_validation["status"] = "running"
                learning_task["auto_validation"] = auto_validation
                return learning_task
            replay_tasks.append(task)

        comparisons: list[dict] = []
        validations: list[str] = []
        outcomes: list[str] = []
        for replay_task in replay_tasks:
            replay_of = (replay_task.payload or {}).get("_replay_of")
            if not replay_of:
                continue
            original_task = task_queue.get_task(replay_of)
            if not original_task:
                continue
            comparison = build_task_comparison(original_task, replay_task)
            comparisons.append(comparison)
            outcomes.append(str(comparison.get("diff", {}).get("outcome") or "unchanged"))
            validation = record_replay_validation(workspace, tenant_id, comparison)
            if isinstance(validation, dict) and validation.get("id"):
                validations.append(str(validation["id"]))

        if not comparisons:
            auto_validation["status"] = "failed"
            auto_validation["reason"] = "missing_comparison"
            auto_validation["finalized_at"] = datetime.now().isoformat()
            learning_task["auto_validation"] = auto_validation
            learning_task["status"] = "needs_learning"
            learning_task["updated_at"] = datetime.now().isoformat()
            append_learning_task_status(learning_task, learning_task["status"])
            return learning_task

        if any(item == "regressed" for item in outcomes):
            result_status = "validated_regressed"
        elif any(item == "improved" for item in outcomes):
            result_status = "validated_improved"
        else:
            result_status = "validated_unchanged"

        learning_task["status"] = result_status
        learning_task["updated_at"] = datetime.now().isoformat()
        learning_task["validation_result"] = {
            "mode": "live_task_replay",
            "result": result_status,
            "comparisons": comparisons,
            "validation_ids": validations,
        }
        learning_task["last_comparison"] = {
            "result": result_status,
            "comparisons": comparisons,
        }
        history = learning_task.get("comparison_history", []) if isinstance(learning_task.get("comparison_history"), list) else []
        history.append({
            "at": learning_task["updated_at"],
            "result": result_status,
            "comparisons": comparisons,
            "validation_ids": validations,
        })
        learning_task["comparison_history"] = history[-8:]
        learning_task["next_validation_action"] = (
            "本轮重放验证出现正向提升，可以继续沉淀为经验或策略候选"
            if result_status == "validated_improved"
            else "本轮重放验证未形成稳定提升，需要继续学习、调整策略或补充样本"
        )
        auto_validation["status"] = "completed"
        auto_validation["finalized_at"] = learning_task["updated_at"]
        auto_validation["finalized_task_ids"] = created_task_ids[:]
        if validations:
            auto_validation["validation_ids"] = validations
        learning_task["auto_validation"] = auto_validation
        append_learning_task_status(learning_task, learning_task["status"])
        return learning_task

    def normalize_mission_failure_learning_task(learning_task: dict) -> dict:
        if not isinstance(learning_task, dict):
            return learning_task
        if str(learning_task.get("source") or "") != "mission_failure":
            return learning_task

        auto_validation = learning_task.get("auto_validation", {}) if isinstance(learning_task.get("auto_validation"), dict) else {}
        if str(auto_validation.get("source") or "") != "historical_archive":
            return learning_task
        if auto_validation.get("status") != "completed":
            return learning_task

        current_status = str(learning_task.get("status") or "")
        if current_status in {"validated_improved", "validated_unchanged", "validated_regressed", "validated_mixed"}:
            return learning_task

        validation_ids = auto_validation.get("validation_ids", []) if isinstance(auto_validation.get("validation_ids"), list) else []
        learning_task["status"] = "validated_improved" if validation_ids else "validated_unchanged"
        learning_task["updated_at"] = datetime.now().isoformat()
        learning_task["validation_result"] = {
            "mode": "historical_review_experiment",
            "result": learning_task["status"],
            "review_id": auto_validation.get("review_id"),
            "validation_ids": validation_ids,
        }
        learning_task["next_validation_action"] = (
            "历史验证已产生正向增益，可以继续晋升为经验或策略候选"
            if validation_ids
            else "历史验证已完成，但还没有明确增益，建议继续补样本和策略实验"
        )
        append_learning_task_status(learning_task, learning_task["status"])
        return learning_task

    def refresh_runtime_learning_tasks(
        workspace: Path,
        tenant_manager,
        task_queue,
        tenant_id: str | None = None,
    ) -> dict:
        learning_state = load_learning_tasks(workspace)
        tasks = learning_state.get("tasks", {}) if isinstance(learning_state, dict) else {}
        if not isinstance(tasks, dict):
            tasks = {}

        changed = False
        for current_task_id, payload in list(tasks.items()):
            if not isinstance(payload, dict):
                continue
            scoped_tenant_id = str(payload.get("tenant_id") or tenant_id or "default")
            if tenant_id and scoped_tenant_id != tenant_id:
                continue

            current = copy.deepcopy(payload)
            previous = copy.deepcopy(payload)
            current = normalize_mission_failure_learning_task(current)
            current = maybe_expand_mission_plan_learning_task(
                workspace=workspace,
                tenant_manager=tenant_manager,
                tenant_id=scoped_tenant_id,
                learning_task=current,
            )
            current = maybe_ai_assist_mission_plan_learning_task(
                workspace=workspace,
                tenant_manager=tenant_manager,
                tenant_id=scoped_tenant_id,
                learning_task=current,
            )
            current = maybe_auto_validate_mission_plan_learning_task(
                workspace=workspace,
                tenant_id=scoped_tenant_id,
                task_queue=task_queue,
                learning_task=current,
            )

            if str(current.get("status") or "") in {"ready_for_validation", "candidate_found"}:
                current = maybe_auto_validate_learning_task(
                    workspace=workspace,
                    tenant_id=scoped_tenant_id,
                    task_queue=task_queue,
                    learning_task=current,
                )
            if str(current.get("status") or "") == "validating":
                current = finalize_observation_learning_task(
                    workspace=workspace,
                    tenant_id=scoped_tenant_id,
                    task_queue=task_queue,
                    learning_task=current,
                )
                current = finalize_general_learning_task_validation(
                    workspace=workspace,
                    tenant_id=scoped_tenant_id,
                    task_queue=task_queue,
                    learning_task=current,
                )
            if str(current.get("status") or "") in {"observing", "baseline_tracking"}:
                current = maybe_auto_progress_observation_task(
                    workspace=workspace,
                    tenant_id=scoped_tenant_id,
                    task_queue=task_queue,
                    learning_task=current,
                )

            if current != previous:
                current["updated_at"] = current.get("updated_at") or datetime.now().isoformat()
                tasks[current_task_id] = current
                changed = True

        if changed:
            save_learning_tasks(workspace, {"tasks": tasks})
            return load_learning_tasks(workspace)
        return {
            "updated_at": learning_state.get("updated_at"),
            "tasks": tasks,
        }

    def refresh_learning_task(
        workspace: Path,
        tenant_manager,
        learning_state: dict,
        tenant_id: str,
        sample: dict,
        diagnosis: dict,
        learning_plan: dict,
        task_queue,
    ) -> dict | None:
        tasks = learning_state.get("tasks", {}) if isinstance(learning_state, dict) else {}
        task_id = make_learning_task_id(tenant_id, sample)
        observation_categories = {"stable_verified", "partial_recovery", "observation_needed"}
        issue_category = diagnosis.get("reconstruct", {}).get("issue_category") or diagnosis.get("analyze", {}).get("issue_category")
        needs_observation = diagnosis.get("research_state") in {"stable", "observing"} and issue_category in observation_categories

        if not learning_plan.get("needs_external_learning"):
            if needs_observation:
                existing = tasks.get(task_id) if isinstance(tasks.get(task_id), dict) else {}
                current = build_observation_learning_task(
                    tenant_id=tenant_id,
                    sample=sample,
                    diagnosis=diagnosis,
                )
                current = merge_observation_learning_task(existing, current)
                current = finalize_observation_learning_task(
                    workspace=workspace,
                    tenant_id=tenant_id,
                    task_queue=task_queue,
                    learning_task=current,
                )
                current = maybe_auto_progress_observation_task(
                    workspace=workspace,
                    tenant_id=tenant_id,
                    task_queue=task_queue,
                    learning_task=current,
                )
                tasks[task_id] = current
                return current

            existing = tasks.get(task_id)
            if isinstance(existing, dict):
                existing["status"] = "resolved"
                existing["resolved_at"] = datetime.now().isoformat()
                existing["updated_at"] = datetime.now().isoformat()
                existing["diagnosis_state"] = diagnosis.get("research_state")
                tasks[task_id] = existing
            return existing if isinstance(existing, dict) else None

        existing = tasks.get(task_id) if isinstance(tasks.get(task_id), dict) else {}
        current = execute_learning_task(
            workspace=workspace,
            tenant_manager=tenant_manager,
            tenant_id=tenant_id,
            sample=sample,
            diagnosis=diagnosis,
            learning_plan=learning_plan,
        )
        current["created_at"] = existing.get("created_at") or datetime.now().isoformat()
        current["status_history"] = existing.get("status_history", []) if isinstance(existing.get("status_history"), list) else []
        if not current["status_history"] or current["status_history"][-1].get("status") != current.get("status"):
            current["status_history"].append({
                "status": current.get("status"),
                "at": current.get("updated_at"),
            })
        current = maybe_auto_validate_learning_task(
            workspace=workspace,
            tenant_id=tenant_id,
            task_queue=task_queue,
            learning_task=current,
        )
        tasks[task_id] = current
        return current

    def build_historical_learning_tasks(
        workspace: Path,
        tenant_id: str,
        task_queue,
    ) -> list[dict]:
        items = load_review_queue(workspace, tenant_id)
        historical: list[dict] = []
        codex_available = detect_local_codex().get("available")

        for item in items:
            if not isinstance(item, dict):
                continue
            review_id = str(item.get("id") or "")
            if not review_id:
                continue

            draft = item.get("draft", {}) if isinstance(item.get("draft"), dict) else {}
            experiment_plan = item.get("experiment_plan", {}) if isinstance(item.get("experiment_plan"), dict) else {}
            upgrade_candidate = item.get("upgrade_candidate", {}) if isinstance(item.get("upgrade_candidate"), dict) else {}
            platform_promotion = item.get("platform_promotion", {}) if isinstance(item.get("platform_promotion"), dict) else {}
            latest_run = item.get("experiment_runs", [{}])[0] if isinstance(item.get("experiment_runs"), list) and item.get("experiment_runs") else {}
            latest_summary = latest_run.get("summary", {}) if isinstance(latest_run, dict) else {}

            candidate_approaches: list[dict] = []
            if draft:
                candidate_approaches.append({
                    "source": "local_memory",
                    "title": "历史优化草案",
                    "summary": trim_candidate_text(draft.get("summary") or item.get("notes") or "历史复盘草案"),
                    "confidence": 0.64,
                    "evidence": [
                        f"review_id={review_id}",
                        f"strategy={item.get('strategy_id') or '--'}",
                    ],
                    "next_steps": [
                        "将草案中的 proposed_changes 转成新一轮实验输入",
                        "对照历史 review 样本确认问题是否被真正覆盖",
                    ],
                    "metadata": {
                        "draft_generated_at": item.get("draft_generated_at"),
                    },
                })
            if upgrade_candidate:
                candidate_approaches.append({
                    "source": "platform_shared" if platform_promotion else "local_memory",
                    "title": upgrade_candidate.get("title") or "历史升级候选",
                    "summary": trim_candidate_text(upgrade_candidate.get("summary") or "历史实验曾得到正向升级候选"),
                    "confidence": 0.78 if upgrade_candidate.get("decision") in {"accept", "auto_accept"} else 0.68,
                    "evidence": [
                        f"decision={upgrade_candidate.get('decision') or '--'}",
                        f"status={item.get('status') or '--'}",
                    ],
                    "next_steps": [
                        "复用这条升级候选作为相似问题的优先对照方案",
                        "在新样本上重放验证，确认不是偶发收益",
                    ],
                    "metadata": {
                        "decided_at": upgrade_candidate.get("decided_at"),
                        "platform_promotion": platform_promotion.get("status"),
                    },
                })

            source_runs = [
                {
                    "source": "local_memory",
                    "status": "completed" if draft else "no_match",
                    "candidate_count": 1 if draft else 0,
                },
                {
                    "source": "platform_shared",
                    "status": "completed" if platform_promotion else "no_match",
                    "candidate_count": 1 if platform_promotion else 0,
                },
                {
                    "source": "ai_assist",
                    "status": "available" if codex_available else "unavailable",
                    "candidate_count": 0,
                },
            ]

            historical.append({
                "task_id": f"historical:{tenant_id}:{review_id}",
                "tenant_id": tenant_id,
                "source_dir": None,
                "bundle_path": None,
                "sample_signature": None,
                "issue_category": item.get("alert_reason"),
                "queries": [
                    item.get("notes"),
                    experiment_plan.get("next_action"),
                ],
                "preferred_sources": ["local_memory", "platform_shared", "ai_assist"],
                "validation_gate": "历史案例已完成至少一轮复盘/实验，可作为相似问题的候选解法，但新样本仍需重放验证。",
                "status": (
                    "running_experiment"
                    if item.get("status") == "running_experiment"
                    else "promoted"
                    if platform_promotion
                    else "validated"
                    if latest_summary.get("status") == "improved"
                    else item.get("status") or "archived"
                ),
                "source_runs": source_runs,
                "candidate_approaches": candidate_approaches[:4],
                "next_validation_action": (
                    latest_summary.get("recommended_action")
                    or experiment_plan.get("next_action")
                    or "把这条历史案例映射成当前问题的验证任务"
                ),
                "updated_at": (
                    platform_promotion.get("promoted_at")
                    or upgrade_candidate.get("decided_at")
                    or item.get("last_run_at")
                    or item.get("created_at")
                ),
                "created_at": item.get("created_at"),
                "resolved_at": platform_promotion.get("promoted_at") or upgrade_candidate.get("decided_at"),
                "archived": True,
                "review_id": review_id,
                "strategy_id": item.get("strategy_id"),
                "experiment_summary": latest_summary if isinstance(latest_summary, dict) else {},
            })

        historical.sort(key=lambda entry: entry.get("updated_at") or "", reverse=True)
        return historical[:12]

    return {
        "append_learning_task_status": append_learning_task_status,
        "merge_learning_source_runs": merge_learning_source_runs,
        "maybe_expand_mission_plan_learning_task": maybe_expand_mission_plan_learning_task,
        "maybe_ai_assist_mission_plan_learning_task": maybe_ai_assist_mission_plan_learning_task,
        "maybe_auto_validate_mission_plan_learning_task": maybe_auto_validate_mission_plan_learning_task,
        "maybe_auto_validate_learning_task": maybe_auto_validate_learning_task,
        "finalize_general_learning_task_validation": finalize_general_learning_task_validation,
        "refresh_runtime_learning_tasks": refresh_runtime_learning_tasks,
        "build_observation_learning_task": build_observation_learning_task,
        "merge_observation_learning_task": merge_observation_learning_task,
        "maybe_auto_progress_observation_task": maybe_auto_progress_observation_task,
        "finalize_observation_learning_task": finalize_observation_learning_task,
        "normalize_mission_failure_learning_task": normalize_mission_failure_learning_task,
        "refresh_learning_task": refresh_learning_task,
        "build_historical_learning_tasks": build_historical_learning_tasks,
        "trigger_historical_review_validation": trigger_historical_review_validation,
        "trigger_learning_task_validation": trigger_learning_task_validation,
    }
