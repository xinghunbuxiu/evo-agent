"""Durable tenant-scoped Skill Replay evidence with Broker signature re-verification."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .sandbox_broker_protocol import SKILL_REPLAY_PROFILE_ID, verify_broker_response


EVIDENCE_SCHEMA = "mission.skill-replay-evidence.v1"
EVIDENCE_REF_SCHEMA = "mission.skill-replay-evidence-ref.v1"
EXPERIENCE_SCHEMA = "mission.skill-replay-experience.v1"
_ATTESTED_SCHEMA = "mission.sandbox-broker-attestation.v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_MAX_BYTES = 2 * 1024 * 1024


class SkillReplayEvidenceError(ValueError):
    """Signed Skill Replay evidence is invalid, unsafe, or inconsistent."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8", errors="strict")


def _identity(value: Any, field: str, pattern: re.Pattern[str] = _ID_RE) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise SkillReplayEvidenceError(f"{field} is invalid")
    return value


def _private_directory(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise SkillReplayEvidenceError("evidence root must be absolute and non-symlink")
    try:
        info = path.lstat()
    except OSError as exc:
        raise SkillReplayEvidenceError("evidence root is unavailable") from exc
    if (
        not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
        or info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o077
        or path.resolve(strict=True) != path
    ):
        raise SkillReplayEvidenceError("evidence root must be broker-owned, private and canonical")
    return path


class SkillReplayEvidenceStore:
    """Create-once signed evidence store; never treats worker-supplied flags as proof."""

    def __init__(self, root: Path, *, broker_public_key: bytes, broker_key_id: str):
        self.root = _private_directory(Path(root))
        if not isinstance(broker_key_id, str) or not broker_key_id.strip() or len(broker_key_id) > 128:
            raise SkillReplayEvidenceError("broker_key_id is invalid")
        try:
            Ed25519PublicKey.from_public_bytes(broker_public_key)
        except (ValueError, TypeError) as exc:
            raise SkillReplayEvidenceError("broker public key is invalid") from exc
        self.broker_public_key = bytes(broker_public_key)
        self.broker_key_id = broker_key_id

    def _tenant_dir(self, tenant_id: str, *, create: bool) -> Path:
        tenant = _identity(tenant_id, "tenant_id")
        path = self.root / tenant
        if path.exists() or path.is_symlink():
            try:
                info = path.lstat()
            except OSError as exc:
                raise SkillReplayEvidenceError("tenant evidence directory is unavailable") from exc
            if (
                not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o077
            ):
                raise SkillReplayEvidenceError("tenant evidence directory is unsafe")
        elif create:
            path.mkdir(mode=0o700)
        else:
            raise SkillReplayEvidenceError("tenant evidence directory is unavailable")
        return path

    def _path(self, tenant_id: str, evidence_id: str, *, create: bool) -> Path:
        tenant = self._tenant_dir(tenant_id, create=create)
        return tenant / f"{_identity(evidence_id, 'evidence_id', _UUID_RE)}.json"

    @staticmethod
    def _read_private(path: Path) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            raise SkillReplayEvidenceError("evidence file is unavailable or is a symlink") from exc
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                or info.st_mode & 0o222 or info.st_size > _MAX_BYTES
            ):
                raise SkillReplayEvidenceError("evidence file is unsafe or oversized")
            chunks, remaining = [], _MAX_BYTES + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > _MAX_BYTES:
                raise SkillReplayEvidenceError("evidence file exceeds its size limit")
            return raw
        finally:
            os.close(fd)

    @staticmethod
    def _atomic_create(path: Path, payload: bytes) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_path, 0o400)
            try:
                os.link(temp_path, path)
            except FileExistsError:
                if SkillReplayEvidenceStore._read_private(path) != payload:
                    raise SkillReplayEvidenceError("evidence ID already exists with different signed content")
                return
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            if SkillReplayEvidenceStore._read_private(path) != payload:
                raise SkillReplayEvidenceError("evidence readback verification failed")
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    def _verify_envelope(self, envelope, *, workspace_id, mission_context, skill_binding):
        if not isinstance(envelope, dict):
            raise SkillReplayEvidenceError("Broker attestation envelope is missing")
        request_id = _identity(envelope.get("request_id"), "request_id", _UUID_RE)
        try:
            return verify_broker_response(
                envelope,
                public_key=self.broker_public_key,
                expected_key_id=self.broker_key_id,
                expected_request_id=request_id,
                expected_workspace_id=workspace_id,
                expected_mission_context=mission_context,
                expected_profile_id=SKILL_REPLAY_PROFILE_ID,
                expected_target=f"{skill_binding['skill_id']}@{skill_binding['skill_version']}",
                expected_skill_binding=skill_binding,
            )
        except (ValueError, TypeError) as exc:
            raise SkillReplayEvidenceError("Broker Skill Replay signature or binding is invalid") from exc

    def record(
        self,
        attested_execution: Mapping[str, Any],
        *,
        tenant_id: str,
        workspace_id: str,
        mission_context: Mapping[str, Any],
        skill_binding: Mapping[str, Any],
    ) -> dict[str, str]:
        """Verify, bind and atomically persist one Broker-attested Skill Replay."""
        if not isinstance(attested_execution, Mapping) or set(attested_execution) != {
            "schema_version", "attestation", "result", "skill_replay_output",
        } or attested_execution.get("schema_version") != _ATTESTED_SCHEMA:
            raise SkillReplayEvidenceError("attested execution has unsupported or missing fields")
        required_context = {"tenant_id", "mission_run_id", "node_id", "task_id"}
        if not isinstance(mission_context, Mapping) or set(mission_context) != required_context:
            raise SkillReplayEvidenceError("Mission context has unsupported or missing fields")
        context = {
            key: _identity(mission_context[key], f"mission_context.{key}")
            for key in sorted(required_context)
        }
        tenant = _identity(tenant_id, "tenant_id")
        if context["tenant_id"] != tenant:
            raise SkillReplayEvidenceError("evidence tenant does not match Mission context")
        workspace = _identity(workspace_id, "workspace_id")
        if not isinstance(skill_binding, Mapping):
            raise SkillReplayEvidenceError("Skill binding is missing")
        binding = dict(skill_binding)
        if binding.get("mission_context") != context:
            raise SkillReplayEvidenceError("Skill binding does not match Mission context")
        envelope = attested_execution["attestation"]
        result = self._verify_envelope(
            envelope, workspace_id=workspace, mission_context=context, skill_binding=binding,
        )
        output = envelope.get("skill_replay_output") if isinstance(envelope, dict) else None
        if attested_execution.get("result") != result or attested_execution.get("skill_replay_output") != output:
            raise SkillReplayEvidenceError("attested execution projection does not match signed Broker response")
        evidence_id = _identity(envelope.get("request_id"), "evidence_id", _UUID_RE)
        path = self._path(tenant, evidence_id, create=True)
        if path.exists() or path.is_symlink():
            existing = self.load_verified(tenant_id=tenant, evidence_id=evidence_id)
            if existing["broker_attestation"] != envelope:
                raise SkillReplayEvidenceError("evidence ID already exists with different signed content")
            digest = existing["evidence_sha256"]
            return {
                "schema_version": EVIDENCE_REF_SCHEMA, "evidence_id": evidence_id,
                "tenant_id": tenant, "sha256": digest, "relative_path": f"{tenant}/{evidence_id}.json",
            }
        record = {
            "schema_version": EVIDENCE_SCHEMA,
            "evidence_id": evidence_id,
            "tenant_id": tenant,
            "workspace_id": workspace,
            "mission_context": context,
            "skill_binding": binding,
            "execution_result": result,
            "skill_replay_output": output,
            "broker_attestation": envelope,
        }
        record_bytes = _canonical(record)
        digest = hashlib.sha256(record_bytes).hexdigest()
        payload = _canonical({"record": record, "record_sha256": digest})
        if len(payload) > _MAX_BYTES:
            raise SkillReplayEvidenceError("Skill Replay evidence exceeds its storage limit")
        self._atomic_create(path, payload)
        return {
            "schema_version": EVIDENCE_REF_SCHEMA, "evidence_id": evidence_id,
            "tenant_id": tenant, "sha256": digest, "relative_path": f"{tenant}/{evidence_id}.json",
        }

    def load_verified(self, *, tenant_id: str, evidence_id: str) -> dict[str, Any]:
        """Read evidence and re-verify the Broker signature, tenant and task binding."""
        path = self._path(tenant_id, evidence_id, create=False)
        try:
            wrapper = json.loads(self._read_private(path).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SkillReplayEvidenceError("evidence file is malformed") from exc
        if not isinstance(wrapper, dict) or set(wrapper) != {"record", "record_sha256"}:
            raise SkillReplayEvidenceError("evidence wrapper is malformed")
        record = wrapper.get("record")
        if not isinstance(record, dict) or set(record) != {
            "schema_version", "evidence_id", "tenant_id", "workspace_id", "mission_context",
            "skill_binding", "execution_result", "skill_replay_output", "broker_attestation",
        }:
            raise SkillReplayEvidenceError("evidence record is malformed")
        try:
            digest = hashlib.sha256(_canonical(record)).hexdigest()
        except (TypeError, ValueError, UnicodeError) as exc:
            raise SkillReplayEvidenceError("evidence record is not canonical JSON") from exc
        if wrapper.get("record_sha256") != digest:
            raise SkillReplayEvidenceError("evidence record digest mismatch")
        if (
            record.get("schema_version") != EVIDENCE_SCHEMA
            or record.get("tenant_id") != tenant_id
            or record.get("evidence_id") != evidence_id
        ):
            raise SkillReplayEvidenceError("evidence identity does not match lookup")
        context, binding = record.get("mission_context"), record.get("skill_binding")
        workspace = _identity(record.get("workspace_id"), "workspace_id")
        if not isinstance(context, dict) or not isinstance(binding, dict):
            raise SkillReplayEvidenceError("evidence lineage is invalid")
        if context.get("tenant_id") != tenant_id or binding.get("mission_context") != context:
            raise SkillReplayEvidenceError("evidence crosses tenant or Mission boundaries")
        verified_result = self._verify_envelope(
            record.get("broker_attestation"), workspace_id=workspace,
            mission_context=context, skill_binding=binding,
        )
        envelope = record["broker_attestation"]
        if (
            envelope.get("request_id") != evidence_id
            or record.get("execution_result") != verified_result
            or record.get("skill_replay_output") != envelope.get("skill_replay_output")
        ):
            raise SkillReplayEvidenceError("evidence projection does not match signed envelope")
        return {**record, "evidence_sha256": digest}

    def record_experience(
        self, workspace: Path, *, tenant_id: str, evidence_id: str,
        domain: str, task_type: str, input_summary: str,
    ):
        """Persist a tenant Experience linked to verified evidence; reflection stays explicit."""
        from .learning import Experience, ExperienceStore

        record = self.load_verified(tenant_id=tenant_id, evidence_id=evidence_id)
        result, output, binding = (
            record["execution_result"], record["skill_replay_output"], record["skill_binding"],
        )
        succeeded, timed_out = result["execution_succeeded"] is True, result["timed_out"] is True
        error = output.get("error")
        if not succeeded and not isinstance(error, dict):
            error = {
                "type": "TimeoutError" if timed_out else "SkillReplayError",
                "message": "Skill Replay did not complete successfully",
            }
        status = "succeeded" if succeeded else ("timed_out" if timed_out else "failed")
        value_digest = (
            hashlib.sha256(_canonical({"value": output.get("value")})).hexdigest()
            if succeeded else None
        )
        replay = {
            "schema_version": EXPERIENCE_SCHEMA,
            "evidence_id": evidence_id,
            "evidence_sha256": record["evidence_sha256"],
            "tenant_id": tenant_id,
            "mission_run_id": record["mission_context"]["mission_run_id"],
            "mission_node_id": record["mission_context"]["node_id"],
            "task_id": record["mission_context"]["task_id"],
            "skill_id": binding["skill_id"],
            "skill_version": binding["skill_version"],
            "content_sha256": binding["content_sha256"],
            "trust_level": binding["trust_level"],
            "broker_request_id": evidence_id,
            "execution_success": succeeded,
            "execution_status": status,
            "exit_code": result["exit_code"],
            "timed_out": timed_out,
            "observed_output": {
                "stdout_sha256": result["stdout"]["sha256"],
                "stderr_sha256": result["stderr"]["sha256"],
                "value_sha256": value_digest,
            },
            "failure": error if not succeeded else None,
            "reflection": {
                "status": "pending",
                "error_reason": error if not succeeded else None,
                "reality": "broker_signed_isolated_execution_observation",
                "reusable_experience": None,
            },
        }
        experience_id = f"skill-replay-{evidence_id}"
        store = ExperienceStore(Path(workspace), tenant_id)
        existing = next((item for item in store.load_by_domain(domain, limit=1000) if item.id == experience_id), None)
        if existing is not None:
            metadata = existing.metadata if isinstance(existing.metadata, dict) else {}
            if metadata.get("skill_replay") != replay:
                raise SkillReplayEvidenceError("Experience ID already exists with different Skill Replay evidence")
            return existing
        summary = (
            f"Skill Replay succeeded; signed evidence {evidence_id}" if succeeded
            else f"Skill Replay {status}: {error.get('type', 'unknown')} - {error.get('message', '')}"
        )
        experience = Experience(
            id=experience_id, domain=domain, task_type=task_type,
            input_summary=str(input_summary or "")[:512], output_summary=summary[:512],
            quality_score=1.0 if succeeded else 0.0, metadata={"skill_replay": replay},
        )
        store.save(experience)
        return experience


__all__ = [
    "EVIDENCE_SCHEMA", "EVIDENCE_REF_SCHEMA", "EXPERIENCE_SCHEMA",
    "SkillReplayEvidenceError", "SkillReplayEvidenceStore",
]
