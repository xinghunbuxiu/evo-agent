
"""Mission-facing bridge from signed Broker Skill Replay to durable Experience."""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Mapping

from .sandbox_broker_protocol import SKILL_REPLAY_PROFILE_ID
from .sandbox_broker_transport import execute_via_broker_attested
from .skill_replay_evidence_store import SkillReplayEvidenceStore

_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_WORKSPACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SkillReplayMissionError(RuntimeError):
    """Mission Replay failed after a known point in the evidence lifecycle."""

    def __init__(self, message: str, *, evidence_ref: dict[str, str] | None = None):
        super().__init__(message)
        self.evidence_ref = evidence_ref


class SkillReplayMissionAdapter:
    """Execute one immutable Skill binding and persist only Broker-verified evidence.

    The adapter deliberately does not invoke SkillExecutor or run Skill code in
    the Mission process. The Broker owns artifact resolution and isolated execution.
    """

    def __init__(
        self, *, socket_path: str, workspace_id: str, broker_public_key: bytes,
        broker_key_id: str, evidence_store: SkillReplayEvidenceStore,
        experience_workspace: Path,
    ):
        if not isinstance(socket_path, str) or not socket_path.startswith("/") or "\x00" in socket_path:
            raise ValueError("broker socket path must be absolute")
        if not isinstance(workspace_id, str) or not _WORKSPACE_RE.fullmatch(workspace_id):
            raise ValueError("workspace_id is invalid")
        if not isinstance(broker_key_id, str) or not broker_key_id.strip():
            raise ValueError("broker_key_id is required")
        if not isinstance(evidence_store, SkillReplayEvidenceStore):
            raise TypeError("evidence_store must be a verified SkillReplayEvidenceStore")
        self.socket_path = socket_path
        self.workspace_id = workspace_id
        self.broker_public_key = bytes(broker_public_key)
        self.broker_key_id = broker_key_id
        self.evidence_store = evidence_store
        self.experience_workspace = Path(experience_workspace)

    def execute(
        self, spec: Any, *, tenant_id: str, mission_context: Mapping[str, Any],
        skill_binding: Mapping[str, Any], domain: str, task_type: str,
        input_summary: str,
    ) -> dict[str, Any]:
        """Run via Broker, persist the signed envelope, then project Experience.

        A non-zero or timed-out Skill run is still a signed observation and is
        recorded as failed/pending reflection. Transport or signature failures
        produce no Experience and are never converted into successful evidence.
        """
        if not isinstance(tenant_id, str) or not _IDENTITY_RE.fullmatch(tenant_id):
            raise ValueError("tenant_id is invalid")
        if not isinstance(mission_context, Mapping):
            raise ValueError("mission_context is required")
        context = dict(mission_context)
        if set(context) != {"tenant_id", "mission_run_id", "node_id", "task_id"}:
            raise ValueError("mission_context has unsupported or missing fields")
        if context.get("tenant_id") != tenant_id:
            raise ValueError("tenant_id does not match Mission context")
        if any(not isinstance(context.get(key), str) or not _IDENTITY_RE.fullmatch(context[key])
               for key in ("tenant_id", "mission_run_id", "node_id", "task_id")):
            raise ValueError("Mission context contains an invalid identity")
        if not isinstance(skill_binding, Mapping):
            raise ValueError("Skill replay binding is required")
        binding = dict(skill_binding)
        if binding.get("mission_context") != context:
            raise ValueError("Skill binding does not match Mission context")
        if getattr(spec, "profile_id", None) != SKILL_REPLAY_PROFILE_ID:
            raise ValueError("Mission Skill Replay requires the dedicated replay profile")
        expected_target = f"{binding.get('skill_id')}@{binding.get('skill_version')}"
        if getattr(spec, "target", None) != expected_target:
            raise ValueError("Skill Replay target does not match immutable Skill binding")
        for field, value in (("domain", domain), ("task_type", task_type)):
            if not isinstance(value, str) or not _IDENTITY_RE.fullmatch(value):
                raise ValueError(f"{field} is invalid")
        if not isinstance(input_summary, str):
            raise ValueError("input_summary must be a string")

        # A retry of the same Mission task must address the same Broker
        # operation. Broker returns the original signed response if complete,
        # and refuses re-execution if the prior outcome is indeterminate.
        request_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            "evo-agent:skill-replay:execute:"
            + ":".join(context[key] for key in (
                "tenant_id", "mission_run_id", "node_id", "task_id",
            )),
        ))
        attested = execute_via_broker_attested(
            self.socket_path, self.workspace_id, spec,
            mission_context=context, public_key=self.broker_public_key,
            expected_key_id=self.broker_key_id, skill_binding=binding,
            request_id=request_id,
        )
        evidence_ref = self.evidence_store.record(
            attested, tenant_id=tenant_id, workspace_id=self.workspace_id,
            mission_context=context, skill_binding=binding,
        )
        try:
            experience = self.evidence_store.record_experience(
                self.experience_workspace, tenant_id=tenant_id,
                evidence_id=evidence_ref["evidence_id"], domain=domain,
                task_type=task_type, input_summary=input_summary,
            )
        except Exception as exc:
            raise SkillReplayMissionError(
                "Broker evidence was persisted but Experience projection failed",
                evidence_ref=evidence_ref,
            ) from exc
        replay = experience.metadata.get("skill_replay", {}) if isinstance(experience.metadata, dict) else {}
        reflection = replay.get("reflection", {}) if isinstance(replay, dict) else {}
        return {
            "schema_version": "mission.skill-replay-result.v1",
            "result": attested["result"],
            "skill_replay_output": attested["skill_replay_output"],
            "evidence": evidence_ref,
            "experience": {
                "id": experience.id,
                "quality_score": experience.quality_score,
                "execution_status": replay.get("execution_status"),
                "reflection_status": reflection.get("status", "pending"),
            },
        }


__all__ = ["SkillReplayMissionAdapter", "SkillReplayMissionError"]
