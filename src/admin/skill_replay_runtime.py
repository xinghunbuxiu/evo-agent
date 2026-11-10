"""Configured Mission entry point for Broker-isolated Skill Replay.

Replay is opt-in: ordinary Mission execution remains available when the Broker
is not configured. Candidate code is parsed in-process but is only executed by
the separately managed Sandbox Broker.
"""
from __future__ import annotations

import ast
import logging
import os
import re
import stat
from pathlib import Path
from typing import Mapping

from core import Skill
from core.execution_profiles import ExecutionProfileSpec, MAX_OUTPUT_BYTES
from core.sandbox_broker_protocol import SKILL_REPLAY_PROFILE_ID
from core.sandbox_broker_transport import stage_skill_candidate_via_broker
from core.skill_replay_contract import build_skill_replay_binding
from core.skill_replay_evidence_store import SkillReplayEvidenceStore
from core.skill_replay_mission import SkillReplayMissionAdapter
from admin.knowledge_runtime import load_local_skill_payload

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


class SkillReplayRuntimeConfigurationError(ValueError):
    """The optional Mission-to-Broker replay configuration is unsafe or incomplete."""


class SkillReplayRuntime:
    def __init__(self, *, workspace: Path, socket_path: str, workspace_id: str,
                 broker_public_key: bytes, broker_key_id: str,
                 evidence_store: SkillReplayEvidenceStore):
        self.workspace = Path(workspace)
        self.socket_path = socket_path
        self.workspace_id = workspace_id
        self.broker_public_key = bytes(broker_public_key)
        self.broker_key_id = broker_key_id
        self.evidence_store = evidence_store
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
        if str(mission_run.get("tenant_id") or "default") != tenant_id:
            raise PermissionError("Mission tenant does not match replay tenant")

        plan = mission_run.get("plan") if isinstance(mission_run.get("plan"), dict) else {}
        nodes = plan.get("nodes") if isinstance(plan.get("nodes"), list) else []
        if not any(isinstance(node, dict) and str(node.get("id") or "") == node_id for node in nodes):
            raise ValueError("Mission node does not belong to this Mission run")

        payload = load_local_skill_payload(self.workspace, tenant_id, skill_id)
        if not isinstance(payload, dict):
            raise FileNotFoundError("Skill candidate was not found in this tenant")
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
        LOGGER.info(
            "Mission Skill Replay recorded mission_run_id=%s node_id=%s skill_id=%s execution_succeeded=%s evidence_id=%s",
            mission_run_id, node_id, skill.id,
            bool(replay.get("result", {}).get("execution_succeeded")),
            replay.get("evidence", {}).get("evidence_id"),
        )
        return {
            "schema_version": "mission.skill-replay-operation.v1",
            "task_id": task_id,
            "skill_binding": binding,
            "stage_receipt": stage_receipt,
            "replay": replay,
        }


def _read_public_key(path_value: str) -> bytes:
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink():
        raise SkillReplayRuntimeConfigurationError("Broker public key path must be absolute and non-symlink")
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o022:
            raise SkillReplayRuntimeConfigurationError("Broker public key file is not trusted")
        raw = path.read_bytes()
    except OSError as exc:
        raise SkillReplayRuntimeConfigurationError("Broker public key file is unavailable") from exc
    if len(raw) != 32:
        raise SkillReplayRuntimeConfigurationError("Broker public key must contain 32 raw Ed25519 bytes")
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
    if not present:
        return None
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
    return SkillReplayRuntime(
        workspace=workspace,
        socket_path=socket_path,
        workspace_id=workspace_id,
        broker_public_key=public_key,
        broker_key_id=broker_key_id,
        evidence_store=evidence_store,
    )


__all__ = [
    "SkillReplayRuntime",
    "SkillReplayRuntimeConfigurationError",
    "create_skill_replay_runtime",
]
