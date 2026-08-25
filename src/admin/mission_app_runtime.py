"""
Mission 应用装配运行时：
负责下一轮计划与成长时间线等纯辅助逻辑。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable


def create_mission_app_runtime_bindings(
    *,
    extract_feedback_entries_from_result: Callable[[dict], list[dict]],
    trim_candidate_text: Callable[[str | None, int], str],
    normalize_string_list: Callable[[object], list[str]],
):
    def build_mission_next_cycle_plan(mission_run: dict, actions: list[dict]) -> dict:
        goal = str(mission_run.get("goal") or "").strip()
        completed_actions = [item for item in actions if isinstance(item, dict) and item.get("status") == "completed"]
        insight_actions = [
            item for item in completed_actions
            if str(item.get("insight_summary") or "").strip() or isinstance(item.get("next_actions"), list)
        ]
        role_reflection_contexts: list[dict] = []
        plan = mission_run.get("plan", {}) if isinstance(mission_run.get("plan"), dict) else {}
        nodes = plan.get("nodes") if isinstance(plan.get("nodes"), list) else []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            payload = node.get("role_reflection_context", {})
            if isinstance(payload, dict) and any(str(payload.get(key) or "").strip() for key in ["summary", "next_experiment", "blocked_reason"]):
                role_reflection_contexts.append(payload)
        focus_points: list[str] = []
        next_steps: list[str] = []
        feedback_categories: list[str] = []
        feedback_texts: list[str] = []
        publish_modes: list[str] = []
        for item in insight_actions:
            insight = str(item.get("insight_summary") or "").strip()
            if insight and insight not in focus_points:
                focus_points.append(insight)
            for step in (item.get("next_actions") or []):
                step_text = str(step).strip()
                if step_text and step_text not in next_steps:
                    next_steps.append(step_text)
            result = item.get("task_result", {}) if isinstance(item.get("task_result"), dict) else {}
            for feedback_summary in extract_feedback_entries_from_result(result):
                category = str(feedback_summary.get("category") or "").strip().lower()
                if category:
                    feedback_categories.append(category)
                    feedback_text = str(
                        feedback_summary.get("feedback_text")
                        or feedback_summary.get("content")
                        or ""
                    ).strip()
                    if feedback_text:
                        feedback_texts.append(trim_candidate_text(feedback_text, 44))
            draft_generation = result.get("draft_generation", {}) if isinstance(result.get("draft_generation"), dict) else {}
            strategy = draft_generation.get("strategy", {}) if isinstance(draft_generation.get("strategy"), dict) else {}
            response_mode = str(strategy.get("response_mode") or "").strip().lower()
            if response_mode:
                publish_modes.append(response_mode)

        role_next_experiments = [
            str(item.get("next_experiment") or "").strip()
            for item in role_reflection_contexts
            if isinstance(item, dict) and str(item.get("next_experiment") or "").strip()
        ]
        role_summaries = [
            str(item.get("summary") or "").strip()
            for item in role_reflection_contexts
            if isinstance(item, dict) and str(item.get("summary") or "").strip()
        ]
        role_blockers = [
            str(item.get("blocked_reason") or "").strip()
            for item in role_reflection_contexts
            if isinstance(item, dict) and str(item.get("blocked_reason") or "").strip()
        ]
        if role_next_experiments:
            next_step = role_next_experiments[0]
            if next_step not in next_steps:
                next_steps.insert(0, next_step)
        if role_summaries:
            focus = f"岗位最近反思: {role_summaries[0]}"
            if focus not in focus_points:
                focus_points.insert(0, focus)
        if role_blockers:
            blocker_focus = f"优先解除岗位当前阻塞: {role_blockers[0]}"
            if blocker_focus not in focus_points:
                focus_points.insert(0, blocker_focus)

        preferred_content_mode = ""
        if "worth_content" in feedback_categories:
            preferred_content_mode = "content_response"
            if "互动里已经出现值得承接的具体问题" not in focus_points:
                focus_points.insert(0, "互动里已经出现值得承接的具体问题")
            content_step = "优先做一条解释型内容，正面承接用户最关心的问题"
            if content_step not in next_steps:
                next_steps.insert(0, content_step)
        elif "worth_follow" in feedback_categories:
            preferred_content_mode = "follow_response"
            if "互动里出现可继续延展的讨论点" not in focus_points:
                focus_points.insert(0, "互动里出现可继续延展的讨论点")
            follow_step = "优先做一条轻互动延展内容，把讨论继续往下带"
            if follow_step not in next_steps:
                next_steps.insert(0, follow_step)
        elif "worth_greeting" in feedback_categories:
            preferred_content_mode = "light_social"
            if "当前更适合先建立轻量互动存在感" not in focus_points:
                focus_points.insert(0, "当前更适合先建立轻量互动存在感")
            greeting_step = "先保持轻量打招呼和观察，等出现更明确的话题再放大"
            if greeting_step not in next_steps:
                next_steps.insert(0, greeting_step)
        elif publish_modes:
            preferred_content_mode = publish_modes[0]

        feedback_goal_hint = ""
        if feedback_texts:
            feedback_goal_hint = "；".join(feedback_texts[:2])
            feedback_focus = f"优先围绕这些反馈继续推进：{feedback_goal_hint}"
            if feedback_focus not in focus_points:
                focus_points.append(feedback_focus)

        if not focus_points and not next_steps:
            return {
                "title": "等待更多运行结果",
                "status": "pending",
                "goal": goal,
                "focus_points": [],
                "next_steps": [],
                "preferred_content_mode": "",
                "feedback_goal_hint": "",
            }

        return {
            "title": "下一轮自治行动计划",
            "status": "ready",
            "goal": goal,
            "focus_points": focus_points[:4],
            "next_steps": next_steps[:6],
            "preferred_content_mode": preferred_content_mode,
            "feedback_goal_hint": feedback_goal_hint,
            "role_reflection_experiments": role_next_experiments[:3],
            "role_reflection_summaries": role_summaries[:3],
        }

    def build_mission_growth_timeline(actions: list[dict]) -> list[dict]:
        timeline: list[dict] = []
        for item in actions:
            if not isinstance(item, dict):
                continue
            result = item.get("task_result", {}) if isinstance(item.get("task_result"), dict) else {}
            growth = item.get("growth_update", {}) if isinstance(item.get("growth_update"), dict) else {}
            recorded_at = growth.get("recorded_at")
            if not recorded_at:
                continue
            timeline.append({
                "timestamp": recorded_at,
                "event_type": str(item.get("task_type") or item.get("action_type") or "mission_task"),
                "title": str(item.get("title") or item.get("node_id") or "mission action"),
                "detail": str(result.get("insight_summary") or result.get("message") or item.get("detail") or "").strip(),
                "experience_id": growth.get("experience_id") or result.get("experience_id"),
            })
        timeline.sort(key=lambda item: item["timestamp"], reverse=True)
        return timeline[:8]

    return {
        "build_mission_next_cycle_plan": build_mission_next_cycle_plan,
        "build_mission_growth_timeline": build_mission_growth_timeline,
    }
