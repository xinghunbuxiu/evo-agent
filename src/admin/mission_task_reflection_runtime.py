"""Create factual, tenant-bound Experience and pending Reflection records for terminal Mission tasks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from core.experience_reflection import ExperienceReflectionStore, canonical_experience_digest
from core.learning import Experience, ExperienceStore
from core.verification import verify_verification_evidence


def _text(value: Any, limit: int = 1200) -> str:
    return str(value or "").strip()[:limit]


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _validated_verification_attestation(
    workspace: Path,
    tenant_id: str,
    mission_run_id: str,
    node_id: str,
    task_id: str,
    task,
    value: Any,
) -> tuple[dict | None, str | None]:
    """Accept only a locally signed verifier result bound to this exact queue task."""
    if not isinstance(value, dict):
        return None, "not_provided"

    required = {
        "source", "task_id", "tenant_id", "mission_run_id", "mission_node_id",
        "execution_event_id", "verifier_id", "verifier_version", "status", "checks",
    }
    # A missing signature is an authentication failure, not a malformed
    # attestation. Unknown or missing non-signature fields remain shape errors.
    if frozenset(value) not in {frozenset(required), frozenset(required | {"signature"})}:
        return None, "attestation_shape_invalid"

    signature = value.get("signature")
    if (
        not isinstance(signature, dict)
        or set(signature) != {"algorithm", "key_id", "value"}
        or not verify_verification_evidence(Path(workspace), tenant_id, value)
    ):
        return None, "signature_invalid"

    completed_at = _text(getattr(task, "completed_at", ""), 80)
    expected_event_id = f"task-completion:{task_id}:{completed_at}" if completed_at else ""
    expected = {
        "source": "mission_independent_verifier",
        "task_id": task_id,
        "tenant_id": tenant_id,
        "mission_run_id": mission_run_id,
        "mission_node_id": node_id,
        "execution_event_id": expected_event_id,
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        return None, "attestation_binding_mismatch"
    if not expected_event_id:
        return None, "execution_event_missing"
    if not _text(value.get("verifier_id"), 180) or not _text(value.get("verifier_version"), 100):
        return None, "verifier_identity_missing"

    checks = value.get("checks")
    if not isinstance(checks, list) or not checks:
        return None, "checks_missing"
    check_ids: set[str] = set()
    for check in checks:
        if not isinstance(check, dict):
            return None, "checks_invalid"
        check_id = _text(check.get("check_id"), 180)
        if not check_id or check_id in check_ids or not isinstance(check.get("passed"), bool):
            return None, "checks_invalid"
        check_ids.add(check_id)

    task_status = _text(
        getattr(getattr(task, "status", None), "value", getattr(task, "status", "")),
        40,
    ).lower()
    task_succeeded = task_status in {"success", "completed"}
    verdict = value.get("status")
    all_checks_passed = all(item["passed"] for item in checks)
    if verdict == "passed":
        if not task_succeeded or not all_checks_passed:
            return None, "verdict_inconsistent"
    elif verdict == "failed":
        if task_succeeded and all_checks_passed:
            return None, "verdict_inconsistent"
    else:
        return None, "verdict_invalid"

    return dict(value), None


def _load_or_create_source(
    experience_store: ExperienceStore,
    candidate: Experience,
    *,
    stable_evidence_refs: list[str],
) -> Experience:
    """Keep the task observation immutable while allowing later proof enrichment."""
    source_path = experience_store.exp_dir / "mission_task" / f"{candidate.id}.json"
    if source_path.is_symlink():
        raise ValueError("Mission task Experience record is unsafe")
    if not source_path.exists():
        experience_store.save(candidate)
        if source_path.is_symlink() or not source_path.is_file():
            raise ValueError("Mission task Experience readback is missing")
        try:
            stored = Experience(**json.loads(source_path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError("Mission task Experience readback is invalid") from exc
        if canonical_experience_digest(stored) != canonical_experience_digest(candidate):
            raise ValueError("Mission task Experience readback digest mismatch")
        return stored
    if not source_path.is_file():
        raise ValueError("Mission task Experience record is unsafe")
    try:
        existing = Experience(**json.loads(source_path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("Mission task Experience record is unreadable") from exc

    expected_metadata = candidate.metadata
    actual_metadata = existing.metadata if isinstance(existing.metadata, dict) else {}
    stable_fields = (
        "source", "tenant_id", "mission_run_id", "mission_node_id", "task_id",
        "terminal_status", "terminal_at", "terminal_event_id",
    )
    if (
        existing.id != candidate.id
        or existing.domain != "mission_task"
        or existing.task_type != candidate.task_type
        or existing.created_at != candidate.created_at
        or any(actual_metadata.get(field) != expected_metadata.get(field) for field in stable_fields)
    ):
        raise ValueError("Mission task Experience ID conflicts with existing immutable content")
    existing_refs = actual_metadata.get("evidence_refs")
    if (
        not isinstance(existing_refs, list)
        or not set(stable_evidence_refs).issubset(
            {item for item in existing_refs if isinstance(item, str)}
        )
    ):
        raise ValueError("Mission task Experience evidence lineage conflicts with existing content")
    return existing


def _reflection_result(
    reflection: Experience,
    source: Experience,
    terminal_event_id: str,
    *,
    reused: bool = False,
) -> dict:
    payload = reflection.metadata.get("experience_reflection", {})
    findings = payload.get("findings", {}) if isinstance(payload, dict) else {}
    execution = findings.get("execution_evidence", {}) if isinstance(findings, dict) else {}
    signed = (
        execution.get("signature_verification") == "valid"
        and isinstance(execution.get("attestation"), dict)
    )
    return {
        "status": "created",
        "source_experience_id": source.id,
        "source_experience_digest": canonical_experience_digest(source),
        "reflection_id": reflection.id,
        "reflection_revision": payload.get("revision"),
        "review_state": payload.get("state", "pending"),
        "terminal_event_id": terminal_event_id,
        "independent_verification": execution.get("verdict") if signed else "unavailable",
        "verification_evidence_sha256": execution.get("sha256") if signed else None,
        "reused": reused,
    }


def record_mission_task_reflection(
    *,
    workspace: Path,
    tenant_id: str,
    mission_run: dict,
    action: dict,
    task,
) -> dict:
    """Persist one immutable task observation and append signed evidence as a Reflection.

    Worker output is stored as a report, never as independent verification. A
    valid verifier attestation is retained in the append-only Reflection itself,
    so a verifier that becomes available on a later refresh can add a new
    revision without mutating the original Experience or its digest.
    """
    if not isinstance(mission_run, dict) or not isinstance(action, dict) or task is None:
        raise ValueError("Mission task reflection context is invalid")

    tenant = _text(tenant_id, 180)
    mission_run_id = _text(mission_run.get("mission_run_id"), 180)
    node_id = _text(action.get("node_id"), 180)
    task_id = _text(getattr(task, "id", ""), 180)
    action_task_id = _text(action.get("task_id"), 180)
    status = _text(
        getattr(getattr(task, "status", None), "value", getattr(task, "status", "")),
        40,
    ).lower()
    terminal_at = _text(
        getattr(task, "completed_at", "")
        or getattr(task, "updated_at", "")
        or getattr(task, "created_at", ""),
        80,
    )
    mission_tenant_id = _text(mission_run.get("tenant_id") or "default", 180)
    action_tenant = _text(action.get("tenant_id"), 180)
    task_tenant = _text(getattr(task, "tenant_id", ""), 180)

    if not tenant or not mission_run_id or not node_id or not task_id or not terminal_at:
        raise ValueError("Mission task reflection lineage is incomplete")
    if status not in {"success", "completed", "failed", "cancelled"}:
        raise ValueError("Mission task reflection requires a terminal queue task")
    if mission_tenant_id != tenant or action_tenant != tenant or task_tenant != tenant:
        raise ValueError("Mission task reflection tenant binding mismatch")
    if action_task_id != task_id:
        raise ValueError("Mission task reflection task binding mismatch")
    if _text(action.get("mission_run_id"), 180) != mission_run_id:
        raise ValueError("Mission task reflection run binding mismatch")

    result = getattr(task, "result", None)
    result = result if isinstance(result, dict) else {}
    summary = _text(result.get("summary") or result.get("message"), 1200)
    error = _text(getattr(task, "error", "") or result.get("error"), 1200)
    worker_id = _text(action.get("worker_id") or action.get("assigned_worker_id"), 180) or None

    terminal_event_id = f"task-terminal:{task_id}:{terminal_at}:{status}"
    completed_at = _text(getattr(task, "completed_at", ""), 80)
    execution_event_id = f"task-completion:{task_id}:{completed_at}" if completed_at else None
    evidence_refs = [task_id, mission_run_id, node_id, terminal_event_id]
    if execution_event_id:
        evidence_refs.append(execution_event_id)

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
            "worker_id": worker_id,
            "worker_reported_summary": summary,
            "observed_error": error,
            "evidence_refs": evidence_refs,
            "quality_score_semantics": "unrated_observation_not_a_promotion_signal",
        },
        created_at=terminal_at,
    )

    experience_store = ExperienceStore(Path(workspace), tenant)
    base_evidence_refs = [task_id, mission_run_id, node_id, terminal_event_id]
    source = _load_or_create_source(
        experience_store, source, stable_evidence_refs=base_evidence_refs,
    )
    source_metadata = source.metadata if isinstance(source.metadata, dict) else {}
    # The first immutable observation wins if a worker mutates its summary after
    # terminal completion. Later evidence is appended to Reflection revisions.
    summary = _text(source_metadata.get("worker_reported_summary"), 1200)
    error = _text(source_metadata.get("observed_error"), 1200)
    source_evidence_refs = list(base_evidence_refs)
    if execution_event_id and execution_event_id in source_metadata.get("evidence_refs", []):
        source_evidence_refs.append(execution_event_id)

    attestation, verification_reason = _validated_verification_attestation(
        Path(workspace), tenant, mission_run_id, node_id, task_id, task,
        action.get("independent_verification"),
    )
    verification_digest = (
        hashlib.sha256(_canonical_json(attestation)).hexdigest()
        if attestation is not None else None
    )

    reflection_store = ExperienceReflectionStore(Path(workspace), tenant)
    existing_reflections = reflection_store.list_for_source(source.id)

    if attestation is None:
        # Do not append an unverified downgrade after a valid signed verifier
        # result has already been retained for this immutable task observation.
        for existing_reflection in reversed(existing_reflections):
            payload = existing_reflection.metadata.get("experience_reflection", {})
            findings = payload.get("findings", {}) if isinstance(payload, dict) else {}
            execution = findings.get("execution_evidence", {}) if isinstance(findings, dict) else {}
            stored_attestation = execution.get("attestation") if isinstance(execution, dict) else None
            if not isinstance(stored_attestation, dict):
                continue
            validated, _ = _validated_verification_attestation(
                Path(workspace), tenant, mission_run_id, node_id, task_id, task,
                stored_attestation,
            )
            stored_digest = hashlib.sha256(_canonical_json(validated)).hexdigest() if validated else None
            if (
                validated is not None
                and execution.get("signature_verification") == "valid"
                and execution.get("sha256") == stored_digest
            ):
                return _reflection_result(
                    existing_reflection, source, terminal_event_id, reused=True,
                )

    execution_evidence = {
        "signature_verification": "valid" if attestation is not None else "unavailable",
        "verdict": attestation.get("status") if attestation is not None else None,
        "sha256": verification_digest,
        "attestation": attestation,
        "reason": verification_reason,
    }
    findings = {
        "observed_outcome": (
            f"Queue task status={status}; "
            + (f"worker summary: {summary}" if summary else "no worker summary was supplied")
            + (f"; observed error: {error}" if error else "")
        )[:1600],
        "success_factors": (
            [f"independent check passed: {item['check_id']}" for item in attestation["checks"] if item["passed"]]
            if attestation and attestation["status"] == "passed" else []
        ),
        "failure_causes": (
            [f"independent check failed: {item['check_id']}" for item in attestation["checks"] if not item["passed"]]
            if attestation else []
        ) + ([f"queue task error: {error}"] if error else []),
        "applicability_conditions": [
            f"Mission run {mission_run_id}",
            f"Mission node {node_id}",
        ],
        "constraints": [
            "This is an automatically generated factual draft, not a reviewer conclusion.",
            "Worker-reported output is unverified unless a valid runtime-signed verifier attestation is attached.",
            "A signed verifier result is evidence, not automatic Skill approval or promotion.",
        ],
        "counterexamples": [],
        "open_questions": (
            ["Independent verifier evidence is unavailable or invalid; do not treat this task as an accepted reusable procedure."]
            if attestation is None else (
                ["Independent verifier checks failed; inspect the signed failed checks before reuse."]
                if attestation["status"] == "failed" else []
            )
        ),
        "execution_evidence": execution_evidence,
        "source_kind": "automatic_mission_terminal_observation",
    }
    idempotency_key = (
        f"mission-terminal-reflection:{mission_run_id}:{node_id}:{task_id}:"
        + (f"verification:{verification_digest}" if verification_digest else "unverified")
    )
    reflection = reflection_store.append(
        source.id,
        author="mission-system",
        findings=findings,
        idempotency_key=idempotency_key,
        source_evidence_refs=source_evidence_refs,
        created_at=terminal_at,
    )
    return _reflection_result(reflection, source, terminal_event_id)
