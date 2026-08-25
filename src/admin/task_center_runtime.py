"""正式任务中心：任务与建议的 upsert 工具。"""

from __future__ import annotations


def upsert_task(task_center: dict, payload: dict) -> dict:
    items = task_center.get("items")
    if not isinstance(items, list):
        items = []
        task_center["items"] = items
    task_id = str(payload.get("task_id") or "").strip()
    existing = next(
        (item for item in items if isinstance(item, dict) and str(item.get("task_id") or "").strip() == task_id),
        None,
    )
    if existing is None:
        existing = {}
        items.append(existing)
    existing.update(payload)
    task_center["items"] = items[-80:]
    return existing


def upsert_task_recommendation(task_center: dict, payload: dict) -> dict:
    recommendations = task_center.get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = []
        task_center["recommendations"] = recommendations
    recommendation_id = str(payload.get("recommendation_id") or "").strip()
    existing = next(
        (
            item for item in recommendations
            if isinstance(item, dict) and str(item.get("recommendation_id") or "").strip() == recommendation_id
        ),
        None,
    )
    if existing is None:
        existing = {}
        recommendations.append(existing)
    existing.update(payload)
    task_center["recommendations"] = recommendations[-80:]
    return existing


def has_open_formal_task(task_center: dict, member_id: str, *, exclude_task_id: str | None = None) -> bool:
    items = task_center.get("items")
    if not isinstance(items, list):
        return False
    excluded = str(exclude_task_id or "").strip()
    normalized_member_id = str(member_id or "").strip()
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("member_id") or "").strip() != normalized_member_id:
            continue
        if excluded and str(item.get("task_id") or "").strip() == excluded:
            continue
        if str(item.get("status") or "").strip() != "approved":
            return True
    return False


def has_suggested_recommendation(
    task_center: dict,
    member_id: str,
    *,
    sources: set[str] | None = None,
) -> bool:
    recommendations = task_center.get("recommendations")
    if not isinstance(recommendations, list):
        return False
    normalized_member_id = str(member_id or "").strip()
    for item in recommendations:
        if not isinstance(item, dict):
            continue
        if str(item.get("member_id") or "").strip() != normalized_member_id:
            continue
        if str(item.get("status") or "").strip() != "suggested":
            continue
        if sources:
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            source = str(metadata.get("source") or "").strip()
            if source not in sources:
                continue
        return True
    return False
