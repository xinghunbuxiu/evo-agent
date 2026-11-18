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


def adopt_worker_growth_recommendation(
    task_center: dict,
    *,
    recommendation_id: str,
    member_id: str,
    assigned_by_member_id: str = "talent_development_officer",
    now: str,
) -> dict:
    """Adopt one Talent Center worker-growth recommendation as an assigned Learning Task.

    The recommendation is the source of truth for task content. Adoption is
    tenant-runtime scoped by the caller, deterministic, and never dispatches
    work. Repeated requests return the same task without mutating its lifecycle.
    """
    normalized_id = str(recommendation_id or "").strip()
    normalized_member_id = str(member_id or "").strip()
    if not normalized_id or not normalized_member_id:
        raise ValueError("recommendation_id and member_id are required")
    recommendations = task_center.get("recommendations")
    if not isinstance(recommendations, list):
        raise ValueError("recommendation was not found")
    recommendation = next(
        (
            item for item in recommendations
            if isinstance(item, dict)
            and str(item.get("recommendation_id") or "").strip() == normalized_id
        ),
        None,
    )
    if not isinstance(recommendation, dict):
        raise ValueError("recommendation was not found")
    metadata = recommendation.get("metadata") if isinstance(recommendation.get("metadata"), dict) else {}
    if metadata.get("source") != "talent_center_worker_growth":
        raise ValueError("recommendation is not a worker-growth recommendation")
    if str(recommendation.get("member_id") or "").strip() != normalized_member_id:
        raise ValueError("recommendation member does not match the requested employee")

    task_id = f"learning:{normalized_id}"
    items = task_center.get("items")
    if not isinstance(items, list):
        items = []
        task_center["items"] = items
    existing = next(
        (
            item for item in items
            if isinstance(item, dict)
            and (
                str(item.get("task_id") or "").strip() == task_id
                or (
                    isinstance(item.get("metadata"), dict)
                    and str(item["metadata"].get("recommendation_id") or "").strip() == normalized_id
                )
            )
        ),
        None,
    )
    status = str(recommendation.get("status") or "suggested").strip()
    if status == "adopted":
        if not isinstance(existing, dict):
            raise ValueError("adopted recommendation has no linked Learning Task; manual reconciliation required")
        return {"task": existing, "created": False}
    if status != "suggested":
        raise ValueError("only suggested recommendations can be adopted")
    if isinstance(existing, dict):
        raise ValueError("Learning Task already exists while recommendation is still suggested")

    title = str(recommendation.get("title") or "").strip()
    objective = str(recommendation.get("objective") or "").strip()
    if not title or not objective:
        raise ValueError("worker-growth recommendation is missing task content")
    deliverables = recommendation.get("deliverables")
    deliverable_items = [
        str(value).strip()
        for value in (deliverables if isinstance(deliverables, list) else [])
        if str(value).strip()
    ]
    task = {
        "task_id": task_id,
        "member_id": normalized_member_id,
        "assigned_by_member_id": str(assigned_by_member_id or "talent_development_officer").strip(),
        "title": title,
        "objective": objective,
        "deliverables": deliverable_items,
        "status": "assigned",
        "assigned_at": now,
        "started_at": None,
        "submitted_at": None,
        "approved_at": None,
        "result_summary": None,
        "reflection": None,
        "review_note": None,
        "metadata": {
            "source": "talent_center_worker_growth_adoption",
            "recommendation_id": normalized_id,
            "source_mission_run_id": metadata.get("source_mission_run_id"),
            "source_node_id": metadata.get("source_node_id"),
            "worker_id": metadata.get("worker_id"),
            "training_mode": metadata.get("training_mode"),
            "priority": metadata.get("priority"),
            "failure_reasons": metadata.get("failure_reasons", []),
            "automatic_retry": False,
            "execution_authorized": False,
        },
    }
    items.append(task)
    task_center["items"] = items[-80:]
    recommendation["status"] = "adopted"
    recommendation["adopted_at"] = now
    recommendation["metadata"] = {
        **metadata,
        "adopted_learning_task_id": task_id,
        "adoption_status": "assigned",
    }
    return {"task": task, "created": True}


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
