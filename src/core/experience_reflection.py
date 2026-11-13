"""Append-only Reflection contract primitives for Experience learning.

This module deliberately does not implement reviewer authorization or Skill
promotion. Those belong to authenticated admin routes and the existing
Broker/Validator publication pipeline.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from .learning import Experience

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_STATES = {"pending", "accepted", "rejected"}


def canonical_experience_digest(experience: Experience) -> str:
    """Hash the canonical persisted Experience payload (not a caller claim)."""
    payload = json.dumps(
        experience.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _clean_string(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field} is required")
    return result


def build_pending_reflection(
    source: Experience,
    *,
    tenant_id: str,
    author: str,
    findings: dict,
    source_evidence_refs: list[str] | None = None,
    revision: int = 1,
    parent_reflection_id: str | None = None,
    idempotency_key: str,
    created_at: str | None = None,
) -> Experience:
    """Build a pending Reflection as a separate Experience record.

    The caller must obtain source from the same tenant-scoped store and must
    allocate revision/parent under its persistence transaction. This pure
    builder does not itself establish tenant membership or authorization.
    """
    tenant = _clean_string(tenant_id, "tenant_id")
    actor = _clean_string(author, "author")
    key = _clean_string(idempotency_key, "idempotency_key")
    if not isinstance(source, Experience):
        raise ValueError("source must be an Experience")
    if not isinstance(findings, dict):
        raise ValueError("findings must be an object")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("revision must be a positive integer")
    parent = str(parent_reflection_id or "").strip() or None
    if revision == 1 and parent is not None:
        raise ValueError("first reflection revision cannot have a parent")
    if revision > 1 and parent is None:
        raise ValueError("later reflection revisions require a parent")

    evidence_refs = source_evidence_refs or []
    if not isinstance(evidence_refs, list) or any(
        not isinstance(item, str) or not item.strip() for item in evidence_refs
    ):
        raise ValueError("source_evidence_refs must be a list of non-empty strings")

    now = created_at or datetime.now(timezone.utc).isoformat()
    source_digest = canonical_experience_digest(source)
    identity = {
        "tenant_id": tenant,
        "source_experience_id": source.id,
        "source_experience_digest": source_digest,
        "revision": revision,
        "parent_reflection_id": parent,
        "author": actor,
        "idempotency_key": key,
        "findings": findings,
        "source_evidence_refs": evidence_refs,
    }
    reflection_id = "reflection-" + hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:32]
    payload = {
        "schema_version": 1,
        "reflection_id": reflection_id,
        "tenant_id": tenant,
        "source_experience_id": source.id,
        "source_experience_digest": source_digest,
        "revision": revision,
        "parent_reflection_id": parent,
        "state": "pending",
        "author": actor,
        "created_at": now,
        "source_evidence_refs": list(evidence_refs),
        "findings": findings,
        "idempotency_key": key,
    }
    validate_reflection_payload(payload, expected_tenant_id=tenant, require_pending=True)
    return Experience(
        id=reflection_id,
        domain="reflection",
        task_type="experience_reflection",
        input_summary=f"Reflection for Experience {source.id}",
        output_summary=str(findings.get("observed_outcome") or "Pending Experience reflection"),
        quality_score=0.0,
        metadata={"experience_reflection": payload},
        created_at=now,
    )


def validate_reflection_payload(
    payload: dict,
    *,
    expected_tenant_id: str,
    require_pending: bool = False,
) -> None:
    """Validate structural invariants; authorization and evidence ownership are external."""
    if not isinstance(payload, dict):
        raise ValueError("reflection payload must be an object")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported reflection schema_version")
    required = (
        "reflection_id", "tenant_id", "source_experience_id",
        "source_experience_digest", "revision", "state", "author",
        "created_at", "findings", "idempotency_key",
    )
    for field in required:
        _clean_string(payload.get(field), field)
    if payload["tenant_id"] != expected_tenant_id:
        raise ValueError("reflection tenant mismatch")
    if not _DIGEST_RE.fullmatch(payload["source_experience_digest"]):
        raise ValueError("invalid source_experience_digest")
    revision = payload["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("revision must be a positive integer")
    parent = payload.get("parent_reflection_id")
    if revision == 1 and parent is not None:
        raise ValueError("first reflection revision cannot have a parent")
    if revision > 1 and not str(parent or "").strip():
        raise ValueError("later reflection revisions require a parent")
    if payload["state"] not in _ALLOWED_STATES:
        raise ValueError("invalid reflection state")
    if require_pending and payload["state"] != "pending":
        raise ValueError("new reflections must start pending")
    if not isinstance(payload["findings"], dict):
        raise ValueError("findings must be an object")
    refs = payload.get("source_evidence_refs", [])
    if not isinstance(refs, list) or any(not isinstance(item, str) or not item.strip() for item in refs):
        raise ValueError("source_evidence_refs must be a list of non-empty strings")
    if payload["state"] == "pending":
        if payload.get("reviewer") is not None or payload.get("decision_at") is not None:
            raise ValueError("pending reflection cannot contain reviewer decision fields")
    else:
        reviewer = payload.get("reviewer")
        _clean_string(reviewer.get("actor") if isinstance(reviewer, dict) else None, "reviewer.actor")
        _clean_string(payload.get("decision_at"), "decision_at")
        if payload["state"] == "rejected":
            _clean_string(payload.get("decision_reason"), "decision_reason")
