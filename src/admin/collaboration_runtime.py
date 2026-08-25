"""跨工种协作运行时：配置驱动，不绑定具体工种。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from admin.collaboration_policy_runtime import render_message_template, resolve_collaboration_rule
from admin.runtime_state import normalize_child_members_runtime
from admin.worker_route_runtime import resolve_work_type_id

ORCHESTRATOR_MEMBER_ID = "talent_development_officer"

COLLABORATION_STATUSES = frozenset({
    "open",
    "assigned",
    "provider_submitted",
    "approved",
    "integrated",
    "closed",
    "cancelled",
})

INTEGRATION_PHASES = frozenset({
    "waiting_assignment",
    "waiting_delivery",
    "ready_to_integrate",
    "integrated",
})


def normalize_collaboration_center(payload: dict | None) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    requests = payload.get("requests") if isinstance(payload.get("requests"), list) else []
    assignments = payload.get("assignments") if isinstance(payload.get("assignments"), list) else []
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    normalized_requests: list[dict] = []
    for item in requests:
        if not isinstance(item, dict):
            continue
        request_id = str(item.get("request_id") or "").strip()
        if not request_id:
            continue
        normalized_requests.append({
            "request_id": request_id,
            "requester_member_id": str(item.get("requester_member_id") or "").strip() or None,
            "requester_task_id": str(item.get("requester_task_id") or "").strip() or None,
            "needed_capability": str(item.get("needed_capability") or "").strip() or None,
            "target_work_type_id": str(item.get("target_work_type_id") or "").strip() or None,
            "target_department_id": str(item.get("target_department_id") or "").strip() or None,
            "title": str(item.get("title") or "").strip() or None,
            "description": str(item.get("description") or "").strip() or None,
            "status": str(item.get("status") or "open").strip() or "open",
            "requester_continues": item.get("requester_continues", True) is not False,
            "policy_id": str(item.get("policy_id") or "").strip() or None,
            "deliverable_template_id": str(item.get("deliverable_template_id") or "").strip() or None,
            "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "approved_at": item.get("approved_at"),
            "integrated_at": item.get("integrated_at"),
        })
    normalized_assignments: list[dict] = []
    for item in assignments:
        if not isinstance(item, dict):
            continue
        assignment_id = str(item.get("assignment_id") or "").strip()
        request_id = str(item.get("request_id") or "").strip()
        if not assignment_id or not request_id:
            continue
        normalized_assignments.append({
            "assignment_id": assignment_id,
            "request_id": request_id,
            "provider_member_id": str(item.get("provider_member_id") or "").strip() or None,
            "provider_task_id": str(item.get("provider_task_id") or "").strip() or None,
            "assigned_by": str(item.get("assigned_by") or ORCHESTRATOR_MEMBER_ID).strip() or ORCHESTRATOR_MEMBER_ID,
            "assigned_at": item.get("assigned_at"),
            "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        })
    normalized_events: list[dict] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        normalized_events.append({
            "event_id": str(item.get("event_id") or "").strip() or None,
            "event_type": str(item.get("event_type") or "").strip() or None,
            "request_id": str(item.get("request_id") or "").strip() or None,
            "created_at": item.get("created_at"),
            "payload": item.get("payload") if isinstance(item.get("payload"), dict) else {},
        })
    return {
        "requests": normalized_requests[-120:],
        "assignments": normalized_assignments[-120:],
        "events": normalized_events[-200:],
    }


def _find_member(runtime: dict, member_id: str) -> dict | None:
    members = normalize_child_members_runtime(
        runtime.get("child_members"),
        legacy_child_agent=runtime.get("child_agent") if isinstance(runtime.get("child_agent"), dict) else None,
    )
    target = str(member_id or "").strip()
    if not target:
        return None
    return next(
        (
            item for item in members.get("items", [])
            if isinstance(item, dict) and str(item.get("member_id") or "").strip() == target
        ),
        None,
    )


def _member_display_name(member: dict | None, fallback: str = "成员") -> str:
    if not isinstance(member, dict):
        return fallback
    return str(member.get("name") or member.get("member_id") or fallback).strip() or fallback


def _append_event(center: dict, *, event_type: str, request_id: str, payload: dict | None = None) -> None:
    events = center.get("events")
    if not isinstance(events, list):
        events = []
        center["events"] = events
    now_iso = datetime.now().isoformat()
    events.append({
        "event_id": f"collab_event:{request_id}:{int(datetime.now().timestamp() * 1000)}",
        "event_type": event_type,
        "request_id": request_id,
        "created_at": now_iso,
        "payload": payload if isinstance(payload, dict) else {},
    })
    center["events"] = events[-200:]


def _upsert_request(center: dict, request: dict) -> dict:
    requests = center.get("requests")
    if not isinstance(requests, list):
        requests = []
        center["requests"] = requests
    request_id = str(request.get("request_id") or "").strip()
    existing = next(
        (item for item in requests if isinstance(item, dict) and str(item.get("request_id") or "").strip() == request_id),
        None,
    )
    if existing is None:
        requests.append(request)
    else:
        existing.update(request)
    center["requests"] = requests[-120:]
    return request


def _get_request(center: dict, request_id: str) -> dict | None:
    target = str(request_id or "").strip()
    requests = center.get("requests") if isinstance(center.get("requests"), list) else []
    return next(
        (item for item in requests if isinstance(item, dict) and str(item.get("request_id") or "").strip() == target),
        None,
    )


def _get_assignment_by_request(center: dict, request_id: str) -> dict | None:
    target = str(request_id or "").strip()
    assignments = center.get("assignments") if isinstance(center.get("assignments"), list) else []
    return next(
        (item for item in assignments if isinstance(item, dict) and str(item.get("request_id") or "").strip() == target),
        None,
    )


def _set_task_integration_pending(task: dict, *, request_id: str, phase: str) -> None:
    if not isinstance(task, dict):
        return
    task["integration_pending"] = {
        "collaboration_request_id": request_id,
        "phase": phase if phase in INTEGRATION_PHASES else "waiting_assignment",
        "updated_at": datetime.now().isoformat(),
    }


def create_collaboration_request(
    *,
    workspace: Path,
    runtime: dict,
    requester_member_id: str,
    needed_capability: str,
    title: str,
    description: str = "",
    requester_task_id: str | None = None,
    target_work_type_id: str | None = None,
    target_department_id: str | None = None,
    requester_continues: bool = True,
    policy_id: str | None = None,
    append_relationship_message: Callable[..., None] | None = None,
) -> dict:
    requester = _find_member(runtime, requester_member_id)
    if not requester:
        raise ValueError("请求方员工不存在")
    if str(requester.get("primary_role") or "").strip() == "talent_development":
        raise ValueError("育成师不能作为协作请求方")

    capability = str(needed_capability or "").strip()
    if not capability:
        raise ValueError("needed_capability 必填")
    request_title = str(title or "").strip()
    if not request_title:
        raise ValueError("title 必填")

    resolved = resolve_collaboration_rule(workspace, needed_capability=capability, policy_id=policy_id)
    rule = resolved.get("rule") if isinstance(resolved.get("rule"), dict) else {}
    deliverable_template = resolved.get("deliverable_template") if isinstance(resolved.get("deliverable_template"), dict) else {}
    now_iso = datetime.now().isoformat()
    request_id = f"collab:{requester_member_id}:{int(datetime.now().timestamp() * 1000)}"

    center = runtime.get("collaboration_center") if isinstance(runtime.get("collaboration_center"), dict) else {}
    center = normalize_collaboration_center(center)
    request = {
        "request_id": request_id,
        "requester_member_id": requester_member_id,
        "requester_task_id": str(requester_task_id or "").strip() or None,
        "needed_capability": capability,
        "target_work_type_id": str(target_work_type_id or "").strip() or None,
        "target_department_id": str(
            target_department_id or rule.get("prefer_department_id") or ""
        ).strip() or None,
        "title": request_title,
        "description": str(description or "").strip() or None,
        "status": "open",
        "requester_continues": requester_continues is not False,
        "policy_id": str(resolved.get("policy_id") or "").strip() or None,
        "deliverable_template_id": str(
            rule.get("deliverable_template_id") or deliverable_template.get("template_id") or ""
        ).strip() or None,
        "metadata": {
            "resolve_by": str(rule.get("resolve_by") or "trainer_manual").strip(),
            "reviewer_role": str(rule.get("reviewer_role") or ORCHESTRATOR_MEMBER_ID).strip(),
        },
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    _upsert_request(center, request)
    _append_event(center, event_type="collaboration.created", request_id=request_id, payload={"needed_capability": capability})
    runtime["collaboration_center"] = center

    task_id = str(requester_task_id or "").strip()
    if task_id:
        task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
        items = task_center.get("items") if isinstance(task_center.get("items"), list) else []
        task = next(
            (
                item for item in items
                if isinstance(item, dict)
                and str(item.get("task_id") or "").strip() == task_id
                and str(item.get("member_id") or "").strip() == requester_member_id
            ),
            None,
        )
        if isinstance(task, dict):
            _set_task_integration_pending(task, request_id=request_id, phase="waiting_assignment")
            task_center["items"] = items
            runtime["task_center"] = task_center

    if callable(append_relationship_message):
        relationship_center = runtime.get("relationship_center") if isinstance(runtime.get("relationship_center"), dict) else {}
        threads = relationship_center.get("conversation_threads")
        if not isinstance(threads, list):
            threads = []
            relationship_center["conversation_threads"] = threads
        append_relationship_message(
            relationship_center,
            thread_id=f"collab:{request_id}",
            participants=[requester_member_id, ORCHESTRATOR_MEMBER_ID],
            sender_member_id=requester_member_id,
            sender_role=str(requester.get("primary_role") or "child_agent"),
            message_type="collaboration_request",
            content=str(description or request_title).strip(),
            metadata={
                "collaboration_request_id": request_id,
                "needed_capability": capability,
                "requester_continues": requester_continues is not False,
            },
        )
        notify_template = str(resolved.get("message_template") or "").strip()
        if notify_template:
            orchestrator_message = render_message_template(
                notify_template.replace("交付并通过审核", "待安排").replace("可对接", "待处理"),
                {
                    "needed_capability": capability,
                    "requester_member_name": _member_display_name(requester),
                    "title": request_title,
                    "provider_member_name": "提供方",
                    "deliverable_summary": "",
                },
            )
            append_relationship_message(
                relationship_center,
                thread_id=f"trainer:{ORCHESTRATOR_MEMBER_ID}",
                participants=[ORCHESTRATOR_MEMBER_ID],
                sender_member_id=requester_member_id,
                sender_role=str(requester.get("primary_role") or "child_agent"),
                message_type="collaboration_orchestrator_notice",
                content=orchestrator_message or f"协作请求：{request_title}（{capability}）",
                metadata={"collaboration_request_id": request_id},
            )
        runtime["relationship_center"] = relationship_center

    return request


def assign_collaboration_request(
    *,
    runtime: dict,
    request_id: str,
    provider_member_id: str,
    provider_task_id: str | None = None,
    assigned_by: str = ORCHESTRATOR_MEMBER_ID,
) -> dict:
    center = normalize_collaboration_center(runtime.get("collaboration_center"))
    request = _get_request(center, request_id)
    if not isinstance(request, dict):
        raise ValueError("协作请求不存在")
    if str(request.get("status") or "") not in {"open", "assigned"}:
        raise ValueError(f"当前状态 {request.get('status')} 不可指派")

    provider = _find_member(runtime, provider_member_id)
    if not provider:
        raise ValueError("提供方员工不存在")
    if str(provider.get("primary_role") or "").strip() == "talent_development":
        raise ValueError("育成师不能作为协作提供方")

    now_iso = datetime.now().isoformat()
    assignment_id = f"collab_assign:{request_id}:{int(datetime.now().timestamp() * 1000)}"
    assignment = {
        "assignment_id": assignment_id,
        "request_id": request_id,
        "provider_member_id": provider_member_id,
        "provider_task_id": str(provider_task_id or "").strip() or None,
        "assigned_by": str(assigned_by or ORCHESTRATOR_MEMBER_ID).strip() or ORCHESTRATOR_MEMBER_ID,
        "assigned_at": now_iso,
        "metadata": {
            "provider_work_type_id": resolve_work_type_id(provider),
        },
    }
    assignments = center.get("assignments")
    if not isinstance(assignments, list):
        assignments = []
        center["assignments"] = assignments
    assignments = [item for item in assignments if not (isinstance(item, dict) and str(item.get("request_id") or "") == request_id)]
    assignments.append(assignment)
    center["assignments"] = assignments[-120:]

    request["status"] = "assigned"
    request["updated_at"] = now_iso
    _upsert_request(center, request)
    _append_event(
        center,
        event_type="collaboration.assigned",
        request_id=request_id,
        payload={"provider_member_id": provider_member_id, "provider_task_id": provider_task_id},
    )
    runtime["collaboration_center"] = center

    requester_task_id = str(request.get("requester_task_id") or "").strip()
    requester_member_id = str(request.get("requester_member_id") or "").strip()
    if requester_task_id and requester_member_id:
        task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
        items = task_center.get("items") if isinstance(task_center.get("items"), list) else []
        task = next(
            (
                item for item in items
                if isinstance(item, dict)
                and str(item.get("task_id") or "").strip() == requester_task_id
                and str(item.get("member_id") or "").strip() == requester_member_id
            ),
            None,
        )
        if isinstance(task, dict):
            _set_task_integration_pending(task, request_id=request_id, phase="waiting_delivery")
            runtime["task_center"] = task_center

    if provider_task_id:
        task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
        items = task_center.get("items") if isinstance(task_center.get("items"), list) else []
        provider_task = next(
            (item for item in items if isinstance(item, dict) and str(item.get("task_id") or "").strip() == str(provider_task_id)),
            None,
        )
        if isinstance(provider_task, dict):
            metadata = provider_task.get("metadata") if isinstance(provider_task.get("metadata"), dict) else {}
            provider_task["metadata"] = {
                **metadata,
                "collaboration_request_id": request_id,
                "collaboration_role": "provider",
            }
            runtime["task_center"] = task_center

    return {"request": request, "assignment": assignment}


def list_collaboration_requests(
    runtime: dict,
    *,
    role: str = "orchestrator",
    member_id: str | None = None,
) -> list[dict]:
    center = normalize_collaboration_center(runtime.get("collaboration_center"))
    requests = center.get("requests") if isinstance(center.get("requests"), list) else []
    assignments = center.get("assignments") if isinstance(center.get("assignments"), list) else []
    normalized_role = str(role or "orchestrator").strip().lower()
    target_member = str(member_id or "").strip()

    results: list[dict] = []
    for request in requests:
        if not isinstance(request, dict):
            continue
        request_id = str(request.get("request_id") or "").strip()
        assignment = _get_assignment_by_request(center, request_id)
        enriched = {
            **request,
            "assignment": assignment,
        }
        if normalized_role == "orchestrator":
            results.append(enriched)
            continue
        if normalized_role == "requester":
            if target_member and str(request.get("requester_member_id") or "").strip() == target_member:
                results.append(enriched)
            continue
        if normalized_role == "provider":
            if (
                isinstance(assignment, dict)
                and target_member
                and str(assignment.get("provider_member_id") or "").strip() == target_member
            ):
                results.append(enriched)
    return results


def maybe_mark_provider_collaboration_submitted(*, runtime: dict, task: dict) -> dict | None:
    if not isinstance(task, dict):
        return None
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    request_id = str(metadata.get("collaboration_request_id") or task.get("collaboration_request_id") or "").strip()
    if not request_id:
        task_id = str(task.get("task_id") or "").strip()
        center = normalize_collaboration_center(runtime.get("collaboration_center"))
        assignment = next(
            (
                item for item in center.get("assignments", [])
                if isinstance(item, dict) and str(item.get("provider_task_id") or "").strip() == task_id
            ),
            None,
        )
        if isinstance(assignment, dict):
            request_id = str(assignment.get("request_id") or "").strip()
        else:
            return None
    else:
        center = normalize_collaboration_center(runtime.get("collaboration_center"))

    request = _get_request(center, request_id)
    if not isinstance(request, dict):
        return None
    if str(request.get("status") or "") in {"approved", "integrated", "closed", "cancelled"}:
        return request

    request["status"] = "provider_submitted"
    request["updated_at"] = datetime.now().isoformat()
    _upsert_request(center, request)
    _append_event(center, event_type="collaboration.provider_submitted", request_id=request_id, payload={"task_id": task.get("task_id")})
    runtime["collaboration_center"] = center
    return request


def maybe_finalize_provider_collaboration(
    *,
    workspace: Path,
    runtime: dict,
    task: dict,
    append_relationship_message: Callable[..., None] | None = None,
) -> dict | None:
    if not isinstance(task, dict):
        return None
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    request_id = str(metadata.get("collaboration_request_id") or task.get("collaboration_request_id") or "").strip()
    center = normalize_collaboration_center(runtime.get("collaboration_center"))
    if not request_id:
        task_id = str(task.get("task_id") or "").strip()
        assignment = next(
            (
                item for item in center.get("assignments", [])
                if isinstance(item, dict) and str(item.get("provider_task_id") or "").strip() == task_id
            ),
            None,
        )
        if not isinstance(assignment, dict):
            return None
        request_id = str(assignment.get("request_id") or "").strip()
    request = _get_request(center, request_id)
    if not isinstance(request, dict):
        return None

    assignment = _get_assignment_by_request(center, request_id)
    provider_member_id = str(task.get("member_id") or "").strip()
    if isinstance(assignment, dict):
        expected_provider = str(assignment.get("provider_member_id") or "").strip()
        if expected_provider and provider_member_id and expected_provider != provider_member_id:
            return None
        if not assignment.get("provider_task_id"):
            assignment["provider_task_id"] = str(task.get("task_id") or "").strip() or None

    now_iso = datetime.now().isoformat()
    request["status"] = "approved"
    request["approved_at"] = now_iso
    request["updated_at"] = now_iso
    deliverable_summary = str(task.get("result_summary") or task.get("reflection") or "").strip()
    request_metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    request["metadata"] = {
        **request_metadata,
        "deliverable_summary": deliverable_summary[:500] if deliverable_summary else None,
        "provider_task_id": str(task.get("task_id") or "").strip() or None,
    }
    _upsert_request(center, request)
    _append_event(
        center,
        event_type="collaboration.approved",
        request_id=request_id,
        payload={"provider_task_id": task.get("task_id"), "deliverable_summary": deliverable_summary[:200] if deliverable_summary else None},
    )
    runtime["collaboration_center"] = center

    requester_member_id = str(request.get("requester_member_id") or "").strip()
    requester_task_id = str(request.get("requester_task_id") or "").strip()
    if requester_task_id and requester_member_id:
        task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
        items = task_center.get("items") if isinstance(task_center.get("items"), list) else []
        requester_task = next(
            (
                item for item in items
                if isinstance(item, dict)
                and str(item.get("task_id") or "").strip() == requester_task_id
                and str(item.get("member_id") or "").strip() == requester_member_id
            ),
            None,
        )
        if isinstance(requester_task, dict):
            _set_task_integration_pending(requester_task, request_id=request_id, phase="ready_to_integrate")
            pending = requester_task.get("integration_pending") if isinstance(requester_task.get("integration_pending"), dict) else {}
            requester_task["integration_pending"] = {
                **pending,
                "ready_at": now_iso,
                "deliverable_summary": deliverable_summary[:500] if deliverable_summary else None,
            }
            runtime["task_center"] = task_center

    if callable(append_relationship_message) and requester_member_id:
        resolved = resolve_collaboration_rule(
            workspace,
            needed_capability=str(request.get("needed_capability") or "").strip(),
            policy_id=str(request.get("policy_id") or "").strip() or None,
        )
        rule = resolved.get("rule") if isinstance(resolved.get("rule"), dict) else {}
        notify_targets = rule.get("notify_on_approved") if isinstance(rule.get("notify_on_approved"), list) else ["requester"]
        provider = _find_member(runtime, provider_member_id)
        requester = _find_member(runtime, requester_member_id)
        message = render_message_template(
            str(resolved.get("message_template") or "").strip()
            or "所需能力 {{needed_capability}} 已就绪，请在本任务当前阶段收尾后对接。",
            {
                "needed_capability": str(request.get("needed_capability") or "").strip(),
                "requester_member_name": _member_display_name(requester),
                "provider_member_name": _member_display_name(provider, "提供方"),
                "title": str(request.get("title") or "").strip(),
                "deliverable_summary": deliverable_summary[:300] if deliverable_summary else "",
            },
        )
        relationship_center = runtime.get("relationship_center") if isinstance(runtime.get("relationship_center"), dict) else {}
        if "requester" in notify_targets:
            append_relationship_message(
                relationship_center,
                thread_id=f"trainer:{requester_member_id}",
                participants=[ORCHESTRATOR_MEMBER_ID, requester_member_id],
                sender_member_id=ORCHESTRATOR_MEMBER_ID,
                sender_role="talent_development",
                message_type="collaboration_ready",
                content=message,
                metadata={
                    "collaboration_request_id": request_id,
                    "needed_capability": request.get("needed_capability"),
                    "integration_phase": "ready_to_integrate",
                },
            )
            append_relationship_message(
                relationship_center,
                thread_id=f"collab:{request_id}",
                participants=[requester_member_id, ORCHESTRATOR_MEMBER_ID],
                sender_member_id=ORCHESTRATOR_MEMBER_ID,
                sender_role="talent_development",
                message_type="collaboration_ready",
                content=message,
                metadata={"collaboration_request_id": request_id},
            )
        runtime["relationship_center"] = relationship_center

    return request


def mark_collaboration_integrated(*, runtime: dict, request_id: str, member_id: str) -> dict:
    center = normalize_collaboration_center(runtime.get("collaboration_center"))
    request = _get_request(center, request_id)
    if not isinstance(request, dict):
        raise ValueError("协作请求不存在")
    if str(request.get("requester_member_id") or "").strip() != str(member_id or "").strip():
        raise ValueError("仅请求方可标记已对接")
    if str(request.get("status") or "") not in {"approved", "integrated"}:
        raise ValueError("协作尚未进入可对接状态")

    now_iso = datetime.now().isoformat()
    request["status"] = "integrated"
    request["integrated_at"] = now_iso
    request["updated_at"] = now_iso
    _upsert_request(center, request)
    _append_event(center, event_type="collaboration.integrated", request_id=request_id, payload={})
    runtime["collaboration_center"] = center

    requester_task_id = str(request.get("requester_task_id") or "").strip()
    if requester_task_id:
        task_center = runtime.get("task_center") if isinstance(runtime.get("task_center"), dict) else {}
        items = task_center.get("items") if isinstance(task_center.get("items"), list) else []
        task = next(
            (
                item for item in items
                if isinstance(item, dict)
                and str(item.get("task_id") or "").strip() == requester_task_id
                and str(item.get("member_id") or "").strip() == member_id
            ),
            None,
        )
        if isinstance(task, dict):
            _set_task_integration_pending(task, request_id=request_id, phase="integrated")
            runtime["task_center"] = task_center
    return request


__all__ = [
    "assign_collaboration_request",
    "create_collaboration_request",
    "list_collaboration_requests",
    "mark_collaboration_integrated",
    "maybe_finalize_provider_collaboration",
    "maybe_mark_provider_collaboration_submitted",
    "normalize_collaboration_center",
]
