"""Immutable identity contract for version-pinned Skill replay requests.

This module does not execute Skill code. It creates and verifies the exact
artifact binding that a future trusted sandbox broker must attest alongside
its execution result.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping


SKILL_REPLAY_SCHEMA = "mission.skill-replay-binding.v1"
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


def build_skill_replay_binding(skill: Any, mission_context: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze Skill ID, version, source digest, trust and task lineage."""
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

    return {
        "schema_version": SKILL_REPLAY_SCHEMA,
        "skill_id": skill_id,
        "skill_version": version,
        "content_sha256": content_digest,
        "trust_level": trust,
        "mission_context": _mission_context(mission_context),
    }


def verify_skill_replay_binding(binding: Any, skill: Any) -> dict[str, Any]:
    """Reject stale or substituted Skill objects before broker dispatch."""
    if not isinstance(binding, Mapping) or set(binding) != {
        "schema_version", "skill_id", "skill_version", "content_sha256",
        "trust_level", "mission_context",
    }:
        raise SkillReplayBindingError("Skill replay binding has unsupported or missing fields")
    if binding.get("schema_version") != SKILL_REPLAY_SCHEMA:
        raise SkillReplayBindingError("unsupported Skill replay binding schema")

    expected = build_skill_replay_binding(skill, binding.get("mission_context"))
    if dict(binding) != expected:
        raise SkillReplayBindingError("Skill artifact changed after replay request was created")
    return expected


__all__ = [
    "SKILL_REPLAY_SCHEMA",
    "SkillReplayBindingError",
    "build_skill_replay_binding",
    "verify_skill_replay_binding",
]
