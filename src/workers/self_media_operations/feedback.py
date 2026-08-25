"""
自媒体运营工种 - 互动反馈域。

计划承接:
- 评论采集
- 反馈分类
- 回复建议
- 回复效果观察
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable


def count_external_replies(replies: list[dict] | None, self_username: str) -> int:
    if not isinstance(replies, list):
        return 0
    count = 0
    for item in replies:
        if not isinstance(item, dict):
            continue
        author = str(item.get("author") or "").strip()
        if self_username and author == self_username:
            continue
        if author:
            count += 1
    return count


def build_feedback_followup_observations(
    comments: list[dict],
    tracked_replies: list[dict],
    *,
    self_username: str,
) -> tuple[list[dict], list[dict]]:
    if not isinstance(tracked_replies, list):
        return [], []
    comment_map = {}
    for item in comments:
        if not isinstance(item, dict):
            continue
        comment_id = str(item.get("id") or "").strip()
        if comment_id:
            comment_map[comment_id] = item

    observations: list[dict] = []
    refreshed_tracked: list[dict] = []
    for tracked in tracked_replies[:20]:
        if not isinstance(tracked, dict):
            continue
        comment_id = str(tracked.get("comment_id") or "").strip()
        if not comment_id:
            continue
        current = comment_map.get(comment_id)
        if not isinstance(current, dict):
            refreshed_tracked.append(tracked)
            observations.append({
                "comment_id": comment_id,
                "status": "not_visible",
                "summary": "本轮未再次看到这条已回复评论，继续等待后续观察",
                "article_title": tracked.get("article_title"),
                "author_name": tracked.get("author_name"),
            })
            continue

        current_replies = current.get("replies", []) if isinstance(current.get("replies"), list) else []
        current_reply_count = int(current.get("replyCount") or 0)
        current_digg_count = int(current.get("diggCount") or 0)
        current_external_replies = count_external_replies(current_replies, self_username)
        baseline_reply_count = int(tracked.get("baseline_reply_count") or 0)
        baseline_digg_count = int(tracked.get("baseline_digg_count") or 0)
        baseline_external_replies = int(tracked.get("baseline_external_reply_count") or 0)

        signals: list[str] = []
        if current_external_replies > baseline_external_replies:
            signals.append("出现了新的外部回复")
        if current_digg_count > baseline_digg_count:
            signals.append("评论点赞数有提升")
        expected_self_reply_count = 1 if bool(tracked.get("self_reply_recorded")) else 0
        if current_reply_count > baseline_reply_count + expected_self_reply_count:
            signals.append("评论线程继续增长")

        status = "continued_interaction" if signals else "waiting"
        summary = "；".join(signals) if signals else "已回复，但暂未观察到新的外部互动"
        refreshed = {
            **tracked,
            "last_seen_at": datetime.now().isoformat(),
            "current_reply_count": current_reply_count,
            "current_digg_count": current_digg_count,
            "current_external_reply_count": current_external_replies,
            "observation_status": status,
        }
        refreshed_tracked.append(refreshed)
        observations.append({
            "comment_id": comment_id,
            "status": status,
            "summary": summary,
            "article_title": str(current.get("articleTitle") or tracked.get("article_title") or "").strip(),
            "author_name": str(current.get("author") or tracked.get("author_name") or "").strip(),
            "signals": signals,
        })
    return observations, refreshed_tracked


def classify_feedback_text(text: str) -> tuple[str, list[str]]:
    normalized = str(text or "").strip()
    lowered = normalized.lower()
    if not normalized:
        return "skip", ["没有拿到有效反馈文本"]
    praise_tokens = ["支持", "喜欢", "不错", "赞", "厉害", "写得好"]
    question_tokens = ["?", "？", "怎么", "为什么", "啥", "是否", "能不能"]
    attack_tokens = ["垃圾", "胡说", "骗人", "滚", "傻", "有病"]
    request_tokens = ["求", "想看", "希望", "建议", "能讲讲", "展开说说"]
    discussion_tokens = ["我觉得", "感觉", "其实", "确实", "同意", "不太认同", "有道理"]

    reasons: list[str] = []
    if any(token in normalized for token in attack_tokens) or any(token in lowered for token in attack_tokens):
        reasons.append("检测到强负面/攻击性词汇")
        return "skip", reasons
    if any(token in normalized for token in question_tokens):
        reasons.append("检测到提问语气或问号")
        return "worth_content", reasons
    if any(token in normalized for token in request_tokens):
        reasons.append("检测到内容请求或选题建议")
        return "worth_content", reasons
    if any(token in normalized for token in praise_tokens):
        reasons.append("检测到明显正向评价")
        return "worth_greeting", reasons
    if any(token in normalized for token in discussion_tokens):
        reasons.append("检测到普通讨论或轻观点表达")
        return "worth_follow", reasons
    reasons.append("默认归类为可轻量打招呼的讨论")
    return "worth_greeting", reasons


def build_feedback_reply(category: str, text: str, payload: dict) -> dict:
    topic = str(payload.get("topic") or "这个话题").strip()
    category = str(category or "discussion")
    role_reflection_summary = str(payload.get("_role_reflection_summary") or "").strip()
    role_reflection_experiment = str(payload.get("_role_reflection_experiment") or "").strip()
    experiment_hint = f" 我也在验证“{role_reflection_experiment}”这条方向。" if role_reflection_experiment else ""
    if category == "worth_greeting":
        return {
            "reply_needed": True,
            "tone": "light",
            "reply_text": f"这个点挺有意思，我也在继续看 {topic} 这条线，后面有新想法再一起聊。{experiment_hint}".strip(),
            "recommended_actions": [
                "先轻量打招呼，建立存在感",
                "观察对方后续是否继续互动",
            ],
        }
    if category == "worth_follow":
        return {
            "reply_needed": True,
            "tone": "social",
            "reply_text": f"你这个观察我也注意到了，后面我会继续顺着 {topic} 这条线看看，欢迎再聊。{experiment_hint}".strip(),
            "recommended_actions": [
                "把这类讨论记为可跟进话题",
                "如果后续互动增加，再考虑延展成内容",
            ],
        }
    if category == "worth_content":
        action_line = "把这类反馈直接纳入下一轮内容生成"
        if role_reflection_experiment:
            action_line = f"把这类反馈纳入“{role_reflection_experiment}”这轮实验，优先转成下一篇内容"
        return {
            "reply_needed": True,
            "tone": "lead",
            "reply_text": (
                f"这个问题记下来了，后面我会专门围绕 {topic} 再展开讲讲，欢迎继续补充你最关心的点。"
                f"{experiment_hint}"
            ).strip(),
            "recommended_actions": [
                action_line,
                "优先做解释型或延展型内容来承接讨论",
            ],
        }
    skip_reason = "暂不介入，避免无效消耗"
    if role_reflection_summary:
        skip_reason = f"暂不介入，先保持当前岗位判断：{role_reflection_summary}"
    return {
        "reply_needed": False,
        "tone": "skip",
        "reply_text": "",
        "recommended_actions": [
            skip_reason,
            "只在该话题持续发酵时再回头观察",
        ],
    }


def process_toutiao_feedback(payload: dict) -> dict:
    account = str(payload.get("account_id") or "default")
    feedback_text = str(payload.get("feedback_text") or payload.get("comment_text") or "").strip()
    author_name = str(payload.get("author_name") or "用户").strip()
    role_reflection_summary = str(payload.get("_role_reflection_summary") or "").strip()
    role_reflection_experiment = str(payload.get("_role_reflection_experiment") or "").strip()
    category, reasons = classify_feedback_text(feedback_text)
    reply = build_feedback_reply(category, feedback_text, payload)
    insight_summary = f"{author_name} 的反馈被识别为 {category}"
    if role_reflection_experiment:
        insight_summary += f"，将优先纳入岗位实验：{role_reflection_experiment}"
    feedback_summary = {
        "category": category,
        "reasons": reasons,
        "author_name": author_name,
        "feedback_text": feedback_text,
        "reply_needed": reply.get("reply_needed"),
        "reply_text": reply.get("reply_text"),
        "tone": reply.get("tone"),
        "recommended_actions": reply.get("recommended_actions", []),
        "role_reflection_summary": role_reflection_summary,
        "role_reflection_experiment": role_reflection_experiment,
        "headline": insight_summary,
        "insight_summary": f"{insight_summary}；{('适合轻互动' if reply.get('reply_needed') else '建议略过')}",
    }
    return {
        "connector": "evo_toutiao_executor",
        "channel": "toutiao",
        "validation_outcome": "passed",
        "message": "头条反馈已完成分析",
        "account": account,
        "feedback_summary": feedback_summary,
        "next_actions": feedback_summary.get("recommended_actions", []),
        "reply_preview": reply.get("reply_text"),
    }


def process_toutiao_feedback_collection(
    workspace: Path,
    tenant_id: str,
    payload: dict,
    *,
    run_comment_list: Callable[[Path, dict], dict],
    run_comment_reply: Callable[[Path, dict], dict],
    get_account_identity: Callable[[Path, str], dict],
) -> dict:
    account = str(payload.get("account_id") or "default")
    collect_result = run_comment_list(workspace, payload)
    if str(collect_result.get("validation_outcome") or "") != "passed":
        return collect_result

    parsed = collect_result.get("result", {}) if isinstance(collect_result.get("result"), dict) else {}
    comments = parsed.get("comments", []) if isinstance(parsed.get("comments"), list) else []
    account_identity = get_account_identity(workspace, account)
    self_username = str(account_identity.get("username") or "").strip()
    self_user_id = str(account_identity.get("user_id") or "").strip()
    max_comments = max(1, min(int(payload.get("max_comments") or 8), 20))
    auto_reply = bool(payload.get("auto_reply_feedback", False))
    reply_limit = max(0, min(int(payload.get("reply_limit") or 2), 5))
    topic = str(payload.get("topic") or "这个话题").strip()
    role_reflection_summary = str(payload.get("_role_reflection_summary") or "").strip()
    role_reflection_experiment = str(payload.get("_role_reflection_experiment") or "").strip()
    tracked_replies = payload.get("_tracked_replies", []) if isinstance(payload.get("_tracked_replies"), list) else []
    selected_feedback: list[dict] = []
    category_counts = {
        "worth_content": 0,
        "worth_follow": 0,
        "worth_greeting": 0,
        "skip": 0,
    }
    replied_items: list[dict] = []
    skipped_replied = 0
    skipped_self_authored = 0
    scanned_comments = comments[:max_comments]
    followup_observations, refreshed_tracked_replies = build_feedback_followup_observations(
        scanned_comments,
        tracked_replies,
        self_username=self_username,
    )
    tracked_ids = {
        str(item.get("comment_id") or "").strip()
        for item in refreshed_tracked_replies
        if isinstance(item, dict)
    }
    for comment in scanned_comments:
        if not isinstance(comment, dict):
            continue
        author_name = str(comment.get("author") or "用户").strip()
        author_id = str(comment.get("authorId") or "").strip()
        if (self_user_id and author_id == self_user_id) or (self_username and author_name == self_username):
            skipped_self_authored += 1
            continue
        content = str(comment.get("content") or "").strip()
        if not content:
            continue
        replies = comment.get("replies", []) if isinstance(comment.get("replies"), list) else []
        already_replied = bool(replies)
        if already_replied:
            skipped_replied += 1
        category, reasons = classify_feedback_text(content)
        category_counts[category] = category_counts.get(category, 0) + 1
        reply = build_feedback_reply(category, content, {
            **payload,
            "topic": topic,
        })
        entry = {
            "comment_id": str(comment.get("id") or "").strip(),
            "author_name": author_name,
            "feedback_text": content,
            "article_title": str(comment.get("articleTitle") or "").strip(),
            "time": str(comment.get("time") or "").strip(),
            "digg_count": int(comment.get("diggCount") or 0),
            "reply_count": int(comment.get("replyCount") or 0),
            "external_reply_count": count_external_replies(replies, self_username),
            "category": category,
            "reasons": reasons,
            "reply_needed": reply.get("reply_needed"),
            "reply_text": reply.get("reply_text"),
            "tone": reply.get("tone"),
            "already_replied": already_replied,
        }
        if category != "skip":
            selected_feedback.append(entry)
        if auto_reply and reply_limit > len(replied_items) and reply.get("reply_needed") and not already_replied and entry["comment_id"]:
            reply_result = run_comment_reply(workspace, {
                "account_id": account,
                "comment_id": entry["comment_id"],
                "content": str(reply.get("reply_text") or ""),
            })
            entry["reply_execution"] = reply_result.get("result")
            entry["reply_status"] = reply_result.get("validation_outcome")
            if str(reply_result.get("validation_outcome") or "") == "passed":
                replied_items.append({
                    "comment_id": entry["comment_id"],
                    "author_name": entry["author_name"],
                    "article_title": entry["article_title"],
                    "feedback_text": entry["feedback_text"],
                    "category": entry["category"],
                    "reply_text": entry["reply_text"],
                    "baseline_reply_count": entry["reply_count"],
                    "baseline_digg_count": entry["digg_count"],
                    "baseline_external_reply_count": entry["external_reply_count"],
                    "self_reply_recorded": True,
                    "tracked_at": datetime.now().isoformat(),
                })
                if entry["comment_id"] not in tracked_ids:
                    refreshed_tracked_replies.append(dict(replied_items[-1]))
                    tracked_ids.add(entry["comment_id"])

    focus_feedback = [
        item for item in selected_feedback
        if str(item.get("category") or "") in {"worth_content", "worth_follow", "worth_greeting"}
    ]
    recommended_actions: list[str] = []
    if category_counts.get("worth_content", 0):
        recommended_actions.append(
            f"优先把评论里的具体疑问承接成下一轮解释型内容"
            + (f"，并验证“{role_reflection_experiment}”是否更有效" if role_reflection_experiment else "")
        )
    if category_counts.get("worth_follow", 0):
        recommended_actions.append("围绕有讨论势头的话题做一条轻互动延展内容")
    if category_counts.get("worth_greeting", 0):
        recommended_actions.append("保持轻量互动频率，先建立账号存在感")
    if not recommended_actions:
        recommended_actions.append("当前暂无高价值评论，继续观察下一轮互动数据")
    if auto_reply:
        recommended_actions.append("已对部分高价值评论自动回复，继续观察后续互动变化")
    continued_observations = [
        item for item in followup_observations
        if isinstance(item, dict) and str(item.get("status") or "") == "continued_interaction"
    ]
    if continued_observations:
        recommended_actions.insert(0, "优先跟进已被激活的评论线程，看看能否继续放大成下一轮内容")
    elif refreshed_tracked_replies:
        recommended_actions.append("继续观察已回复评论是否出现新的外部互动，再决定是否升级为重点选题")
    insight_summary = (
        f"本轮采集 {len(scanned_comments)} 条评论，"
        f"可承接内容 {category_counts.get('worth_content', 0)} 条，"
        f"可继续讨论 {category_counts.get('worth_follow', 0)} 条，"
        f"轻互动 {category_counts.get('worth_greeting', 0)} 条"
    )
    if continued_observations:
        insight_summary += f"，已观察到 {len(continued_observations)} 条回复后继续发酵"
    if role_reflection_summary:
        insight_summary += f"；当前岗位判断 {role_reflection_summary}"
    feedback_collection = {
        "headline": insight_summary,
        "insight_summary": insight_summary + (f"；已自动回复 {len(replied_items)} 条" if replied_items else ""),
        "selected_feedback": focus_feedback[:6],
        "category_counts": category_counts,
        "replied_items": replied_items,
        "followup_observations": followup_observations[:6],
        "updated_tracked_replies": refreshed_tracked_replies[:12],
        "scanned_count": len(scanned_comments),
        "skipped_replied_count": skipped_replied,
        "skipped_self_authored_count": skipped_self_authored,
        "auto_reply_enabled": auto_reply,
        "role_reflection_summary": role_reflection_summary,
        "role_reflection_experiment": role_reflection_experiment,
        "recommended_actions": recommended_actions[:4],
    }
    return {
        "connector": "evo_toutiao_executor",
        "channel": "toutiao",
        "validation_outcome": "passed",
        "message": "头条评论采集与分析完成",
        "account": account,
        "feedback_collection": feedback_collection,
        "next_actions": feedback_collection.get("recommended_actions", []),
    }
