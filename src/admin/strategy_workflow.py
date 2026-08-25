"""
策略复盘工作流：草案、实验计划与重放执行。
"""

from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
from typing import Callable

from core.task_queue import TaskPriority


def generate_strategy_draft(entry: dict, *, safe_float: Callable[[object, float], float]) -> dict:
    strategy_id = entry.get("strategy_id", "unknown")
    alert_reason = entry.get("alert_reason") or "需要复盘"
    review_ratio = safe_float(entry.get("review_ratio"), 0.0)
    avg_eval = safe_float(entry.get("avg_eval"), 0.0)
    total_gain = safe_float(entry.get("total_gain"), 0.0)

    goals = [
        "降低 review 比例，提升稳定通过率",
        "提高输出质量的一致性，减少偶发退化",
    ]
    if total_gain <= 0:
        goals.append("让该策略在重放实验中产生可观测正向增益")

    hypotheses = []
    if review_ratio >= 0.5:
        hypotheses.append("当前策略覆盖面不足，导致大量样本只能勉强通过评估")
    if avg_eval < 0.7:
        hypotheses.append("当前策略输出质量偏低，需要补充关键步骤或约束")
    if total_gain <= 0:
        hypotheses.append("当前策略没有带来明确收益，可能需要重新分流或降权")
    if not hypotheses:
        hypotheses.append("当前策略需要进一步细化命中条件和执行步骤")

    changes = [
        "补充更明确的命中条件，缩小误命中范围",
        "为关键输出增加校验或兜底步骤",
        "把最近 review 样本整理成验证用例，比较优化前后差异",
    ]
    if "reconstruct" in strategy_id:
        changes.append("检查 analysis_result 到 reconstruct 的传递是否完整")
    if "analyze" in strategy_id:
        changes.append("增加对低置信度输入的分流逻辑，避免直接走默认链路")

    validation = [
        "至少重放 3 个历史失败或 review 样本",
        "观察评估均分是否提升，review 比例是否下降",
        "确认没有引入新的 failed 样本或明显退化",
    ]

    return {
        "summary": f"针对 {strategy_id} 的优化草案，原因：{alert_reason}",
        "goals": goals[:3],
        "hypotheses": hypotheses[:3],
        "proposed_changes": changes[:4],
        "validation_plan": validation,
    }


def generate_review_draft(
    workspace: Path,
    tenant_id: str,
    review_id: str,
    *,
    load_review_queue: Callable[[Path, str], list[dict]],
    save_review_queue: Callable[[Path, str, list[dict]], None],
    safe_float: Callable[[object, float], float],
) -> dict | None:
    items = load_review_queue(workspace, tenant_id)
    target = next((item for item in items if item.get("id") == review_id), None)
    if not target:
        return None

    draft = generate_strategy_draft(target, safe_float=safe_float)
    target["status"] = "drafting"
    target["draft"] = draft
    target["draft_generated_at"] = datetime.now().isoformat()
    save_review_queue(workspace, tenant_id, items)
    return target


def generate_experiment_plan(entry: dict, *, safe_float: Callable[[object, float], float]) -> dict:
    strategy_id = entry.get("strategy_id", "unknown")
    draft = entry.get("draft", {}) if isinstance(entry.get("draft"), dict) else {}
    review_ratio = safe_float(entry.get("review_ratio"), 0.0)
    avg_eval = safe_float(entry.get("avg_eval"), 0.0)

    sample_count = 3 if review_ratio < 0.7 else 5
    acceptance = [
        "重放后平均评估分高于当前基线",
        "review 比例低于当前基线",
        "不能引入新的 failed 样本",
    ]
    if avg_eval < 0.6:
        acceptance.append("至少 1 个历史 review 样本被提升到 pass")

    steps = [
        "基于草案修改策略命中条件或关键步骤",
        f"选择 {sample_count} 个最近的 failed/review 样本进行重放",
        "记录重放前后的 capability、strategy、evaluation 差异",
        "把有效样本继续沉淀到 replay_validation",
    ]

    return {
        "title": f"{strategy_id} 重放实验计划",
        "linked_draft_summary": draft.get("summary"),
        "sample_count": sample_count,
        "steps": steps,
        "acceptance_criteria": acceptance,
        "next_action": "完成策略调整后执行一轮重放并观察对比结果",
    }


def generate_review_experiment_plan(
    workspace: Path,
    tenant_id: str,
    review_id: str,
    *,
    load_review_queue: Callable[[Path, str], list[dict]],
    save_review_queue: Callable[[Path, str, list[dict]], None],
    safe_float: Callable[[object, float], float],
) -> dict | None:
    items = load_review_queue(workspace, tenant_id)
    target = next((item for item in items if item.get("id") == review_id), None)
    if not target:
        return None
    if not isinstance(target.get("draft"), dict):
        return None

    plan = generate_experiment_plan(target, safe_float=safe_float)
    target["status"] = "validating"
    target["experiment_plan"] = plan
    target["experiment_generated_at"] = datetime.now().isoformat()
    save_review_queue(workspace, tenant_id, items)
    return target


def task_strategy_id(task) -> str | None:
    result = task.result or {}
    if not isinstance(result, dict):
        return None
    feedback = result.get("feedback", {})
    if not isinstance(feedback, dict):
        return None
    decision = feedback.get("decision", {})
    if not isinstance(decision, dict):
        return None
    strategy = decision.get("strategy", {})
    if not isinstance(strategy, dict):
        return None
    return strategy.get("strategy_id")


def task_evaluation_verdict(task) -> str | None:
    result = task.result or {}
    if not isinstance(result, dict):
        return None
    feedback = result.get("feedback", {})
    if not isinstance(feedback, dict):
        return None
    evaluation = feedback.get("evaluation", {})
    if not isinstance(evaluation, dict):
        return None
    return evaluation.get("verdict")


def task_evaluation_score(task, *, safe_float: Callable[[object, float], float]) -> float | None:
    result = task.result or {}
    if not isinstance(result, dict):
        return None
    feedback = result.get("feedback", {})
    if not isinstance(feedback, dict):
        return None
    evaluation = feedback.get("evaluation", {})
    if not isinstance(evaluation, dict):
        return None
    score = evaluation.get("score")
    if score is None:
        return None
    return safe_float(score)


def select_experiment_source_tasks(
    task_queue,
    tenant_id: str,
    strategy_id: str,
    sample_count: int,
) -> list:
    candidates = []
    tasks = task_queue.list_tasks(tenant_id=tenant_id, limit=400)

    for task in tasks:
        payload = task.payload or {}
        if payload.get("_replay_of"):
            continue
        if task_strategy_id(task) != strategy_id:
            continue

        verdict = task_evaluation_verdict(task)
        if task.status.value == "failed":
            priority = 0
        elif verdict == "review":
            priority = 1
        elif task.status.value == "success":
            priority = 2
        else:
            priority = 3

        candidates.append((priority, task.created_at, task))

    candidates.sort(
        key=lambda item: (
            item[0],
            -datetime.fromisoformat(item[1]).timestamp() if item[1] else 0,
        )
    )
    return [task for _, _, task in candidates[:max(1, sample_count)]]


def run_review_experiment(
    workspace: Path,
    tenant_id: str,
    review_id: str,
    task_queue,
    *,
    load_review_queue: Callable[[Path, str], list[dict]],
    save_review_queue: Callable[[Path, str, list[dict]], None],
) -> dict | None:
    items = load_review_queue(workspace, tenant_id)
    target = next((item for item in items if item.get("id") == review_id), None)
    if not target or not isinstance(target.get("experiment_plan"), dict):
        return None

    strategy_id = target.get("strategy_id")
    if not strategy_id:
        return None

    plan = target.get("experiment_plan", {})
    sample_count = max(1, int(plan.get("sample_count", 3) or 3))
    source_tasks = select_experiment_source_tasks(task_queue, tenant_id, strategy_id, sample_count)
    if not source_tasks:
        raise ValueError("当前策略暂无可用于实验的历史样本")

    created_tasks = []
    for source_task in source_tasks:
        replay_payload = copy.deepcopy(source_task.payload or {})
        replay_payload["_replay_of"] = source_task.id
        replay_payload["_experiment_review_id"] = review_id
        replay_payload["_experiment_strategy_id"] = strategy_id

        replay_task = task_queue.submit(
            task_type=source_task.type,
            payload=replay_payload,
            priority=TaskPriority.HIGH,
            tenant_id=tenant_id,
        )
        created_tasks.append(replay_task)

    experiment_run = {
        "created_at": datetime.now().isoformat(),
        "plan_title": plan.get("title"),
        "sample_count_requested": sample_count,
        "sample_count_actual": len(created_tasks),
        "source_task_ids": [task.id for task in source_tasks],
        "task_ids": [task.id for task in created_tasks],
        "summary": {
            "status": "running",
            "completed": 0,
            "pending": len(created_tasks),
            "success": 0,
            "review": 0,
            "failed": 0,
            "avg_score": None,
            "baseline_avg_score": None,
            "score_delta": None,
            "improved_count": 0,
            "regressed_count": 0,
            "unchanged_count": 0,
            "recommended_action": "等待实验任务完成后再判断是否升级策略",
        },
    }

    target["status"] = "running_experiment"
    target["last_run_at"] = experiment_run["created_at"]
    target.setdefault("experiment_runs", [])
    if isinstance(target["experiment_runs"], list):
        target["experiment_runs"].insert(0, experiment_run)
        target["experiment_runs"] = target["experiment_runs"][:10]
    else:
        target["experiment_runs"] = [experiment_run]
    save_review_queue(workspace, tenant_id, items)
    return target
