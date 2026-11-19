"""Immutable identity contract for version-pinned Skill replay requests.

A v1 binding pins source and Mission lineage. A v2 binding additionally pins
the canonical Skill Manifest digest. The Manifest is metadata, never executable
input; Broker-owned storage and the Validator remain separate trust boundaries.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from .skill_manifest import normalize_skill_manifest, manifest_sha256


SKILL_REPLAY_SCHEMA = "mission.skill-replay-binding.v1"
SKILL_REPLAY_MANIFEST_SCHEMA = "mission.skill-replay-binding.v2"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
_TRUST_LEVELS = {"draft", "verified", "cloud"}


class SkillReplayBindingError(ValueError):
    """A Skill artifact or replay identity cannot be safely bound."""


def _required_identity(value: Any, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise SkillReplayBindingError(f"{field} is invalid")
    return value


def _mission_context(value: Any) -> dict[str, str]:
    fields = {"tenant_id", "mission_run_id", "node_id", "task_id"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise SkillReplayBindingError("mission_context must contain exact Tenant, Mission, node, and task identities")
    return {
        field: _required_identity(value[field], f"mission_context.{field}", _ID_RE)
        for field in sorted(fields)
    }


def _skill_manifest(skill: Any) -> dict[str, Any] | None:
    parameters = getattr(skill, "parameters", None)
    manifest = parameters.get("manifest") if isinstance(parameters, Mapping) else None
    if manifest is None:
        return None
    try:
        normalized = normalize_skill_manifest(manifest)
    except ValueError as exc:
        raise SkillReplayBindingError("Skill Manifest is invalid") from exc
    expected = {
        "skill_id": getattr(skill, "id", None),
        "skill_version": getattr(skill, "version", None),
        "name": getattr(skill, "name", None),
        "domain": getattr(skill, "domain", None),
        "capability_type": getattr(skill, "capability_type", None),
        "description": getattr(skill, "description", None),
    }
    if any(normalized.get(key) != value for key, value in expected.items()):
        raise SkillReplayBindingError("Skill Manifest identity does not match the Skill record")
    return normalized


def build_skill_replay_binding(skill: Any, mission_context: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze source, optional canonical Manifest digest, trust and Mission lineage."""
    skill_id = _required_identity(getattr(skill, "id", None), "skill_id", _ID_RE)
    version = _required_identity(getattr(skill, "version", None), "skill_version", _VERSION_RE)
    code = getattr(skill, "code", None)
    if not isinstance(code, str) or not code.strip():
        raise SkillReplayBindingError("skill code must be a non-empty UTF-8 string")
    try:
        content_digest = hashlib.sha256(code.encode("utf-8", errors="strict")).hexdigest()
    except UnicodeError as exc:
        raise SkillReplayBindingError("skill code is not valid UTF-8") from exc
    trust = getattr(getattr(skill, "trust_level", None), "value", getattr(skill, "trust_level", None))
    if trust not in _TRUST_LEVELS:
        raise SkillReplayBindingError("skill trust_level is invalid")
    context = _mission_context(mission_context)
    manifest = _skill_manifest(skill)
    if manifest is None:
        return {
            "schema_version": SKILL_REPLAY_SCHEMA,
            "skill_id": skill_id,
            "skill_version": version,
            "content_sha256": content_digest,
            "trust_level": trust,
            "mission_context": context,
        }
    return {
        "schema_version": SKILL_REPLAY_MANIFEST_SCHEMA,
        "skill_id": skill_id,
        "skill_version": version,
        "content_sha256": content_digest,
        "manifest_sha256": manifest_sha256(manifest),
        "trust_level": trust,
        "mission_context": context,
    }


def verify_skill_replay_binding(binding: Any, skill: Any) -> dict[str, Any]:
    """Reject stale, substituted or Manifest-swapped Skill objects before dispatch."""
    if not isinstance(binding, Mapping):
        raise SkillReplayBindingError("Skill replay binding has unsupported or missing fields")
    schema = binding.get("schema_version")
    fields = (
        {"schema_version", "skill_id", "skill_version", "content_sha256", "trust_level", "mission_context"}
        if schema == SKILL_REPLAY_SCHEMA else
        {"schema_version", "skill_id", "skill_version", "content_sha256", "manifest_sha256", "trust_level", "mission_context"}
        if schema == SKILL_REPLAY_MANIFEST_SCHEMA else set()
    )
    if not fields or set(binding) != fields:
        raise SkillReplayBindingError("Skill replay binding has unsupported or missing fields")
    expected = build_skill_replay_binding(skill, binding.get("mission_context"))
    if dict(binding) != expected:
        raise SkillReplayBindingError("Skill artifact changed after replay request was created")
    return expected


__all__ = [
    "SKILL_REPLAY_SCHEMA",
    "SKILL_REPLAY_MANIFEST_SCHEMA",
    "SkillReplayBindingError",
    "build_skill_replay_binding",
    "verify_skill_replay_binding",
]
