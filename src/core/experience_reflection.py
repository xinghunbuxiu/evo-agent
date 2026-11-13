"""Append-only Reflection contract primitives for Experience learning.

This module deliberately does not implement reviewer authorization or Skill
promotion. Those belong to authenticated admin routes and the existing
Broker/Validator publication pipeline.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .learning import Experience, ExperienceStore

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
    if not findings:
        raise ValueError("findings must not be empty")
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
        if field == "findings":
            if not isinstance(payload.get(field), dict) or not payload[field]:
                raise ValueError("findings must be a non-empty object")
            continue
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



@contextmanager
def _exclusive_reflection_lock(lock_path: Path):
    """Cross-platform process lock for tenant-local revision allocation."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


class ExperienceReflectionStore:
    """Tenant-bound append-only Reflection persistence on top of ExperienceStore.

    The tenant is fixed at construction. Source records are always loaded from
    that tenant's ExperienceStore; callers cannot submit a source object or
    choose a revision/parent. A cross-process lock serializes idempotency checks
    and revision allocation. ExperienceStore's durable outbox remains the only
    remote archival path.
    """

    def __init__(self, workspace: Path, tenant_id: str):
        self.experience_store = ExperienceStore(Path(workspace), tenant_id)
        self.tenant_id = self.experience_store.tenant_id
        self.lock_path = self.experience_store.tenant_root / ".experience-reflections.lock"

    @staticmethod
    def _safe_id(value: str, field: str) -> str:
        result = _clean_string(value, field)
        if result in {".", ".."} or "/" in result or chr(92) in result:
            raise ValueError(f"{field} must be a safe path segment")
        return result

    def _load_source(self, source_experience_id: str) -> Experience:
        source_id = self._safe_id(source_experience_id, "source_experience_id")
        matches = []
        if not self.experience_store.exp_dir.is_dir():
            raise ValueError("source Experience does not exist in this tenant")
        for domain_dir in self.experience_store.exp_dir.iterdir():
            if domain_dir.is_symlink() or not domain_dir.is_dir():
                continue
            candidate = domain_dir / f"{source_id}.json"
            if not candidate.exists():
                continue
            if candidate.is_symlink() or not candidate.is_file():
                raise ValueError("source Experience record is unsafe")
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                source = Experience(**data)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
                raise ValueError("source Experience record is unreadable") from exc
            if source.id != source_id or source.domain != domain_dir.name:
                raise ValueError("source Experience identity does not match its stored path")
            matches.append(source)
        if len(matches) != 1:
            raise ValueError(
                "source Experience does not exist or is ambiguous in this tenant"
                if not matches else "source Experience ID is ambiguous in this tenant"
            )
        return matches[0]

    @staticmethod
    def _source_evidence_refs(metadata: dict) -> set[str]:
        """Collect evidence identifiers already recorded on the source Experience."""
        refs: set[str] = set()

        def visit(value: Any, evidence_context: bool = False) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    visit(child, evidence_context or "evidence" in str(key).lower())
            elif isinstance(value, list):
                for child in value:
                    visit(child, evidence_context)
            elif evidence_context and isinstance(value, str) and value.strip():
                refs.add(value.strip())

        visit(metadata)
        return refs

    def _load_all_reflections(self) -> list[Experience]:
        """Read both projections and outbox events to recover interrupted saves."""
        found: dict[str, Experience] = {}

        def add_experience(data: dict) -> None:
            try:
                experience = Experience(**data)
            except (TypeError, ValueError) as exc:
                raise ValueError("stored Reflection Experience is malformed") from exc
            if experience.domain != "reflection" or experience.task_type != "experience_reflection":
                return
            payload = experience.metadata.get("experience_reflection")
            validate_reflection_payload(payload, expected_tenant_id=self.tenant_id)
            if payload.get("reflection_id") != experience.id:
                raise ValueError("Reflection ID does not match its Experience projection")
            serialized = _canonical_json(experience.to_dict())
            previous = found.get(experience.id)
            if previous is not None and _canonical_json(previous.to_dict()) != serialized:
                raise ValueError("Reflection ID has conflicting persisted content")
            found[experience.id] = experience

        projection_dir = self.experience_store.exp_dir / "reflection"
        if projection_dir.is_dir():
            for path in projection_dir.glob("*.json"):
                if path.is_symlink() or not path.is_file():
                    raise ValueError("Reflection projection contains an unsafe entry")
                try:
                    add_experience(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise ValueError("Reflection projection is unreadable") from exc

        outbox_root = self.experience_store.tenant_root / "experience_outbox"
        for state in ("pending", "delivered"):
            directory = outbox_root / state
            if not directory.is_dir():
                continue
            for path in directory.glob("*.json"):
                if path.is_symlink() or not path.is_file():
                    raise ValueError("Reflection outbox contains an unsafe entry")
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                    if record.get("tenant_id") != self.tenant_id:
                        raise ValueError("Reflection outbox tenant mismatch")
                    if record.get("domain") != "reflection":
                        continue
                    content = record.get("content")
                    if not isinstance(content, str):
                        raise ValueError("Reflection outbox content is missing")
                    add_experience(json.loads(content))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise ValueError("Reflection outbox record is unreadable") from exc
        return list(found.values())

    def append(
        self,
        source_experience_id: str,
        *,
        author: str,
        findings: dict,
        idempotency_key: str,
        source_evidence_refs: list[str] | None = None,
        created_at: str | None = None,
    ) -> Experience:
        """Append one pending revision; retries return the original immutable record.

        Authentication and author membership must be established by the calling
        route. This store binds persistence to its tenant but is not an auth layer.
        """
        source_id = self._safe_id(source_experience_id, "source_experience_id")
        actor = _clean_string(author, "author")
        key = _clean_string(idempotency_key, "idempotency_key")
        if not isinstance(findings, dict) or not findings:
            raise ValueError("findings must be a non-empty object")
        refs = source_evidence_refs if source_evidence_refs is not None else []
        if not isinstance(refs, list) or any(
            not isinstance(item, str) or not item.strip() for item in refs
        ):
            raise ValueError("source_evidence_refs must be a list of non-empty strings")
        # Reject non-JSON values before taking the persistence lock.
        _canonical_json(findings)
        _canonical_json(refs)

        with _exclusive_reflection_lock(self.lock_path):
            source = self._load_source(source_id)
            source_digest = canonical_experience_digest(source)
            known_evidence_refs = self._source_evidence_refs(source.metadata)
            unknown_evidence_refs = sorted(set(refs) - known_evidence_refs)
            if unknown_evidence_refs:
                raise ValueError("source evidence reference is not attached to this Experience")
            records = self._load_all_reflections()

            for existing in records:
                payload = existing.metadata["experience_reflection"]
                if payload["idempotency_key"] != key:
                    continue
                same_request = (
                    payload["source_experience_id"] == source_id
                    and payload["source_experience_digest"] == source_digest
                    and payload["author"] == actor
                    and _canonical_json(payload["findings"]) == _canonical_json(findings)
                    and payload.get("source_evidence_refs", []) == refs
                )
                if not same_request:
                    raise ValueError("idempotency_key was already used with different Reflection content")
                # Recover the projection if a prior process stopped after
                # writing the outbox event but before completing ExperienceStore.save.
                projection = (
                    self.experience_store.exp_dir / "reflection" / f"{existing.id}.json"
                )
                if projection.exists():
                    if projection.is_symlink() or not projection.is_file():
                        raise ValueError("Reflection projection is unsafe")
                    stored = json.loads(projection.read_text(encoding="utf-8"))
                    if _canonical_json(stored) != _canonical_json(existing.to_dict()):
                        raise ValueError("Reflection projection conflicts with its immutable outbox record")
                else:
                    self.experience_store.save(existing)
                return existing

            source_records = [
                item for item in records
                if item.metadata["experience_reflection"]["source_experience_id"] == source_id
            ]
            source_records.sort(
                key=lambda item: item.metadata["experience_reflection"]["revision"]
            )
            if any(
                item.metadata["experience_reflection"]["source_experience_digest"] != source_digest
                for item in source_records
            ):
                raise ValueError("source Experience digest changed; cannot append to its Reflection chain")
            previous_id = None
            for expected_revision, item in enumerate(source_records, start=1):
                payload = item.metadata["experience_reflection"]
                if payload["revision"] != expected_revision:
                    raise ValueError("Reflection revision sequence is inconsistent")
                if payload.get("parent_reflection_id") != previous_id:
                    raise ValueError("Reflection parent chain is inconsistent")
                previous_id = item.id

            revision = len(source_records) + 1
            reflection = build_pending_reflection(
                source,
                tenant_id=self.tenant_id,
                author=actor,
                findings=findings,
                source_evidence_refs=refs,
                revision=revision,
                parent_reflection_id=previous_id,
                idempotency_key=key,
                created_at=created_at,
            )
            # save() writes the immutable outbox event first, then the unique
            # revision-ID projection. The process lock prevents concurrent
            # allocators from selecting the same revision or idempotency key.
            self.experience_store.save(reflection)
            return reflection

    def list_for_source(self, source_experience_id: str) -> list[Experience]:
        source_id = self._safe_id(source_experience_id, "source_experience_id")
        with _exclusive_reflection_lock(self.lock_path):
            records = [
                item for item in self._load_all_reflections()
                if item.metadata["experience_reflection"]["source_experience_id"] == source_id
            ]
            records.sort(
                key=lambda item: item.metadata["experience_reflection"]["revision"]
            )
            return records
