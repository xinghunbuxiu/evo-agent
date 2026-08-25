"""
自媒体运营工种运行时。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from core import Experience, ExperienceStore
from .content import run_toutiao_publish_draft
from .feedback import (
    process_toutiao_feedback,
    process_toutiao_feedback_collection,
)


WORKER_SCOPE = {
    "work_type_id": "self_media_operations",
    "capability_type": "automation",
    "owned_modules": [
        "feedback",
        "content",
        "monitor",
        "runtime",
    ],
}


def handle_self_media_operation_mission_node(
    *,
    task_queue,
    tenant_id: str,
    mission_run_id: str,
    plan: dict,
    node: dict,
    resolved_context: dict,
    work_type: dict,
    work_type_summary: dict,
    counts: dict,
    actions: list[dict],
    submitted_task_ids: list[str],
    matched_skill_ids: list[str],
    matched_skills: list[dict],
    append_action: Callable[..., None],
    task_priority_cls,
) -> bool:
    node_id = str(node.get("id") or "node")
    task_type = str(node.get("task_type") or "plan")
    channel = str(resolved_context.get("channel") or "").strip().lower()
    role_reflection_context = (
        node.get("role_reflection_context", {})
        if isinstance(node.get("role_reflection_context"), dict)
        else {}
    )
    role_reflection_summary = str(role_reflection_context.get("summary") or "").strip()
    role_reflection_experiment = str(role_reflection_context.get("next_experiment") or "").strip()
    if channel != "toutiao":
        return False

    if task_type == "execute":
        base_payload = {
            "channel": channel,
            "work_type_id": work_type.get("work_type_id"),
            "deliverable_goal": resolved_context.get("deliverable_goal"),
            "account_id": resolved_context.get("account_id") or "default",
            "_mission_run_id": mission_run_id,
            "_mission_node_id": node_id,
            "_mission_kind": plan.get("mission_kind"),
            "_goal": plan.get("goal"),
            "_role_reflection_context": role_reflection_context,
            "_role_reflection_summary": role_reflection_summary,
            "_role_reflection_experiment": role_reflection_experiment,
        }
        created = task_queue.submit(
            task_type="operation_validate",
            payload=base_payload,
            priority=task_priority_cls.NORMAL,
            tenant_id=tenant_id,
        )
        submitted_task_ids.append(created.id)
        counts["submitted"] += 1
        append_action(
            actions=actions,
            node_id=node_id,
            title=node.get("title"),
            action_type="task_submitted",
            status="submitted",
            detail=(
                f"已提交自媒体运营连接器验证任务，优先沿岗位实验推进：{role_reflection_experiment}"
                if role_reflection_experiment
                else "已提交自媒体运营连接器验证任务"
            ),
            matched_skill_ids=matched_skill_ids,
            matched_skills=matched_skills,
            work_type=work_type,
            work_type_summary=work_type_summary,
            extra={
                "task_type": "operation_validate",
                "task_id": created.id,
                "role_reflection_context": role_reflection_context,
            },
        )
        if bool(resolved_context.get("auto_publish_draft")):
            draft_payload = {
                **base_payload,
                "content": resolved_context.get("draft_content"),
                "topic": resolved_context.get("topic"),
                "audience_hint": resolved_context.get("audience_hint"),
                "publish_content_type": resolved_context.get("publish_content_type") or "weitoutiao",
                "article_title": resolved_context.get("article_title"),
            }
            draft_created = task_queue.submit(
                task_type="operation_publish_draft",
                payload=draft_payload,
                priority=task_priority_cls.NORMAL,
                tenant_id=tenant_id,
            )
            submitted_task_ids.append(draft_created.id)
            counts["submitted"] += 1
            append_action(
                actions=actions,
                node_id=node_id,
                title=f"{node.get('title')} / draft",
                action_type="task_submitted",
                status="submitted",
                detail=(
                    f"已提交头条微头条草稿发布任务，参考岗位实验：{role_reflection_experiment}"
                    if role_reflection_experiment
                    else "已提交头条微头条草稿发布任务"
                ),
                matched_skill_ids=matched_skill_ids,
                matched_skills=matched_skills,
                work_type=work_type,
                work_type_summary=work_type_summary,
                extra={
                    "task_type": "operation_publish_draft",
                    "task_id": draft_created.id,
                    "role_reflection_context": role_reflection_context,
                },
            )
        return True

    if node_id == "review_and_iterate":
        analytics_types = resolved_context.get("analytics_types", ["fans"])
        if not isinstance(analytics_types, list):
            analytics_types = ["fans"]
        analytics_types = [str(item).strip().lower() for item in analytics_types if str(item).strip()] or ["fans"]
        analytics_title_map = {
            "fans": "粉丝画像",
            "works": "作品表现",
            "income": "收益表现",
            "content-detail": "内容详情",
        }
        for analytics_type in analytics_types:
            payload = {
                "channel": channel,
                "work_type_id": work_type.get("work_type_id"),
                "account_id": resolved_context.get("account_id") or "default",
                "analytics_type": analytics_type,
                "content_type": resolved_context.get("analytics_content_type"),
                "detail_content_type": resolved_context.get("detail_content_type"),
                "content_id": resolved_context.get("content_id"),
                "_mission_run_id": mission_run_id,
                "_mission_node_id": node_id,
                "_mission_kind": plan.get("mission_kind"),
                "_goal": plan.get("goal"),
                "_role_reflection_context": role_reflection_context,
                "_role_reflection_summary": role_reflection_summary,
                "_role_reflection_experiment": role_reflection_experiment,
            }
            created = task_queue.submit(
                task_type="operation_analytics",
                payload=payload,
                priority=task_priority_cls.NORMAL,
                tenant_id=tenant_id,
            )
            submitted_task_ids.append(created.id)
            counts["submitted"] += 1
            analytics_label = analytics_title_map.get(analytics_type, analytics_type)
            append_action(
                actions=actions,
                node_id=node_id,
                title=f"{node.get('title')} / {analytics_label}",
                action_type="task_submitted",
                status="submitted",
                detail=f"已提交头条{analytics_label}分析任务",
                matched_skill_ids=matched_skill_ids,
                matched_skills=matched_skills,
                work_type=work_type,
                work_type_summary=work_type_summary,
                extra={
                    "task_type": "operation_analytics",
                    "task_id": created.id,
                    "role_reflection_context": role_reflection_context,
                },
            )
        if bool(resolved_context.get("auto_collect_feedback", True)):
            feedback_payload = {
                "channel": channel,
                "work_type_id": work_type.get("work_type_id"),
                "account_id": resolved_context.get("account_id") or "default",
                "topic": resolved_context.get("topic"),
                "max_comments": resolved_context.get("max_feedback_comments") or 8,
                "auto_reply_feedback": bool(resolved_context.get("auto_reply_feedback", False)),
                "reply_limit": resolved_context.get("feedback_reply_limit") or 2,
                "with_replies": True,
                "_mission_run_id": mission_run_id,
                "_mission_node_id": node_id,
                "_mission_kind": plan.get("mission_kind"),
                "_goal": plan.get("goal"),
                "_role_reflection_context": role_reflection_context,
                "_role_reflection_summary": role_reflection_summary,
                "_role_reflection_experiment": role_reflection_experiment,
            }
            feedback_created = task_queue.submit(
                task_type="operation_feedback_collect",
                payload=feedback_payload,
                priority=task_priority_cls.NORMAL,
                tenant_id=tenant_id,
            )
            submitted_task_ids.append(feedback_created.id)
            counts["submitted"] += 1
            append_action(
                actions=actions,
                node_id=node_id,
                title=f"{node.get('title')} / 评论采集",
                action_type="task_submitted",
                status="submitted",
                detail="已提交头条评论采集与互动分析任务",
                matched_skill_ids=matched_skill_ids,
                matched_skills=matched_skills,
                work_type=work_type,
                work_type_summary=work_type_summary,
                extra={
                    "task_type": "operation_feedback_collect",
                    "task_id": feedback_created.id,
                    "role_reflection_context": role_reflection_context,
                },
            )
        return True

    return False


def build_self_media_operation_mission_summary(
    *,
    mission_run: dict,
    refreshed_actions: list[dict],
) -> dict:
    summary = {
        "channel": "toutiao",
        "connector": {},
        "draft": {},
        "analytics": [],
        "feedback": {},
        "growth_updates": [],
        "recommended_next_actions": [],
        "role_reflection": {},
    }
    recommended_next_actions: list[str] = []

    for action in refreshed_actions:
        if not isinstance(action, dict):
            continue
        task_type = str(action.get("task_type") or "").strip()
        task_result = action.get("task_result", {}) if isinstance(action.get("task_result"), dict) else {}
        next_actions = task_result.get("next_actions", []) if isinstance(task_result.get("next_actions"), list) else []
        for item in next_actions:
            text = str(item).strip()
            if text and text not in recommended_next_actions:
                recommended_next_actions.append(text)
        role_reflection_context = action.get("role_reflection_context", {}) if isinstance(action.get("role_reflection_context"), dict) else {}
        if role_reflection_context and not summary["role_reflection"]:
            summary["role_reflection"] = role_reflection_context

        growth_update = task_result.get("growth_update", {}) if isinstance(task_result.get("growth_update"), dict) else {}
        if growth_update:
            summary["growth_updates"].append(growth_update)

        if task_type == "operation_validate":
            probe_result = task_result.get("probe_result", {}) if isinstance(task_result.get("probe_result"), dict) else {}
            executor = task_result.get("executor", {}) if isinstance(task_result.get("executor"), dict) else {}
            summary["connector"] = {
                "status": task_result.get("validation_outcome"),
                "account": task_result.get("account"),
                "username": probe_result.get("username"),
                "logged_in": probe_result.get("logged_in"),
                "message": task_result.get("message"),
                "executor_name": executor.get("name"),
                "executor_adapter": executor.get("adapter"),
                "executor_root_dir": executor.get("root_dir"),
            }
        elif task_type == "operation_publish_draft":
            result = task_result.get("result", {}) if isinstance(task_result.get("result"), dict) else {}
            summary["draft"] = {
                "status": result.get("action") or task_result.get("message"),
                "topic": task_result.get("topic"),
                "publish_content_type": task_result.get("publish_content_type"),
                "article_title": task_result.get("article_title"),
                "preview": task_result.get("draft_content_preview"),
                "message": task_result.get("message"),
                "experience_id": task_result.get("experience_id"),
                "executor_name": task_result.get("executor_name"),
                "executor_adapter": task_result.get("executor_adapter"),
                "executor_root_dir": task_result.get("executor_root_dir"),
                "draft_path": result.get("draft_path"),
                "article_path": result.get("article_path"),
            }
        elif task_type == "operation_analytics":
            analytics_summary = task_result.get("analytics_summary", {}) if isinstance(task_result.get("analytics_summary"), dict) else {}
            summary["analytics"].append({
                "analytics_type": analytics_summary.get("analytics_type") or task_result.get("analytics_type"),
                "headline": analytics_summary.get("headline") or task_result.get("message"),
                "insight_summary": analytics_summary.get("insight_summary") or task_result.get("insight_summary"),
                "recommendations": analytics_summary.get("recommendations", []) if isinstance(analytics_summary.get("recommendations"), list) else [],
                "experience_id": task_result.get("experience_id"),
            })
        elif task_type == "operation_feedback_collect":
            feedback_collection = task_result.get("feedback_collection", {}) if isinstance(task_result.get("feedback_collection"), dict) else {}
            summary["feedback"] = {
                "headline": feedback_collection.get("headline") or task_result.get("message"),
                "insight_summary": feedback_collection.get("insight_summary"),
                "selected_feedback": feedback_collection.get("selected_feedback", []) if isinstance(feedback_collection.get("selected_feedback"), list) else [],
                "recommended_actions": feedback_collection.get("recommended_actions", []) if isinstance(feedback_collection.get("recommended_actions"), list) else [],
                "experience_id": task_result.get("experience_id"),
            }

    summary["analytics"] = summary["analytics"][:6]
    summary["growth_updates"] = summary["growth_updates"][:8]
    role_reflection_experiment = str(summary["role_reflection"].get("next_experiment") or "").strip() if isinstance(summary["role_reflection"], dict) else ""
    if role_reflection_experiment and role_reflection_experiment not in recommended_next_actions:
        recommended_next_actions.insert(0, role_reflection_experiment)
    summary["recommended_next_actions"] = recommended_next_actions[:8]
    return summary


def summarize_toutiao_analytics_result(
    payload: dict,
    analytics_result: dict,
    *,
    safe_float: Callable[[object, float], float],
    safe_percent_value: Callable[[object], float],
    pick_top_distribution_item: Callable[..., dict | None],
    top_region_entries: Callable[[dict, int], list[dict]],
    trim_candidate_text: Callable[[str | None, int], str],
) -> dict:
    result = analytics_result.get("result", {}) if isinstance(analytics_result.get("result"), dict) else {}
    analytics_type = str(analytics_result.get("analytics_type") or payload.get("analytics_type") or "fans")
    role_reflection_summary = str(payload.get("_role_reflection_summary") or "").strip()
    role_reflection_experiment = str(payload.get("_role_reflection_experiment") or "").strip()
    summary = {
        "analytics_type": analytics_type,
        "headline": "已完成头条分析",
        "insight_summary": analytics_result.get("message") or "分析已完成",
        "recommendations": [],
        "structured": {},
    }
    if analytics_type == "works":
        metrics = result.get("metrics", {}) if isinstance(result.get("metrics"), dict) else {}
        top_regions = top_region_entries(metrics)
        impressions = str(metrics.get("昨日展现量") or metrics.get("展现量") or "--")
        views = str(metrics.get("昨日阅读(播放)量") or metrics.get("阅读(播放)量") or "--")
        likes = str(metrics.get("昨日点赞量") or metrics.get("点赞量") or "--")
        comments = str(metrics.get("昨日评论量") or metrics.get("评论量") or "--")
        headline = f"昨日展现 {impressions}，阅读/播放 {views}，点赞 {likes}，评论 {comments}"
        insight_parts = [headline]
        if top_regions:
            insight_parts.append("流量地域集中在 " + " / ".join(f"{item['name']} {item['percent']}" for item in top_regions))
        summary["headline"] = headline
        summary["insight_summary"] = "；".join(insight_parts)
        summary["recommendations"] = [
            "把作品分析和粉丝画像交叉看，确认高展现但低互动的问题出在标题、封面还是内容承接",
            "优先复盘最近有展现的题材，抽取可复用的标题结构和开头写法",
            "如果阅读和互动仍低，下一轮尝试更强观点、更短开场和更清晰的利益点",
        ]
        if role_reflection_experiment:
            summary["recommendations"].insert(0, f"用作品表现验证当前岗位实验：{role_reflection_experiment}")
        summary["structured"] = {
            "impressions": impressions,
            "views": views,
            "likes": likes,
            "comments": comments,
            "top_regions": top_regions,
        }
        return summary
    if analytics_type == "income":
        data_entries = result.get("data", []) if isinstance(result.get("data"), list) else []
        withdraw_total = 0.0
        total_income = 0.0
        income_breakdown: dict[str, float] = {}
        for entry in data_entries:
            if not isinstance(entry, dict):
                continue
            data = entry.get("data")
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "can_withdraw_amount":
                    withdraw_total = safe_float(item.get("total"), withdraw_total)
                    settle_info = item.get("settle_info", {}) if isinstance(item.get("settle_info"), dict) else {}
                    settle_detail = settle_info.get("settle_detail", {}) if isinstance(settle_info.get("settle_detail"), dict) else {}
                    for key, value in settle_detail.items():
                        income_breakdown[str(key)] = safe_float(value, 0.0)
                elif item.get("type") == "total_income":
                    total_income = safe_float(item.get("total"), total_income)
        top_income_parts = sorted(income_breakdown.items(), key=lambda item: item[1], reverse=True)
        headline = f"累计收益 {total_income:.2f}，可提现 {withdraw_total:.2f}"
        insight_parts = [headline]
        if top_income_parts:
            insight_parts.append("收益主要来自 " + " / ".join(f"{name} {amount:.2f}" for name, amount in top_income_parts[:3]))
        if role_reflection_summary:
            insight_parts.append(f"当前岗位判断 {role_reflection_summary}")
        summary["headline"] = headline
        summary["insight_summary"] = "；".join(insight_parts)
        summary["recommendations"] = [
            "把高收益内容类型和近期发布动作关联，确认真正带来收益的是图文、微头条还是问答",
            "若收益集中在少数内容类型，下一轮优先放大该类型产出频率",
            "持续记录收益变化，等样本足够后再决定是否进入正式发布和调度",
        ]
        if role_reflection_experiment:
            summary["recommendations"].insert(0, f"重点确认“{role_reflection_experiment}”是否开始转化为真实收益")
        summary["structured"] = {
            "withdraw_total": round(withdraw_total, 2),
            "total_income": round(total_income, 2),
            "income_breakdown": [{"name": name, "amount": round(amount, 2)} for name, amount in top_income_parts[:5]],
        }
        return summary
    if analytics_type != "fans":
        summary["recommendations"] = [
            "把本次分析结果与后续发布内容关联，形成可复盘样本",
            "继续补采集 works / income 数据，让运营优化不只看粉丝画像",
        ]
        if role_reflection_experiment:
            summary["recommendations"].insert(0, f"结合当前岗位实验“{role_reflection_experiment}”判断这组数据是否支持继续推进")
        return summary

    metrics = result.get("metrics", {}) if isinstance(result.get("metrics"), dict) else {}
    distributions = result.get("distributions", {}) if isinstance(result.get("distributions"), dict) else {}
    top_age = pick_top_distribution_item(distributions.get("age"))
    top_gender = pick_top_distribution_item(distributions.get("gender"))
    top_device = pick_top_distribution_item(distributions.get("devicePrice"))
    top_regions = top_region_entries(metrics)
    hot_works = result.get("distributions", {}).get("fansViewedWorks", [])
    hot_works = hot_works if isinstance(hot_works, list) else []
    hot_work_titles = [
        trim_candidate_text(str(item.get("title") or ""), 48)
        for item in hot_works[:3]
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
    active_fans = str(metrics.get("昨日活跃粉丝数") or metrics.get("粉丝数") or "--")
    total_fans = str(metrics.get("昨日粉丝总数") or "--")
    fan_delta = str(metrics.get("昨日粉丝变化数") or metrics.get("涨粉数") or "--")
    headline = f"昨日活跃粉丝 {active_fans}，总粉丝 {total_fans}，涨粉 {fan_delta}"

    insight_parts = [headline]
    if top_age:
        insight_parts.append(f"年龄主力 {top_age.get('label')} ({top_age.get('percent')})")
    if top_gender:
        insight_parts.append(f"性别主力 {top_gender.get('label')} ({top_gender.get('percent')})")
    if top_regions:
        insight_parts.append("地域集中在 " + " / ".join(f"{item['name']} {item['percent']}" for item in top_regions))
    if role_reflection_summary:
        insight_parts.append(f"当前岗位判断 {role_reflection_summary}")
    insight_summary = "；".join(insight_parts)

    recommendations: list[str] = []
    if top_age and str(top_age.get("label")) in {"31-40", "41-50", "50+"}:
        recommendations.append("内容选题偏向成熟受众，优先现实议题、观点解读、生活经验类表达")
    if top_gender and str(top_gender.get("label")) == "男性":
        recommendations.append("文案可以增加观点强度和信息密度，标题更直接一些")
    if top_device and safe_percent_value(top_device.get("percent")) >= 25 and str(top_device.get("label")) in {"1000~1999", "2000~2999"}:
        recommendations.append("封面和排版保持清晰直给，兼顾中端机阅读体验，不要过度堆视觉元素")
    if hot_work_titles:
        recommendations.append("复用最近被粉丝反复查看的话题方向，优先围绕高浏览主题做二次延展")
    if not recommendations:
        recommendations.append("继续累计 3-5 次分析结果，再提炼更稳定的内容策略")
    if role_reflection_experiment:
        recommendations.insert(0, f"下一轮优先验证岗位实验：{role_reflection_experiment}")
    recommendations.append("下一步补跑 works / income 分析，把画像和收益表现真正关联起来")

    summary["headline"] = headline
    summary["insight_summary"] = insight_summary
    summary["recommendations"] = recommendations[:4]
    summary["structured"] = {
        "active_fans": active_fans,
        "total_fans": total_fans,
        "fan_delta": fan_delta,
        "top_age": top_age,
        "top_gender": top_gender,
        "top_device_price": top_device,
        "top_regions": top_regions,
        "top_viewed_work_titles": hot_work_titles,
    }
    return summary


def build_toutiao_operation_experience(
    task,
    result: dict,
    *,
    trim_candidate_text: Callable[[str | None, int], str],
    summarize_analytics_result: Callable[[dict, dict], dict],
) -> Experience | None:
    if not isinstance(result, dict):
        return None
    payload = task.payload or {}
    channel = str(result.get("channel") or payload.get("channel") or "").strip().lower()
    if channel != "toutiao":
        return None

    outcome = str(result.get("validation_outcome") or "unknown")
    account = str(result.get("account") or payload.get("account_id") or "default")
    domain = "automation"
    task_type = task.type
    quality_score_map = {
        "passed": 0.92,
        "auth_required": 0.35,
        "connector_missing": 0.1,
        "dependency_missing": 0.12,
        "probe_failed": 0.2,
    }
    quality_score = quality_score_map.get(outcome, 0.3)
    insight_summary = str(result.get("insight_summary") or result.get("message") or "").strip()
    role_reflection_summary = str(payload.get("_role_reflection_summary") or "").strip()
    role_reflection_experiment = str(payload.get("_role_reflection_experiment") or "").strip()
    metadata = {
        "channel": channel,
        "account": account,
        "validation_outcome": outcome,
        "connector": result.get("connector"),
        "executor_name": result.get("executor_name"),
        "executor_adapter": result.get("executor_adapter"),
        "executor_root_dir": result.get("executor_root_dir"),
        "ops_dir": result.get("ops_dir"),
        "mission_refs": {
            "mission_run_id": payload.get("_mission_run_id"),
            "mission_node_id": payload.get("_mission_node_id"),
            "mission_kind": payload.get("_mission_kind"),
            "goal": payload.get("_goal"),
            "work_type_id": payload.get("work_type_id"),
            "role_reflection_context": payload.get("_role_reflection_context"),
            "role_reflection_summary": payload.get("_role_reflection_summary"),
            "role_reflection_experiment": payload.get("_role_reflection_experiment"),
        },
    }

    input_summary = str(payload.get("deliverable_goal") or payload.get("_goal") or payload.get("channel") or task.type)
    output_summary = result.get("message") or task.type

    def merge_role_recommendations(items: list[str]) -> list[str]:
        merged: list[str] = []
        if role_reflection_experiment:
            merged.append(f"继续推进岗位实验：{role_reflection_experiment}")
        for item in items:
            text = str(item).strip()
            if text and text not in merged:
                merged.append(text)
        return merged[:5]

    if task.type == "operation_validate":
        probe_result = result.get("probe_result", {}) if isinstance(result.get("probe_result"), dict) else {}
        username = str(probe_result.get("username") or "").strip()
        if username:
            output_summary = f"头条连接器可用，账号 {username} 已就绪"
        elif outcome == "auth_required":
            output_summary = "头条连接器已接入，但账号仍需登录"
        metadata["probe_result"] = {
            "logged_in": probe_result.get("logged_in"),
            "username": probe_result.get("username"),
            "profile_url": probe_result.get("profileUrl"),
        }
        result["insight_summary"] = (
            f"{output_summary}；当前岗位判断 {role_reflection_summary}"
            if role_reflection_summary
            else output_summary
        )
    elif task.type == "operation_publish_draft":
        publish_result = result.get("result", {}) if isinstance(result.get("result"), dict) else {}
        action = str(publish_result.get("action") or "").strip()
        content_preview = str(result.get("draft_content_preview") or publish_result.get("content") or "").strip()
        output_summary = "头条草稿已保存" if action == "draft_saved" else (result.get("message") or "头条草稿处理完成")
        draft_generation = result.get("draft_generation", {}) if isinstance(result.get("draft_generation"), dict) else {}
        metadata["draft_publish"] = {
            "action": action,
            "url": publish_result.get("url"),
            "content_preview": trim_candidate_text(content_preview, 120),
            "topic": payload.get("topic"),
            "generation_strategy": draft_generation.get("strategy"),
        }
        result["insight_summary"] = output_summary
        result["next_actions"] = merge_role_recommendations([
            "继续执行粉丝/作品/收益分析，判断这类内容是否值得正式发布",
            "结合历史高表现选题继续补全文案和素材",
        ])
        if isinstance(draft_generation.get("strategy"), dict):
            strategy = draft_generation.get("strategy", {})
            strategy_title = str(strategy.get("title") or "").strip()
            strategy_style = str(strategy.get("style_hint") or "").strip()
            if strategy_title or strategy_style:
                insight_parts = [
                    output_summary,
                    *(["标题方向 " + strategy_title] if strategy_title else []),
                    *(["表达策略 " + strategy_style] if strategy_style else []),
                ]
                if role_reflection_experiment:
                    insight_parts.append("岗位实验 " + role_reflection_experiment)
                result["insight_summary"] = "；".join(insight_parts)
    elif task.type == "operation_feedback_review":
        feedback_summary = result.get("feedback_summary", {}) if isinstance(result.get("feedback_summary"), dict) else {}
        output_summary = str(feedback_summary.get("headline") or result.get("message") or "反馈处理完成").strip()
        metadata["feedback_review"] = feedback_summary
        result["insight_summary"] = str(feedback_summary.get("insight_summary") or output_summary).strip()
        result["next_actions"] = merge_role_recommendations(
            feedback_summary.get("recommended_actions", []) if isinstance(feedback_summary.get("recommended_actions"), list) else []
        )
    elif task.type == "operation_feedback_collect":
        feedback_collection = result.get("feedback_collection", {}) if isinstance(result.get("feedback_collection"), dict) else {}
        output_summary = str(feedback_collection.get("headline") or result.get("message") or "评论采集处理完成").strip()
        metadata["feedback_collection"] = feedback_collection
        result["insight_summary"] = str(feedback_collection.get("insight_summary") or output_summary).strip()
        result["next_actions"] = merge_role_recommendations(
            feedback_collection.get("recommended_actions", []) if isinstance(feedback_collection.get("recommended_actions"), list) else []
        )
    elif task.type == "operation_analytics":
        analytics_summary = summarize_analytics_result(payload, result)
        insight_summary = str(analytics_summary.get("insight_summary") or insight_summary).strip()
        output_summary = analytics_summary.get("headline") or output_summary
        metadata["analytics"] = analytics_summary
        metadata["analytics_type"] = result.get("analytics_type")
        result["analytics_summary"] = analytics_summary
        result["insight_summary"] = insight_summary
        result["next_actions"] = merge_role_recommendations(analytics_summary.get("recommendations", []))
    insight_summary = str(result.get("insight_summary") or insight_summary).strip()
    if insight_summary:
        metadata["insight_summary"] = insight_summary
    recommendations = result.get("next_actions", []) if isinstance(result.get("next_actions"), list) else []
    metadata["recommendations"] = recommendations[:5]

    experience_id = f"{task.type}_{channel}_{task.id}"
    result["experience_id"] = experience_id
    result["experience_domain"] = domain
    result.setdefault("next_actions", recommendations[:5])
    return Experience(
        id=experience_id,
        domain=domain,
        task_type=task_type,
        input_summary=input_summary,
        output_summary=output_summary,
        quality_score=quality_score,
        capability_type="automation",
        metadata=metadata,
    )


def record_operation_experience(
    workspace: Path,
    task,
    result: dict,
    *,
    trim_candidate_text: Callable[[str | None, int], str],
    summarize_analytics_result: Callable[[dict, dict], dict],
) -> dict:
    experience = build_toutiao_operation_experience(
        task,
        result,
        trim_candidate_text=trim_candidate_text,
        summarize_analytics_result=summarize_analytics_result,
    )
    if experience is None:
        return result
    ExperienceStore(workspace, str(task.tenant_id or "default")).save(experience)
    result["experience_recorded"] = True
    result["growth_update"] = {
        "experience_id": experience.id,
        "domain": experience.domain,
        "task_type": experience.task_type,
        "quality_score": experience.quality_score,
        "recorded_at": experience.created_at,
    }
    return result


def build_operation_experience_timeline(experiences: list[Experience]) -> list[dict]:
    timeline: list[dict] = []
    for exp in experiences:
        if exp.domain != "automation":
            continue
        metadata = exp.metadata if isinstance(exp.metadata, dict) else {}
        channel = str(metadata.get("channel") or "").strip()
        if not channel:
            continue
        timeline.append({
            "timestamp": exp.created_at,
            "strategy_id": None,
            "event_type": exp.task_type,
            "title": f"{channel} / {exp.task_type}",
            "detail": str(metadata.get("insight_summary") or exp.output_summary or "").strip(),
        })
    timeline.sort(key=lambda item: item["timestamp"], reverse=True)
    return timeline[:12]


def register_self_media_operation_handlers(
    *,
    task_queue,
    workspace: Path,
    finalize_operation_result: Callable[[object, dict], dict],
    run_probe_toutiao_connector: Callable[[Path, dict], dict],
    run_toutiao_analytics: Callable[[Path, dict], dict],
    run_toutiao_executor_cli: Callable[..., dict],
    load_recent_automation_experiences: Callable[..., list],
    trim_candidate_text: Callable[[str | None, int], str],
    run_comment_list: Callable[[Path, dict], dict],
    run_comment_reply: Callable[[Path, dict], dict],
    get_account_identity: Callable[[Path, str], dict],
) -> dict[str, Callable]:
    def handle_operation_validate(task):
        channel = str(task.payload.get("channel") or "").strip().lower()
        if not channel:
            raise ValueError("Missing channel")
        if channel == "toutiao":
            result = run_probe_toutiao_connector(workspace, task.payload or {})
            return finalize_operation_result(task, result)
        raise ValueError(f"Unsupported operation channel: {channel}")

    def handle_operation_analytics(task):
        channel = str(task.payload.get("channel") or "").strip().lower()
        if not channel:
            raise ValueError("Missing channel")
        if channel == "toutiao":
            result = run_toutiao_analytics(workspace, task.payload or {})
            return finalize_operation_result(task, result)
        raise ValueError(f"Unsupported operation channel: {channel}")

    def handle_operation_publish_draft(task):
        channel = str(task.payload.get("channel") or "").strip().lower()
        if not channel:
            raise ValueError("Missing channel")
        if channel == "toutiao":
            result = run_toutiao_publish_draft(
                workspace,
                str(task.tenant_id or "default"),
                task.payload or {},
                run_toutiao_executor_cli=run_toutiao_executor_cli,
                load_recent_automation_experiences=load_recent_automation_experiences,
                trim_candidate_text=trim_candidate_text,
            )
            return finalize_operation_result(task, result)
        raise ValueError(f"Unsupported operation channel: {channel}")

    def handle_operation_feedback_review(task):
        channel = str(task.payload.get("channel") or "").strip().lower()
        if not channel:
            raise ValueError("Missing channel")
        if channel == "toutiao":
            result = process_toutiao_feedback(task.payload or {})
            return finalize_operation_result(task, result)
        raise ValueError(f"Unsupported operation channel: {channel}")

    def handle_operation_feedback_collect(task):
        channel = str(task.payload.get("channel") or "").strip().lower()
        if not channel:
            raise ValueError("Missing channel")
        if channel == "toutiao":
            result = process_toutiao_feedback_collection(
                workspace,
                str(task.tenant_id or "default"),
                task.payload or {},
                run_comment_list=run_comment_list,
                run_comment_reply=run_comment_reply,
                get_account_identity=get_account_identity,
            )
            return finalize_operation_result(task, result)
        raise ValueError(f"Unsupported operation channel: {channel}")

    handlers = {
        "operation_validate": handle_operation_validate,
        "operation_analytics": handle_operation_analytics,
        "operation_publish_draft": handle_operation_publish_draft,
        "operation_feedback_review": handle_operation_feedback_review,
        "operation_feedback_collect": handle_operation_feedback_collect,
    }
    for task_type, handler in handlers.items():
        task_queue.register_handler(task_type, handler)
    return handlers
