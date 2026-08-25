"""
经营财务最小模型（M1）：按项目/周期落盘，供 Admin 财务节点与项目卡片读取。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from work_types import get_work_type

PRESET_FINANCE_PROJECT_IDS = frozenset({"toutiao_default", "default", "test"})


FINANCE_DECISION_ACTIONS = frozenset({"continue_invest", "shrink", "adjust_strategy"})


def finance_decisions_path(workspace: Path) -> Path:
    path = finance_store_dir(workspace) / "decisions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_finance_decisions(workspace: Path) -> list[dict]:
    path = finance_decisions_path(workspace)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def save_finance_decisions(workspace: Path, items: list[dict]) -> list[dict]:
    path = finance_decisions_path(workspace)
    normalized = sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    path.write_text(
        json.dumps({"items": normalized, "updated_at": datetime.now().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized


def record_finance_decision(
    workspace: Path,
    *,
    project_id: str,
    action: str,
    note: str = "",
    period: str | None = None,
) -> dict:
    normalized_action = str(action or "").strip()
    if normalized_action not in FINANCE_DECISION_ACTIONS:
        raise ValueError(f"unsupported action: {action}")
    safe_project = str(project_id or "").strip()
    if not safe_project:
        raise ValueError("project_id is required")
    summary = get_finance_summary(workspace, project_id=safe_project, period=period)
    entry = {
        "id": f"decision_{int(datetime.now().timestamp() * 1000)}",
        "project_id": safe_project,
        "period": str(summary.get("period") or _period_key(period)),
        "action": normalized_action,
        "note": str(note or "").strip(),
        "verdict": str(summary.get("verdict") or "unknown"),
        "net": _safe_float(summary.get("net")),
        "revenue": _safe_float(summary.get("revenue")),
        "cost": _safe_float(summary.get("cost")),
        "created_at": datetime.now().isoformat(),
    }
    items = load_finance_decisions(workspace)
    items.insert(0, entry)
    save_finance_decisions(workspace, items[:200])
    return entry


def finance_store_dir(workspace: Path) -> Path:
    path = workspace / ".admin" / "finance"
    path.mkdir(parents=True, exist_ok=True)
    return path


def finance_record_path(workspace: Path, project_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in (project_id or "default"))
    return finance_store_dir(workspace) / f"{safe}.json"


def _period_key(value: str | None = None) -> str:
    raw = str(value or "").strip()
    if raw:
        return raw[:10]
    return datetime.now().strftime("%Y-%m-%d")


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_views_metric(text: object) -> float:
    raw = str(text or "").strip().replace(",", "")
    if not raw or raw == "--":
        return 0.0
    multiplier = 1.0
    if raw.endswith("万"):
        multiplier = 10000.0
        raw = raw[:-1]
    elif raw.endswith("千"):
        multiplier = 1000.0
        raw = raw[:-1]
    try:
        return float(raw) * multiplier
    except ValueError:
        return 0.0


def compute_verdict(revenue: float, cost: float) -> str:
    net = revenue - cost
    if revenue <= 0 and cost <= 0:
        return "unknown"
    if net > 0:
        return "profitable"
    if net == 0:
        return "break_even"
    return "loss"


def build_finance_summary(record: dict | None, *, project_id: str, period: str) -> dict:
    payload = record if isinstance(record, dict) else {}
    revenue = _safe_float(payload.get("revenue"))
    cost = _safe_float(payload.get("cost"))
    views = _safe_float(payload.get("views"))
    likes = _safe_float(payload.get("likes"))
    comments = _safe_float(payload.get("comments"))
    net = round(revenue - cost, 2)
    verdict = str(payload.get("verdict") or compute_verdict(revenue, cost))
    return {
        "project_id": project_id,
        "channel": str(payload.get("channel") or "toutiao"),
        "period": period,
        "revenue": round(revenue, 2),
        "cost": round(cost, 2),
        "views": int(views),
        "likes": int(likes),
        "comments": int(comments),
        "net": net,
        "verdict": verdict,
        "updated_at": str(payload.get("updated_at") or ""),
        "source": str(payload.get("source") or ""),
        "headline": str(payload.get("headline") or ""),
    }


def load_finance_project(workspace: Path, project_id: str) -> dict:
    path = finance_record_path(workspace, project_id)
    if not path.is_file():
        return {"project_id": project_id, "periods": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    periods = payload.get("periods")
    if not isinstance(periods, dict):
        periods = {}
    return {
        "project_id": str(payload.get("project_id") or project_id),
        "periods": periods,
    }


def save_finance_project(workspace: Path, project_id: str, payload: dict) -> dict:
    path = finance_record_path(workspace, project_id)
    normalized = {
        "project_id": project_id,
        "periods": payload.get("periods") if isinstance(payload.get("periods"), dict) else {},
        "updated_at": datetime.now().isoformat(),
    }
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def empty_finance_summary(*, project_id: str = "") -> dict:
    return {
        "project_id": project_id,
        "channel": "",
        "period": _period_key(),
        "revenue": 0.0,
        "cost": 0.0,
        "views": 0,
        "likes": 0,
        "comments": 0,
        "net": 0.0,
        "verdict": "unknown",
        "updated_at": "",
        "source": "",
        "headline": "",
    }


def purge_preset_finance_data(workspace: Path) -> list[str]:
    """删除历史预置/测试财务项目文件，保持 workspace 干净。"""
    removed: list[str] = []
    root = finance_store_dir(workspace)
    for project_id in PRESET_FINANCE_PROJECT_IDS:
        path = finance_record_path(workspace, project_id)
        if path.is_file():
            path.unlink()
            removed.append(project_id)
    for path in list(root.glob("*.json")):
        stem = path.stem
        if stem.startswith("self_media_") or stem in PRESET_FINANCE_PROJECT_IDS:
            path.unlink()
            if stem not in removed:
                removed.append(stem)
    return removed


def resolve_project_id(
    payload: dict | None,
    *,
    tenant_id: str = "default",
    channel: str = "toutiao",
    workspace: Path | None = None,
) -> str:
    data = payload if isinstance(payload, dict) else {}
    explicit = str(data.get("project_id") or data.get("business_project_id") or "").strip()
    if explicit and explicit not in PRESET_FINANCE_PROJECT_IDS:
        return explicit

    job_id = str(data.get("job_id") or data.get("work_type_id") or "").strip()
    if job_id and job_id not in PRESET_FINANCE_PROJECT_IDS and isinstance(workspace, Path):
        work_type = get_work_type(workspace, job_id)
        if isinstance(work_type, dict):
            configured = str(work_type.get("finance_project_id") or "").strip()
            if configured and configured not in PRESET_FINANCE_PROJECT_IDS:
                return configured
        return job_id

    member_id = str(data.get("member_id") or "").strip()
    if member_id and member_id not in PRESET_FINANCE_PROJECT_IDS:
        return f"member_{member_id}"

    account = str(data.get("account_id") or "").strip()
    if account and account not in {"default", "test"}:
        return f"{channel}_{account}" if channel else account

    return ""


def upsert_finance_period(
    workspace: Path,
    *,
    project_id: str,
    period: str | None = None,
    channel: str = "toutiao",
    patch: dict[str, Any],
) -> dict:
    store = load_finance_project(workspace, project_id)
    periods: dict[str, dict] = store["periods"]
    key = _period_key(period)
    current = periods.get(key, {}) if isinstance(periods.get(key), dict) else {}
    merged = {
        **current,
        **{k: v for k, v in patch.items() if v is not None},
        "project_id": project_id,
        "channel": channel,
        "period": key,
        "updated_at": datetime.now().isoformat(),
    }
    revenue = _safe_float(merged.get("revenue"))
    cost = _safe_float(merged.get("cost"))
    merged["net"] = round(revenue - cost, 2)
    merged["verdict"] = compute_verdict(revenue, cost)
    periods[key] = merged
    save_finance_project(workspace, project_id, {"periods": periods})
    return build_finance_summary(merged, project_id=project_id, period=key)


def upsert_finance_from_analytics(
    workspace: Path,
    *,
    tenant_id: str,
    payload: dict,
    result: dict,
    analytics_summary: dict | None = None,
) -> dict | None:
    if not isinstance(result, dict):
        return None
    channel = str(result.get("channel") or payload.get("channel") or "toutiao").strip().lower()
    if channel != "toutiao":
        return None
    analytics_type = str(
        result.get("analytics_type")
        or payload.get("analytics_type")
        or ""
    ).strip().lower()
    if analytics_type not in {"works", "income", "fans"}:
        return None

    project_id = resolve_project_id(payload, tenant_id=tenant_id, channel=channel, workspace=workspace)
    if not project_id:
        return None
    summary = analytics_summary if isinstance(analytics_summary, dict) else {}
    structured = summary.get("structured", {}) if isinstance(summary.get("structured"), dict) else {}
    patch: dict[str, Any] = {
        "source": f"operation_analytics:{analytics_type}",
        "headline": str(summary.get("headline") or result.get("message") or "").strip(),
    }

    if analytics_type == "income":
        patch["revenue"] = _safe_float(structured.get("total_income"))
        if patch["revenue"] <= 0:
            patch["revenue"] = _safe_float(structured.get("withdraw_total"))
    elif analytics_type == "works":
        patch["views"] = _parse_views_metric(structured.get("views"))
        patch["likes"] = _parse_views_metric(structured.get("likes"))
        patch["comments"] = _parse_views_metric(structured.get("comments"))
    else:
        metrics = result.get("result", {}) if isinstance(result.get("result"), dict) else {}
        metric_values = metrics.get("metrics", {}) if isinstance(metrics.get("metrics"), dict) else {}
        patch["views"] = _parse_views_metric(metric_values.get("总粉丝") or metric_values.get("粉丝总数"))

    return upsert_finance_period(
        workspace,
        project_id=project_id,
        channel=channel,
        patch=patch,
    )


def get_finance_summary(
    workspace: Path,
    *,
    project_id: str,
    period: str | None = None,
) -> dict:
    store = load_finance_project(workspace, project_id)
    periods: dict[str, dict] = store["periods"]
    key = _period_key(period)
    if key in periods:
        return build_finance_summary(periods[key], project_id=project_id, period=key)

    latest_key = sorted(periods.keys(), reverse=True)[0] if periods else key
    latest = periods.get(latest_key, {}) if periods else {}
    summary = build_finance_summary(latest, project_id=project_id, period=latest_key)
    summary["is_latest_period"] = bool(periods) and latest_key != key
    return summary


def _list_finance_project_ids(workspace: Path) -> list[str]:
    root = finance_store_dir(workspace)
    return sorted(
        path.stem
        for path in root.glob("*.json")
        if path.stem not in PRESET_FINANCE_PROJECT_IDS
    )


def list_finance_projects(workspace: Path) -> list[str]:
    purge_preset_finance_data(workspace)
    return _list_finance_project_ids(workspace)


def get_finance_trends(workspace: Path, project_id: str, *, limit: int = 7) -> list[dict]:
    store = load_finance_project(workspace, project_id)
    periods: dict[str, dict] = store["periods"]
    keys = sorted(periods.keys(), reverse=True)[: max(1, int(limit))]
    series: list[dict] = []
    for key in reversed(keys):
        record = periods.get(key, {}) if isinstance(periods.get(key), dict) else {}
        series.append(build_finance_summary(record, project_id=project_id, period=key))
    return series


def build_commercial_verdict(
    *,
    primary: dict,
    trends: list[dict],
    latest_decision: dict | None,
) -> dict:
    has_data = bool(str(primary.get("updated_at") or "").strip())
    if not has_data:
        return {
            "headline": "还没有经营数据，暂无法给出商业化结论",
            "recommendation": "wait_for_data",
            "recommendation_label": "先跑通工种任务",
            "confidence": "low",
            "reasons": ["需至少完成一次带 analytics 的正式任务"],
            "next_actions": [
                "公司设置添加工种并启用执行器",
                "育成师建档并派首个正式任务",
                "员工执行提交后查看财务落盘",
            ],
            "score": 0,
        }

    net = _safe_float(primary.get("net"))
    revenue = _safe_float(primary.get("revenue"))
    cost = _safe_float(primary.get("cost"))
    views = _safe_float(primary.get("views"))
    verdict = str(primary.get("verdict") or compute_verdict(revenue, cost))
    reasons: list[str] = []
    next_actions: list[str] = []

    if verdict == "profitable":
        recommendation = "continue_invest"
        recommendation_label = "建议继续投入"
        headline = f"主项目净收益 ¥{net:.2f}，当前判断为盈利，可加大内容与投放试错。"
    elif verdict == "loss":
        recommendation = "shrink"
        recommendation_label = "建议收缩或调整"
        headline = f"净收益 ¥{net:.2f}，成本高于收入，建议收缩投入或调整工种策略。"
        reasons.append("收入未能覆盖已录入成本")
    elif verdict == "break_even":
        recommendation = "adjust_strategy"
        recommendation_label = "建议小幅试错"
        headline = "收支持平，建议先优化内容与转化，再决定是否加仓。"
    elif revenue <= 0 and views > 0:
        recommendation = "adjust_strategy"
        recommendation_label = "建议优化变现路径"
        headline = "已有阅读/互动但收入偏弱，优先优化选题与变现动作。"
        reasons.append("流量指标有数据，但收入尚未形成")
    else:
        recommendation = "adjust_strategy"
        recommendation_label = "建议补齐经营数据"
        headline = "收入与成本数据不完整，请补录成本或等待 analytics 落盘后再决策。"
        reasons.append("当前 verdict 为待评估")

    if len(trends) >= 2:
        prev_net = _safe_float(trends[-2].get("net"))
        if net > prev_net:
            reasons.append(f"净收益较上周期提升 ¥{round(net - prev_net, 2)}")
        elif net < prev_net:
            reasons.append(f"净收益较上周期下降 ¥{round(prev_net - net, 2)}")

    if cost <= 0:
        next_actions.append("在财务页补录本期成本（工具、投放、人力分摊）")
        if recommendation == "continue_invest":
            recommendation = "adjust_strategy"
            recommendation_label = "建议先补成本再决策"

    if not latest_decision:
        next_actions.append("记录一条经营决策：继续投入 / 调整策略 / 收缩投入")

    if latest_decision:
        action = str(latest_decision.get("action") or "")
        if action == "continue_invest":
            reasons.append("你已记录「继续投入」决策")
        elif action == "shrink":
            reasons.append("你已记录「收缩投入」决策")
        elif action == "adjust_strategy":
            reasons.append("你已记录「调整策略」决策")

    confidence = "high" if revenue > 0 and cost > 0 and verdict in {"profitable", "loss", "break_even"} else "medium"
    if revenue <= 0 and views <= 0:
        confidence = "low"

    score = 35
    if revenue > 0:
        score += 25
    if cost > 0:
        score += 15
    if verdict in {"profitable", "break_even", "loss"}:
        score += 15
    if latest_decision:
        score += 10
    if len(trends) >= 2:
        score += 10
    score = min(100, score)

    return {
        "headline": headline,
        "recommendation": recommendation,
        "recommendation_label": recommendation_label,
        "confidence": confidence,
        "reasons": reasons,
        "next_actions": next_actions,
        "score": score,
        "primary_verdict": verdict,
        "primary_net": round(net, 2),
    }


def get_finance_overview(workspace: Path, *, period: str | None = None) -> dict:
    purge_preset_finance_data(workspace)
    project_ids = _list_finance_project_ids(workspace)
    items = [
        get_finance_summary(workspace, project_id=project_id, period=period)
        for project_id in project_ids
    ]
    items = [item for item in items if str(item.get("updated_at") or "").strip()]
    primary = empty_finance_summary()
    if items:
        primary = sorted(items, key=lambda item: str(item.get("updated_at") or ""), reverse=True)[0]
    decisions = load_finance_decisions(workspace)
    latest_decision = decisions[0] if decisions else None
    trends: list[dict] = []
    commercial_verdict = build_commercial_verdict(
        primary=primary,
        trends=[],
        latest_decision=latest_decision if isinstance(latest_decision, dict) else None,
    )
    if str(primary.get("project_id") or "").strip():
        trends = get_finance_trends(workspace, str(primary.get("project_id")))
        commercial_verdict = build_commercial_verdict(
            primary=primary,
            trends=trends,
            latest_decision=latest_decision if isinstance(latest_decision, dict) else None,
        )
    return {
        "project_ids": project_ids,
        "items": items,
        "primary": primary,
        "total": len(items),
        "decisions": decisions[:20],
        "latest_decision": latest_decision,
        "trends": trends,
        "commercial_verdict": commercial_verdict,
    }
