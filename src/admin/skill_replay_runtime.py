"""Configured Mission entry point for Broker-isolated Skill Replay.

Replay is opt-in: ordinary Mission execution remains available when the Broker
is not configured. Candidate code is parsed in-process but is only executed by
the separately managed Sandbox Broker.
"""
from __future__ import annotations

import ast
import json
import logging
import os
import re
import stat
import uuid
from pathlib import Path
from typing import Mapping

from core import Skill
from core.execution_profiles import ExecutionProfileSpec, MAX_OUTPUT_BYTES
from core.sandbox_broker_protocol import SKILL_REPLAY_PROFILE_ID, broker_response_sha256
from core.sandbox_broker_transport import (
    promote_skill_candidate_via_broker,
    stage_skill_candidate_via_broker,
)
from core.skill_validator import VALIDATION_REQUEST_SCHEMA
from core.skill_validator_transport import request_skill_validation
from core.skill_replay_contract import build_skill_replay_binding
from core.skill_replay_evidence_store import SkillReplayEvidenceStore
from core.skill_replay_mission import SkillReplayMissionAdapter

LOGGER = logging.getLogger("evo.skill_replay")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_WORKSPACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CONFIG_ENV = {
    "socket_path": "EVO_SKILL_REPLAY_BROKER_SOCKET",
    "workspace_id": "EVO_SKILL_REPLAY_WORKSPACE_ID",
    "broker_public_key": "EVO_SKILL_REPLAY_BROKER_PUBLIC_KEY",
    "broker_key_id": "EVO_SKILL_REPLAY_BROKER_KEY_ID",
    "evidence_root": "EVO_SKILL_REPLAY_EVIDENCE_ROOT",
}
_VALIDATOR_CONFIG_ENV = {
    "validator_socket_path": "EVO_SKILL_REPLAY_VALIDATOR_SOCKET",
    "validator_public_key": "EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY",
    "validator_key_id": "EVO_SKILL_REPLAY_VALIDATOR_KEY_ID",
}
_VALIDATED_TRUST_LEVEL = "verified"


class SkillReplayRuntimeConfigurationError(ValueError):
    """The optional Mission-to-Broker replay configuration is unsafe or incomplete."""


def _deterministic_request_id(operation: str, identity: Mapping) -> str:
    """Bind Broker idempotency to the exact candidate or signed promotion evidence."""
    payload = json.dumps(
        {"operation": operation, "identity": dict(identity)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    )
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL, f"evo-agent:skill-replay:{payload}",
    ))


def _load_draft_skill_payload(workspace: Path, tenant_id: str, skill_id: str) -> dict | None:
    """Read only a tenant-local draft file without following symlinks."""
    workspace_root = Path(workspace).resolve(strict=True)
    tenants_root = workspace_root / ".tenants"
    tenant_root = tenants_root / tenant_id
    if tenants_root.is_symlink() or tenant_root.is_symlink():
        raise ValueError("tenant Skill storage must not contain symlink directories")
    candidates = (
        tenant_root / "skills" / "draft" / f"{skill_id}.json",
        tenant_root / ".skill_cache" / "drafts" / f"{skill_id}.json",
    )
    for path in candidates:
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ValueError("Skill candidate file is unavailable or unsafe") from exc
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid not in {0, os.geteuid()}
                or info.st_mode & 0o022
                or info.st_size > 512 * 1024
            ):
                raise ValueError("Skill candidate file is not a trusted bounded regular file")
            resolved_tenant = tenant_root.resolve(strict=True)
            resolved_tenant.relative_to(workspace_root)
            resolved = path.resolve(strict=True)
            resolved.relative_to(resolved_tenant)
            chunks = []
            remaining = 512 * 1024 + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > 512 * 1024:
                raise ValueError("Skill candidate file exceeds its size limit")
        except (OSError, ValueError) as exc:
            if isinstance(exc, ValueError):
                raise
            raise ValueError("Skill candidate file could not be read safely") from exc
        finally:
            os.close(fd)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Skill candidate file is not valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Skill candidate file must contain an object")
        return payload
    return None


class SkillReplayRuntime:
    def __init__(self, *, workspace: Path, socket_path: str, workspace_id: str,
                 broker_public_key: bytes, broker_key_id: str,
                 evidence_store: SkillReplayEvidenceStore,
                 validator_socket_path: str | None = None,
                 validator_public_key: bytes | None = None,
                 validator_key_id: str | None = None):
        self.workspace = Path(workspace)
        self.socket_path = socket_path
        self.workspace_id = workspace_id
        self.broker_public_key = bytes(broker_public_key)
        self.broker_key_id = broker_key_id
        self.evidence_store = evidence_store
        self.validator_socket_path = validator_socket_path
        self.validator_public_key = bytes(validator_public_key) if validator_public_key is not None else None
        self.validator_key_id = validator_key_id
        if any(value is not None for value in (validator_socket_path, validator_public_key, validator_key_id)):
            if not validator_socket_path or self.validator_public_key is None or not validator_key_id:
                raise ValueError("independent Validator configuration must be complete")
        self.adapter = SkillReplayMissionAdapter(
            socket_path=socket_path,
            workspace_id=workspace_id,
            broker_public_key=broker_public_key,
            broker_key_id=broker_key_id,
            evidence_store=evidence_store,
            experience_workspace=self.workspace,
        )

    @staticmethod
    def _validate_executable_contract(skill: Skill) -> None:
        parameters = skill.parameters if isinstance(skill.parameters, dict) else {}
        contract = parameters.get("execution_contract")
        if not isinstance(contract, dict) or contract.get("kind") != "python_run_context" or contract.get("replay_eligible") is not True:
            raise ValueError("Skill is a Recipe or lacks the explicit python_run_context execution contract")
        if skill.trust_level.value != "draft":
            raise ValueError("only draft Skill candidates may enter the replay staging flow")
        try:
            tree = ast.parse(skill.code, mode="exec")
        except (SyntaxError, ValueError, TypeError) as exc:
            raise ValueError("Skill code is not valid Python source") from exc
        run_functions = [
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run"
        ]
        if len(run_functions) != 1 or isinstance(run_functions[0], ast.AsyncFunctionDef):
            raise ValueError("executable Skill must define exactly one synchronous run(context) function")
        arguments = run_functions[0].args
        if (
            arguments.posonlyargs
            or len(arguments.args) != 1
            or arguments.vararg is not None
            or arguments.kwarg is not None
            or arguments.kwonlyargs
            or arguments.args[0].arg != "context"
        ):
            raise ValueError("executable Skill entry point must have exactly one argument named context")

    def replay_candidate(self, *, tenant_id: str, mission_run: Mapping,
                         node_id: str, task_id: str, skill_id: str) -> dict:
        if not isinstance(tenant_id, str) or not _ID_RE.fullmatch(tenant_id):
            raise ValueError("tenant_id is invalid")
        if not isinstance(mission_run, Mapping):
            raise ValueError("Mission run is required")
        mission_run_id = str(mission_run.get("mission_run_id") or "").strip()
        if not _ID_RE.fullmatch(mission_run_id):
            raise ValueError("Mission run identity is invalid")
        if not isinstance(node_id, str) or not _ID_RE.fullmatch(node_id):
            raise ValueError("Mission node identity is invalid")
        if not isinstance(task_id, str) or not _ID_RE.fullmatch(task_id):
            raise ValueError("Replay task identity is invalid")
        if not isinstance(skill_id, str) or not _ID_RE.fullmatch(skill_id):
            raise ValueError("skill_id is invalid")
        mission_tenant_id = mission_run.get("tenant_id")
        if not isinstance(mission_tenant_id, str) or not _ID_RE.fullmatch(mission_tenant_id):
            raise ValueError("Mission run tenant identity is missing or invalid")
        if mission_tenant_id != tenant_id:
            raise PermissionError("Mission tenant does not match replay tenant")

        plan = mission_run.get("plan") if isinstance(mission_run.get("plan"), dict) else {}
        nodes = plan.get("nodes") if isinstance(plan.get("nodes"), list) else []
        if not any(isinstance(node, dict) and str(node.get("id") or "") == node_id for node in nodes):
            raise ValueError("Mission node does not belong to this Mission run")

        payload = _load_draft_skill_payload(self.workspace, tenant_id, skill_id)
        if not isinstance(payload, dict):
            raise FileNotFoundError("Draft Skill candidate was not found in this tenant")
        skill = Skill.from_dict(payload)
        if skill.id != skill_id:
            raise ValueError("loaded Skill identity does not match the requested candidate")
        self._validate_executable_contract(skill)
        parameters = skill.parameters if isinstance(skill.parameters, dict) else {}
        if (
            str(parameters.get("mission_run_id") or "") != mission_run_id
            or str(parameters.get("mission_node_id") or "") != node_id
        ):
            raise PermissionError("Skill candidate provenance does not match this Mission node")

        context = {
            "tenant_id": tenant_id,
            "mission_run_id": mission_run_id,
            "node_id": node_id,
            "task_id": task_id,
        }
        binding = build_skill_replay_binding(skill, context)
        stage_receipt = stage_skill_candidate_via_broker(
            self.socket_path,
            self.workspace_id,
            tenant_id=tenant_id,
            mission_context=context,
            skill_id=skill.id,
            skill_version=skill.version,
            code=skill.code,
            public_key=self.broker_public_key,
            expected_key_id=self.broker_key_id,
            request_id=_deterministic_request_id("stage", {
                "mission_context": context,
                "skill_id": skill.id,
                "skill_version": skill.version,
                "content_sha256": binding["content_sha256"],
            }),
        )
        spec = ExecutionProfileSpec(
            profile_id=SKILL_REPLAY_PROFILE_ID,
            target=f"{skill.id}@{skill.version}",
            argv=(),
            cwd=self.workspace,
            timeout_seconds=60,
            max_output_bytes=MAX_OUTPUT_BYTES,
            network_access=False,
        )
        LOGGER.info(
            "Mission Skill Replay started mission_run_id=%s node_id=%s skill_id=%s version=%s task_id=%s",
            mission_run_id, node_id, skill.id, skill.version, task_id,
        )
        replay = self.adapter.execute(
            spec,
            tenant_id=tenant_id,
            mission_context=context,
            skill_binding=binding,
            domain=skill.domain,
            task_type="skill_replay",
            input_summary=f"Replay {skill.id}@{skill.version} for Mission node {node_id}",
        )
        validation = {"status": "not_configured"}
        promotion = {"status": "not_attempted"}
        if replay.get("result", {}).get("execution_succeeded") is not True:
            validation = {"status": "blocked", "reason": "broker_execution_failed"}
            promotion = {"status": "blocked", "reason": "broker_execution_failed"}
        elif self.validator_socket_path and self.validator_public_key and self.validator_key_id:
            try:
                evidence_id = str(replay.get("evidence", {}).get("evidence_id") or "")
                if not evidence_id:
                    raise ValueError("verified Broker evidence reference is missing")
                verified_evidence = self.evidence_store.load_verified(
                    tenant_id=tenant_id, evidence_id=evidence_id,
                )
                broker_attestation = verified_evidence.get("broker_attestation")
                if not isinstance(broker_attestation, dict):
                    raise ValueError("verified Broker response envelope is missing")
                broker_request_id = broker_attestation.get("request_id", evidence_id)
                if broker_request_id != evidence_id:
                    raise ValueError("Broker request identity does not match persisted evidence ID")
                broker_attestation_sha256 = broker_response_sha256(broker_attestation)
                validation_request_id = str(uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    "evo-agent:skill-validation:"
                    + ":".join((
                        tenant_id, mission_run_id, node_id, task_id,
                        broker_request_id, broker_attestation_sha256,
                        skill.id, skill.version, binding["content_sha256"],
                    )),
                ))
                validation_request = {
                    "schema_version": VALIDATION_REQUEST_SCHEMA,
                    "request_id": validation_request_id,
                    "workspace_id": self.workspace_id,
                    "mission_context": context,
                    "skill_binding": binding,
                    "trust_level": _VALIDATED_TRUST_LEVEL,
                    "broker_attestation": broker_attestation,
                }
                validation_attestation = request_skill_validation(
                    self.validator_socket_path,
                    request=validation_request,
                    validator_public_key=self.validator_public_key,
                    expected_key_id=self.validator_key_id,
                    expected_identity={
                        "workspace_id": self.workspace_id,
                        "tenant_id": tenant_id,
                        "mission_run_id": mission_run_id,
                        "node_id": node_id,
                        "task_id": task_id,
                        "broker_request_id": broker_request_id,
                        "broker_attestation_sha256": broker_attestation_sha256,
                        "skill_id": skill.id,
                        "skill_version": skill.version,
                        "content_sha256": binding["content_sha256"],
                        "trust_level": _VALIDATED_TRUST_LEVEL,
                    },
                )
                validation = {
                    "status": "passed",
                    "validation_id": validation_attestation["validation_id"],
                    "validator_id": validation_attestation["validator_id"],
                    "policy_id": validation_attestation["policy_id"],
                    "broker_request_id": validation_attestation.get("broker_request_id", broker_request_id),
                    "broker_attestation_sha256": validation_attestation.get("broker_attestation_sha256", broker_attestation_sha256),
                    "checks_sha256": validation_attestation.get("checks_sha256"),
                }
            except Exception as exc:
                validation = {"status": "rejected", "error_type": type(exc).__name__}
                promotion = {"status": "blocked", "reason": "independent_validation_failed"}
            else:
                try:
                    receipt = promote_skill_candidate_via_broker(
                        self.socket_path,
                        self.workspace_id,
                        mission_context=context,
                        skill_id=skill.id,
                        skill_version=skill.version,
                        content_sha256=binding["content_sha256"],
                        trust_level=_VALIDATED_TRUST_LEVEL,
                        validation_attestation=validation_attestation,
                        public_key=self.broker_public_key,
                        expected_key_id=self.broker_key_id,
                        request_id=_deterministic_request_id("promotion", {
                            "mission_context": context,
                            "skill_id": skill.id,
                            "skill_version": skill.version,
                            "content_sha256": binding["content_sha256"],
                            "validation_attestation": validation_attestation,
                        }),
                    )
                    promotion = {
                        "status": "published",
                        "artifact": receipt["artifact"],
                        "validation_provenance": receipt.get("validation_provenance"),
                    }
                except Exception as exc:
                    promotion = {"status": "failed", "error_type": type(exc).__name__}
        LOGGER.info(
            "Mission Skill Replay recorded mission_run_id=%s node_id=%s skill_id=%s execution_succeeded=%s evidence_id=%s validation_status=%s promotion_status=%s",
            mission_run_id, node_id, skill.id,
            bool(replay.get("result", {}).get("execution_succeeded")),
            replay.get("evidence", {}).get("evidence_id"),
            validation.get("status"), promotion.get("status"),
        )
        return {
            "schema_version": "mission.skill-replay-operation.v1",
            "task_id": task_id,
            "skill_binding": binding,
            "stage_receipt": stage_receipt,
            "replay": replay,
            "validation": validation,
            "promotion": promotion,
        }


def _read_public_key(path_value: str, *, label: str = "Broker") -> bytes:
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink():
        raise SkillReplayRuntimeConfigurationError(f"{label} public key path must be absolute and non-symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise SkillReplayRuntimeConfigurationError(f"{label} public key file is unavailable or unsafe") from exc
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid not in {0, os.geteuid()}
            or info.st_mode & 0o022
            or path.resolve(strict=True) != path
        ):
            raise SkillReplayRuntimeConfigurationError(f"{label} public key file is not trusted")
        raw = os.read(fd, 33)
    except OSError as exc:
        raise SkillReplayRuntimeConfigurationError(f"{label} public key file could not be read safely") from exc
    finally:
        os.close(fd)
    if len(raw) != 32:
        raise SkillReplayRuntimeConfigurationError(f"{label} public key must contain 32 raw Ed25519 bytes")
    return raw


def _validate_evidence_root(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink():
        raise SkillReplayRuntimeConfigurationError("Evidence root must be absolute and non-symlink")
    try:
        info = path.lstat()
    except OSError as exc:
        raise SkillReplayRuntimeConfigurationError("Evidence root must be provisioned before startup") from exc
    if (
        not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
        or info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o077
        or path.resolve(strict=True) != path
    ):
        raise SkillReplayRuntimeConfigurationError("Evidence root must be private, trusted and canonical")
    return path


def create_skill_replay_runtime(*, workspace: Path, environ: Mapping[str, str] | None = None) -> SkillReplayRuntime | None:
    """Build the optional runtime; no configuration leaves normal Mission untouched."""
    values = dict(os.environ if environ is None else environ)
    configured = {key: str(values.get(env_name) or "").strip() for key, env_name in _CONFIG_ENV.items()}
    present = {key for key, value in configured.items() if value}
    validator_configured = {
        key: str(values.get(env_name) or "").strip()
        for key, env_name in _VALIDATOR_CONFIG_ENV.items()
    }
    validator_present = {key for key, value in validator_configured.items() if value}
    if not present and not validator_present:
        return None
    if not present and validator_present:
        raise SkillReplayRuntimeConfigurationError("Validator configuration requires the Broker runtime")
    missing = sorted(set(_CONFIG_ENV) - present)
    if missing:
        missing_names = ", ".join(_CONFIG_ENV[key] for key in missing)
        raise SkillReplayRuntimeConfigurationError(f"Skill Replay configuration is incomplete: {missing_names}")
    socket_path = configured["socket_path"]
    if not Path(socket_path).is_absolute() or "\x00" in socket_path:
        raise SkillReplayRuntimeConfigurationError("Broker socket path must be absolute")
    workspace_id = configured["workspace_id"]
    if not _WORKSPACE_RE.fullmatch(workspace_id):
        raise SkillReplayRuntimeConfigurationError("Broker workspace ID is invalid")
    broker_key_id = configured["broker_key_id"]
    if not _ID_RE.fullmatch(broker_key_id):
        raise SkillReplayRuntimeConfigurationError("Broker key ID is invalid")
    public_key = _read_public_key(configured["broker_public_key"])
    evidence_root = _validate_evidence_root(configured["evidence_root"])
    evidence_store = SkillReplayEvidenceStore(
        evidence_root,
        broker_public_key=public_key,
        broker_key_id=broker_key_id,
    )
    validator_socket_path = None
    validator_public_key = None
    validator_key_id = None
    if validator_present:
        missing_validator = sorted(set(_VALIDATOR_CONFIG_ENV) - validator_present)
        if missing_validator:
            missing_names = ", ".join(_VALIDATOR_CONFIG_ENV[key] for key in missing_validator)
            raise SkillReplayRuntimeConfigurationError(f"Validator configuration is incomplete: {missing_names}")
        validator_socket_path = validator_configured["validator_socket_path"]
        if not Path(validator_socket_path).is_absolute() or "\x00" in validator_socket_path:
            raise SkillReplayRuntimeConfigurationError("Validator socket path must be absolute")
        validator_key_id = validator_configured["validator_key_id"]
        if not _ID_RE.fullmatch(validator_key_id):
            raise SkillReplayRuntimeConfigurationError("Validator key ID is invalid")
        validator_public_key = _read_public_key(validator_configured["validator_public_key"], label="Validator")
    return SkillReplayRuntime(
        workspace=workspace,
        socket_path=socket_path,
        workspace_id=workspace_id,
        broker_public_key=public_key,
        broker_key_id=broker_key_id,
        evidence_store=evidence_store,
        validator_socket_path=validator_socket_path,
        validator_public_key=validator_public_key,
        validator_key_id=validator_key_id,
    )


__all__ = [
    "SkillReplayRuntime",
    "SkillReplayRuntimeConfigurationError",
    "create_skill_replay_runtime",
]
