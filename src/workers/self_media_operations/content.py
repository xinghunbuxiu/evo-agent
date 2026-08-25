"""
自媒体运营工种 - 内容承接域。

计划承接:
- 草稿生成
- 发酵评论转承接内容
- 内容策略胜率复盘
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable


def build_toutiao_content_strategy(
    workspace: Path,
    tenant_id: str,
    payload: dict,
    *,
    load_recent_automation_experiences: Callable[..., list],
    trim_candidate_text: Callable[[str | None, int], str],
) -> dict:
    topic = str(payload.get("topic") or "").strip()
    audience = str(payload.get("audience_hint") or "关注行业趋势的读者").strip()
    goal = str(payload.get("deliverable_goal") or payload.get("goal") or "继续优化内容运营策略").strip()
    goal_hint = str(payload.get("goal_hint") or "").strip()
    feedback_goal_hint = str(payload.get("feedback_goal_hint") or "").strip()
    role_reflection_summary = str(payload.get("_role_reflection_summary") or "").strip()
    role_reflection_experiment = str(payload.get("_role_reflection_experiment") or "").strip()
    preferred_mode = str(payload.get("content_mode") or payload.get("response_mode") or "").strip().lower()
    experiences = load_recent_automation_experiences(workspace, tenant_id, limit=12)
    analytics_payloads = []
    feedback_payloads = []
    for exp in experiences:
        metadata = exp.metadata if isinstance(exp.metadata, dict) else {}
        analytics = metadata.get("analytics", {}) if isinstance(metadata.get("analytics"), dict) else {}
        if analytics:
            analytics_payloads.append(analytics)
        feedback_review = metadata.get("feedback_review", {}) if isinstance(metadata.get("feedback_review"), dict) else {}
        if feedback_review:
            feedback_payloads.append(feedback_review)
        feedback_collection = metadata.get("feedback_collection", {}) if isinstance(metadata.get("feedback_collection"), dict) else {}
        for item in (feedback_collection.get("selected_feedback") or []):
            if isinstance(item, dict):
                feedback_payloads.append(item)

    top_age = None
    top_gender = None
    top_regions: list[dict] = []
    hot_titles: list[str] = []
    income_parts: list[dict] = []
    feedback_questions: list[str] = []
    feedback_requests: list[str] = []
    for analytics in analytics_payloads:
        analytics_type = str(analytics.get("analytics_type") or "").strip().lower()
        structured = analytics.get("structured", {}) if isinstance(analytics.get("structured"), dict) else {}
        if analytics_type == "fans":
            top_age = top_age or structured.get("top_age")
            top_gender = top_gender or structured.get("top_gender")
            if not top_regions:
                top_regions = structured.get("top_regions", []) if isinstance(structured.get("top_regions"), list) else []
            if not hot_titles:
                hot_titles = [
                    str(item).strip()
                    for item in (structured.get("top_viewed_work_titles", []) if isinstance(structured.get("top_viewed_work_titles"), list) else [])
                    if str(item).strip()
                ][:3]
        elif analytics_type == "income" and not income_parts:
            income_parts = structured.get("income_breakdown", []) if isinstance(structured.get("income_breakdown"), list) else []
    for feedback in feedback_payloads:
        category = str(feedback.get("category") or "").strip().lower()
        text = str(feedback.get("feedback_text") or "").strip()
        if not text:
            continue
        if category in {"worth_content", "question", "request"}:
            feedback_questions.append(trim_candidate_text(text, 44))
        elif category in {"worth_follow", "discussion", "praise"}:
            feedback_requests.append(trim_candidate_text(text, 44))

    title = topic or "今天看到一个现象，越想越觉得值得聊聊"
    if hot_titles and not topic:
        seed = hot_titles[0]
        title = seed.replace("...", "").strip() or title
    if feedback_goal_hint and not topic:
        title = trim_candidate_text(feedback_goal_hint.rstrip("。！？!?"), 24) or title
    age_hint = str((top_age or {}).get("label") or "").strip()
    gender_hint = str((top_gender or {}).get("label") or "").strip()
    region_hint = "、".join(
        str(item.get("name") or "").strip()
        for item in top_regions[:3]
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    )
    income_hint = "、".join(
        f"{item.get('name')} {item.get('amount')}"
        for item in income_parts[:2]
        if isinstance(item, dict)
    )
    style_hint = "观点更直接，信息密度更高"
    if age_hint in {"50+", "41-50"}:
        style_hint = "更贴近现实观察和生活感受，少空话，多结论"
    response_mode = "general"
    if preferred_mode in {"content_response", "follow_response", "light_social"}:
        response_mode = preferred_mode
    if feedback_questions:
        response_mode = "content_response"
        style_hint = "先回答关键疑问，再给判断依据，语气真诚直接"
    elif feedback_requests:
        response_mode = "follow_response"
        style_hint = "围绕用户点名想看的方向展开，尽量给到更具体的信息"
    elif response_mode == "content_response":
        style_hint = "围绕一个明确问题展开解释，先给结论，再给依据"
    elif response_mode == "follow_response":
        style_hint = "顺着已有讨论往下写，像接话一样自然延展"
    elif response_mode == "light_social":
        style_hint = "先建立轻量互动感，语气亲近，重点放在引出下一轮讨论"
    if role_reflection_experiment:
        style_hint += f"，并围绕当前岗位实验“{trim_candidate_text(role_reflection_experiment, 32)}”继续推进"

    opening = f"{title}。{goal}。"
    if goal_hint:
        opening += f"这一轮会重点盯住：{goal_hint}。"
    if role_reflection_summary:
        opening += f"结合最近岗位复盘，当前判断是：{trim_candidate_text(role_reflection_summary, 56)}。"
    if role_reflection_experiment:
        opening += f"这次会把实验重点放在：{trim_candidate_text(role_reflection_experiment, 40)}。"
    if feedback_goal_hint and response_mode in {"content_response", "follow_response"}:
        opening += f"尤其会承接大家最近提到的：{feedback_goal_hint}。"
    if region_hint:
        opening += f"最近尤其在{region_hint}这类地区更容易引发共鸣。"
    body_lines = [
        opening,
        "我想聊的核心不是热闹本身，而是这件事背后真正值得普通人留意的变化。",
        f"表达方式上会坚持 {style_hint}，尽量一开头就把观点说清楚。",
    ]
    if age_hint or gender_hint:
        body_lines.append(
            f"从当前反馈看，主要读者更偏向 {gender_hint or '成熟'} / {age_hint or '中青年'}，所以内容会更重事实判断和现实感。"
        )
    if income_hint:
        body_lines.append(f"从已有收益反馈看，{income_hint} 这类方向更值得持续放大。")
    if feedback_questions:
        question_text = str(feedback_questions[0]).rstrip("。！？!?")
        body_lines.append(f"最近不少人会问：{question_text}。这一轮内容会优先把这个问题讲透。")
    elif feedback_requests:
        request_text = str(feedback_requests[0]).rstrip("。！？!?")
        body_lines.append(f"最近有人点名想看：{request_text}。这一轮会优先顺着这个方向往下写。")
    elif feedback_goal_hint and response_mode == "content_response":
        body_lines.append(f"这次会直接回应一个更具体的问题：{feedback_goal_hint.rstrip('。！？!?')}。")
    elif feedback_goal_hint and response_mode == "follow_response":
        body_lines.append(f"这次会顺着大家最近提到的方向继续往下聊：{feedback_goal_hint.rstrip('。！？!?')}。")
    elif response_mode == "light_social":
        body_lines.append("这一轮先不急着讲太满，先把互动氛围带起来，再观察哪些点最值得继续深挖。")
    if role_reflection_experiment:
        body_lines.append(f"如果这轮反馈证明 {trim_candidate_text(role_reflection_experiment, 48)} 方向更有效，后面我会继续沿这条线放大。")
    body_lines.append("如果这件事放到我们自己身上，你会怎么选？欢迎理性聊聊。")
    hashtags: list[str] = []
    if topic:
        hashtags.append(f"#{topic}")
    if region_hint:
        hashtags.append("#热点观察")
    hashtags.append("#evo自动生成草稿")
    deduped_hashtags: list[str] = []
    for item in hashtags:
        if item not in deduped_hashtags:
            deduped_hashtags.append(item)
    return {
        "title": title,
        "audience": audience,
        "style_hint": style_hint,
        "response_mode": response_mode,
        "focus_points": [
            item
            for item in [
                role_reflection_experiment,
                goal_hint,
                feedback_goal_hint,
                age_hint,
                gender_hint,
                region_hint,
                income_hint,
                *feedback_questions[:1],
                *feedback_requests[:1],
            ]
            if item
        ][:4],
        "content": "\n\n".join(body_lines + [" ".join(deduped_hashtags)]),
    }


def build_toutiao_draft_content(
    workspace: Path,
    tenant_id: str,
    payload: dict,
    *,
    load_recent_automation_experiences: Callable[..., list],
    trim_candidate_text: Callable[[str | None, int], str],
) -> dict:
    strategy = build_toutiao_content_strategy(
        workspace,
        tenant_id,
        payload,
        load_recent_automation_experiences=load_recent_automation_experiences,
        trim_candidate_text=trim_candidate_text,
    )
    publish_content_type = str(payload.get("publish_content_type") or "weitoutiao").strip().lower()
    base_content = strategy.get("content") or "evo 自动草稿生成失败，请补充 topic / audience_hint 后重试。"
    if publish_content_type == "article":
        article_title = str(payload.get("article_title") or strategy.get("title") or payload.get("topic") or "Evo Article Draft").strip()
        role_reflection_summary = str(payload.get("_role_reflection_summary") or "").strip()
        role_reflection_experiment = str(payload.get("_role_reflection_experiment") or "").strip()
        article_sections = [
            f"## 先说结论\n\n{strategy.get('title') or article_title} 这件事，值得继续做下去。",
            "## 为什么现在值得做\n\n内容自动化不只是省时间，更重要的是把选题、表达、复盘变成可以持续进化的系统。",
            f"## 这一篇想讲什么\n\n{base_content}",
            "## 接下来怎么验证\n\n先产出、再看反馈、再做下一轮优化。只要形成闭环，系统就会越跑越稳。",
        ]
        if role_reflection_summary or role_reflection_experiment:
            article_sections.insert(
                3,
                "## 当前岗位实验\n\n"
                + "；".join(
                    [
                        part
                        for part in [
                            f"最近岗位判断：{role_reflection_summary}" if role_reflection_summary else "",
                            f"这一轮重点实验：{role_reflection_experiment}" if role_reflection_experiment else "",
                        ]
                        if part
                    ]
                ),
            )
        return {
            "content": "\n\n".join(article_sections).strip(),
            "title": article_title,
            "strategy": strategy,
            "content_type": "article",
        }
    return {
        "content": base_content,
        "title": str(strategy.get("title") or payload.get("topic") or "").strip() or None,
        "strategy": strategy,
        "content_type": "weitoutiao",
    }


def run_toutiao_publish_draft(
    workspace: Path,
    tenant_id: str,
    payload: dict,
    *,
    run_toutiao_executor_cli: Callable[..., dict],
    load_recent_automation_experiences: Callable[..., list],
    trim_candidate_text: Callable[[str | None, int], str],
) -> dict:
    account = str(payload.get("account_id") or "default")
    provided_content = str(payload.get("content") or "").strip()
    generated = None
    if not provided_content:
        generated = build_toutiao_draft_content(
            workspace,
            tenant_id,
            payload,
            load_recent_automation_experiences=load_recent_automation_experiences,
            trim_candidate_text=trim_candidate_text,
        )
    content = provided_content or str((generated or {}).get("content") or "").strip()
    topic = str(payload.get("topic") or "").strip()
    publish_content_type = str(payload.get("publish_content_type") or (generated or {}).get("content_type") or "weitoutiao").strip().lower()
    title = str(payload.get("article_title") or (generated or {}).get("title") or "").strip()
    args = ["publish", publish_content_type, "--account", account, "--content", content, "--draft", "--headless"]
    if topic:
        args.extend(["--topic", topic])
    if title:
        args.extend(["--title", title])

    command_result = run_toutiao_executor_cli(workspace, args, payload=payload)
    parsed = command_result.get("parsed")
    executor = command_result.get("executor", {}) if isinstance(command_result.get("executor"), dict) else {}
    connector_name = str(executor.get("name") or executor.get("adapter") or "toutiao_executor")
    executor_adapter = str(executor.get("adapter") or "").strip() or None
    executor_root_dir = str(executor.get("root_dir") or "").strip() or None
    if command_result.get("ok") and isinstance(parsed, dict):
        return {
            "connector": connector_name,
            "executor_name": connector_name,
            "executor_adapter": executor_adapter,
            "executor_root_dir": executor_root_dir,
            "channel": "toutiao",
            "validation_outcome": "passed",
            "message": "头条微头条草稿发布成功",
            "ops_dir": command_result.get("ops_dir"),
            "account": account,
            "publish_content_type": publish_content_type,
            "article_title": title or None,
            "draft_content_preview": content[:80],
            "draft_generation": generated,
            "result": parsed,
        }

    combined = command_result.get("stdout") or command_result.get("stderr") or ""
    if "未登录" in combined or "auth login" in combined.lower():
        return {
            "connector": connector_name,
            "executor_name": connector_name,
            "executor_adapter": executor_adapter,
            "executor_root_dir": executor_root_dir,
            "channel": "toutiao",
            "validation_outcome": "auth_required",
            "message": "头条执行器已接入，但当前账号未登录",
            "ops_dir": command_result.get("ops_dir"),
            "account": account,
            "publish_content_type": publish_content_type,
            "article_title": title or None,
            "draft_content_preview": content[:80],
            "draft_generation": generated,
            "result": parsed if isinstance(parsed, dict) else {"stdout": command_result.get("stdout"), "stderr": command_result.get("stderr")},
        }

    return {
        "connector": connector_name,
        "executor_name": connector_name,
        "executor_adapter": executor_adapter,
        "executor_root_dir": executor_root_dir,
        "channel": "toutiao",
        "validation_outcome": "probe_failed",
        "message": trim_candidate_text(str(combined or "头条草稿发布失败")),
        "ops_dir": command_result.get("ops_dir"),
        "account": account,
        "publish_content_type": publish_content_type,
        "article_title": title or None,
        "draft_content_preview": content[:80],
        "draft_generation": generated,
        "result": parsed if isinstance(parsed, dict) else {"stdout": command_result.get("stdout"), "stderr": command_result.get("stderr")},
    }
