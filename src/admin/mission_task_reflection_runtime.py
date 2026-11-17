"""Create factual, tenant-bound Experience and pending Reflection records for terminal Mission tasks."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.experience_reflection import ExperienceReflectionStore, canonical_experience_digest
from core.learning import Experience, ExperienceStore


def _text(value: Any, limit: int = 1200) -> str:
    return str(value or "").strip()[:limit]


def record_mission_task_reflection(
    *,
    workspace: Path,
    tenant_id: str,
    mission_run: dict,
    action: dict,
    task,
) -> dict:
    """Persist one immutable task observation and its pending human-review Reflection.

    This records only what the Mission runtime observed. It never accepts worker
    claims as independent verification and never approves or promotes a Skill.
    """
    tenant = _text(tenant_id, 180)
    mission_run_id = _text(mission_run.get("mission_run_id"), 180)
    node_id = _text(action.get("node_id"), 180)
    task_id = _text(getattr(task, "id", ""), 180)
    status = _text(getattr(getattr(task, "status", None), "value", getattr(task, "status", "")), 40).lower()
    terminal_at = _text(
        getattr(task, "completed_at", "")
        or getattr(task, "updated_at", "")
        or getattr(task, "created_at", ""),
        80,
    )
    if not tenant or not mission_run_id or not node_id or not task_id:
        raise ValueError("Mission task reflection lineage is incomplete")
    if status not in {"success", "completed", "failed", "cancelled"}:
        raise ValueError("Mission task reflection requires a terminal queue task")
    if not terminal_at:
        raise ValueError("Mission task terminal timestamp is missing")
    action_tenant = _text(action.get("tenant_id"), 180)
    action_run = _text(action.get("mission_run_id"), 180)
    if action_tenant != tenant or action_run != mission_run_id:
        raise ValueError("Mission task reflection tenant or run binding mismatch")

    result = getattr(task, "result", None)
    result = result if isinstance(result, dict) else {}
    summary = _text(result.get("summary") or result.get("message") or action.get("detail"), 1200)
    error = _text(getattr(task, "error", "") or result.get("error"), 1200)
    verification = action.get("independent_verification")
    if not isinstance(verification, dict) or verification.get("source") != "mission_independent_verifier":
        verification = None
    else:
        verification = {
            "task_id": _text(verification.get("task_id"), 180),
            "execution_event_id": _text(verification.get("execution_event_id"), 240),
            "verifier_id": _text(verification.get("verifier_id"), 180),
            "verifier_version": _text(verification.get("verifier_version"), 100),
            "status": _text(verification.get("status"), 40),
            "checks": [
                {
                    "check_id": _text(item.get("check_id"), 180),
                    "passed": item.get("passed") is True,
                }
                for item in verification.get("checks", [])
                if isinstance(item, dict)
            ],
        }
        if (
            verification["task_id"] != task_id
            or verification["status"] not in {"passed", "failed"}
            or not verification["verifier_id"]
            or not verification["verifier_version"]
            or not verification["execution_event_id"]
        ):
            verification = None

    terminal_event_id = f"task-terminal:{task_id}:{terminal_at}:{status}"
    evidence_refs = [task_id, mission_run_id, node_id, terminal_event_id]
    if verification:
        evidence_refs.append(verification["execution_event_id"])
    source_id = "mission-task-" + hashlib.sha256(
        f"{tenant}:{mission_run_id}:{node_id}:{task_id}".encode("utf-8")
    ).hexdigest()[:32]
    source = Experience(
        id=source_id,
        domain="mission_task",
        task_type="mission_task_outcome",
        input_summary=_text(action.get("title") or action.get("task_type") or node_id, 500),
        output_summary=summary or error or f"Mission task ended with status: {status}",
        quality_score=0.0,
        metadata={
            "source": "mission_task_terminal_observation",
            "tenant_id": tenant,
            "mission_run_id": mission_run_id,
            "mission_node_id": node_id,
            "task_id": task_id,
            "terminal_status": status,
            "terminal_at": terminal_at,
            "terminal_event_id": terminal_event_id,
            "worker_id": _text(action.get("worker_id") or action.get("assigned_worker_id"), 180) or None,
            "worker_reported_summary": summary,
            "observed_error": error,
            "verification": verification,
            "evidence_refs": evidence_refs,
            "quality_score_semantics": "unrated_observation_not_a_promotion_signal",
        },
        created_at=terminal_at,
    )
    experience_store = ExperienceStore(Path(workspace), tenant)
    existing = [
        item for item in experience_store.load_by_domain("mission_task", limit=10000)
        if item.id == source_id
    ]
    if existing:
        if len(existing) != 1 or canonical_experience_digest(existing[0]) != canonical_experience_digest(source):
            raise ValueError("Mission task Experience ID conflicts with existing immutable content")
        source = existing[0]
    else:
        experience_store.save(source)

    findings = {
        "observed_outcome": (
            f"Queue task status={status}; "
            + (f"worker summary: {summary}" if summary else "no worker summary was supplied")
            + (f"; observed error: {error}" if error else "")
        )[:1600],
        "success_factors": (
            [f"independent check passed: {item['check_id']}" for item in verification["checks"] if item["passed"]]
            if verification else []
        ),
        "failure_causes": (
            [f"independent check failed: {item['check_id']}" for item in verification["checks"] if not item["passed"]]
            if verification else []
        ) + ([f"queue task error: {error}"] if error else []),
        "applicability_conditions": [
            f"Mission run {mission_run_id}",
            f"Mission node {node_id}",
        ],
        "constraints": [
            "This is an automatically generated factual draft, not a reviewer conclusion.",
            "Worker-reported output is unverified unless independent verification evidence is attached.",
        ],
        "counterexamples": [],
        "open_questions": (
            [] if verification and verification["status"] == "passed"
            else ["Independent validation is absent or did not pass; do not treat this task as an accepted reusable procedure."]
        ),
        "source_kind": "automatic_mission_terminal_observation",
    }
    reflection = ExperienceReflectionStore(Path(workspace), tenant).append(
        source.id,
        author="mission-system",
        findings=findings,
        idempotency_key=f"mission-terminal-reflection:{mission_run_id}:{node_id}:{task_id}",
        source_evidence_refs=evidence_refs,
        created_at=terminal_at,
    )
    payload = reflection.metadata["experience_reflection"]
    return {
        "status": "created",
        "source_experience_id": source.id,
        "source_experience_digest": canonical_experience_digest(source),
        "reflection_id": reflection.id,
        "reflection_revision": payload["revision"],
        "review_state": payload["state"],
        "terminal_event_id": terminal_event_id,
        "independent_verification": (
            verification["status"] if verification else "unavailable"
        ),
    }
