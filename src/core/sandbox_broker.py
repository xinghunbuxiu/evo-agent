"""Core request validation and replay protection for a privileged sandbox broker.

This module is the broker-side policy core. A deployment must still wrap it in
a root-owned Unix socket service and inject a container executor whose isolation
policy is enforced by the host. No Docker or subprocess fallback is provided.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import json
import os
import re
import sqlite3
import stat
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Callable, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .execution_profiles import ExecutionProfileSpec, MAX_OUTPUT_BYTES, resolve_execution_profile
from .execution_results import build_execution_result
from .sandbox_broker_protocol import (
    BROKER_REQUEST_SCHEMA,
    BROKER_RESPONSE_SCHEMA,
    BROKER_SIGNATURE_ALGORITHM,
    _canonical_json,
    _normalize_mission_context,
    _normalize_skill_binding,
    SKILL_ARTIFACT_RESOLUTION_SCHEMA,
    SKILL_REPLAY_PROFILE_ID,
    _normalize_skill_replay_output,
    SKILL_REPLAY_OUTPUT_SCHEMA,
    BROKER_SIGNATURE_ALGORITHM,
    SKILL_CANDIDATE_STAGE_REQUEST_SCHEMA,
    SKILL_CANDIDATE_STAGE_RESPONSE_SCHEMA,
    SKILL_CANDIDATE_ARTIFACT_SCHEMA,
    SKILL_CANDIDATE_PROMOTION_REQUEST_SCHEMA,
    SKILL_CANDIDATE_PROMOTION_RESPONSE_SCHEMA,
)
from .skill_artifact_store import ARTIFACT_SCHEMA
from .sandbox_runner import RunnerProcessOutput


_REQUEST_FIELDS = {
    "schema_version", "request_id", "workspace_id", "mission_context", "skill_binding",
    "profile_id", "target", "timeout_seconds",
}
_WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TENANT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class BrokerRequestRejected(ValueError):
    """A broker request failed schema, policy, or replay validation."""


class BrokerReplayStore:
    """Durable request ledger with exact signed-response replay.

    A claimed request without a stored response is indeterminate and can never
    be executed again automatically. Completed requests return their original
    response bytes (decoded as JSON), preserving the original signature.
    """

    MAX_RESPONSE_BYTES = 1024 * 1024

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        if self.database_path.is_symlink():
            raise ValueError("broker replay database must not be a symlink")
        self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.database_path.parent.is_symlink():
            raise ValueError("broker replay directory must not be a symlink")
        os.chmod(self.database_path.parent, 0o700)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(
            str(self.database_path), timeout=10, isolation_level=None,
        )
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self):
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS broker_requests (
                    request_id TEXT PRIMARY KEY,
                    request_digest TEXT NOT NULL,
                    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    response_json TEXT,
                    workspace_id TEXT, tenant_id TEXT, mission_run_id TEXT, node_id TEXT, task_id TEXT
                )
                """
            )
            columns = {
                row[1] for row in connection.execute(
                    "PRAGMA table_info(broker_requests)"
                ).fetchall()
            }
            migrations = {"response_json":"TEXT","workspace_id":"TEXT","tenant_id":"TEXT","mission_run_id":"TEXT","node_id":"TEXT","task_id":"TEXT"}
            for name, sql_type in migrations.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE broker_requests ADD COLUMN {name} {sql_type}")
        finally:
            connection.close()
        if self.database_path.exists():
            os.chmod(self.database_path, 0o600)

    @staticmethod
    def _digest(request: dict) -> str:
        return hashlib.sha256(_canonical_json(request)).hexdigest()

    def claim(
        self, request_id: str, request: dict, *,
        allow_indeterminate_resume: bool = False,
    ) -> dict | None:
        """Claim a request or return its exact cached response.

        Incomplete requests remain indeterminate by default. A caller may
        explicitly resume only an operation whose side effects are independently
        create-once/idempotent; the request digest must still match exactly.
        """

        digest = self._digest(request)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT request_digest, response_json FROM broker_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if existing is not None:
                connection.execute("COMMIT")
                if existing[0] != digest:
                    raise BrokerRequestRejected(
                        "request_id was reused with a different request digest"
                    )
                if existing[1] is None:
                    if allow_indeterminate_resume:
                        return None
                    raise BrokerRequestRejected(
                        "request_id is indeterminate; operator review is required"
                    )
                try:
                    response = json.loads(existing[1])
                except (TypeError, json.JSONDecodeError) as exc:
                    raise BrokerRequestRejected(
                        "cached Broker response is corrupt; operator review is required"
                    ) from exc
                if not isinstance(response, dict):
                    raise BrokerRequestRejected(
                        "cached Broker response is invalid; operator review is required"
                    )
                return response
            context = request.get("mission_context")
            workspace_id = request.get("workspace_id")
            if not isinstance(context, dict) or not isinstance(workspace_id, str):
                raise BrokerRequestRejected("request identity is missing from replay ledger claim")
            identity = tuple(context.get(key) for key in ("tenant_id","mission_run_id","node_id","task_id"))
            if any(not isinstance(value,str) or not value for value in identity):
                raise BrokerRequestRejected("request Mission identity is invalid")
            connection.execute(
                """INSERT INTO broker_requests(request_id,request_digest,workspace_id,tenant_id,mission_run_id,node_id,task_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (request_id,digest,workspace_id,*identity),
            )
            connection.execute("COMMIT")
            return None
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def lookup(self, request_id: str, *, workspace_id: str, mission_context: dict) -> dict:
        """Read an outcome only for its exact persisted Mission identity."""
        if not isinstance(request_id,str) or not _UUID_RE.fullmatch(request_id):
            raise BrokerRequestRejected("request_id is invalid")
        try: context = _normalize_mission_context(mission_context)
        except ValueError as exc: raise BrokerRequestRejected("Mission identity is invalid") from exc
        if not isinstance(workspace_id,str) or not _WORKSPACE_ID_RE.fullmatch(workspace_id):
            raise BrokerRequestRejected("workspace_id is invalid")
        connection=self._connect()
        try:
            row=connection.execute(
                "SELECT response_json,workspace_id,tenant_id,mission_run_id,node_id,task_id FROM broker_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
        finally: connection.close()
        if row is None: return {"status":"not_found"}
        expected=(workspace_id,context["tenant_id"],context["mission_run_id"],context["node_id"],context["task_id"])
        if any(value is None for value in row[1:]) or tuple(row[1:])!=expected:
            raise BrokerRequestRejected("request outcome is not available for this Mission identity")
        if row[0] is None: return {"status":"indeterminate"}
        try: response=json.loads(row[0])
        except (TypeError,json.JSONDecodeError) as exc:
            raise BrokerRequestRejected("cached Broker response is corrupt; operator review is required") from exc
        if not isinstance(response,dict) or response.get("request_id")!=request_id:
            raise BrokerRequestRejected("cached Broker response is invalid; operator review is required")
        return {"status":"completed","response":response}

    def complete(self, request_id: str, request: dict, response: dict) -> None:
        """Durably cache the signed response before it is sent over the socket."""
        if not isinstance(response, dict):
            raise BrokerRequestRejected("Broker response must be an object")
        encoded = _canonical_json(response).decode("utf-8")
        if len(encoded.encode("utf-8")) > self.MAX_RESPONSE_BYTES:
            raise BrokerRequestRejected("Broker response exceeds the durable cache limit")
        digest = self._digest(request)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT request_digest, response_json FROM broker_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is None or row[0] != digest:
                raise BrokerRequestRejected("Broker request claim is missing or mismatched")
            if row[1] is not None:
                if row[1] != encoded:
                    raise BrokerRequestRejected("Broker completed response is immutable")
            else:
                connection.execute(
                    "UPDATE broker_requests SET response_json = ? WHERE request_id = ? AND response_json IS NULL",
                    (encoded, request_id),
                )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

def validate_broker_request(request: object) -> dict:
    """Validate the exact wire shape before workspace lookup or execution."""
    if not isinstance(request, dict) or set(request) != _REQUEST_FIELDS:
        raise BrokerRequestRejected("broker request has unsupported or missing fields")
    if request.get("schema_version") != BROKER_REQUEST_SCHEMA:
        raise BrokerRequestRejected("unsupported broker request schema")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not _UUID_RE.fullmatch(request_id):
        raise BrokerRequestRejected("request_id must be a canonical UUID")
    workspace_id = request.get("workspace_id")
    if not isinstance(workspace_id, str) or not _WORKSPACE_ID_RE.fullmatch(workspace_id):
        raise BrokerRequestRejected("workspace_id is invalid")
    try:
        mission_context = _normalize_mission_context(request.get("mission_context"))
    except ValueError as exc:
        raise BrokerRequestRejected("mission_context is invalid") from exc
    profile_id = request.get("profile_id")
    if profile_id not in {"python.unittest", "python.pytest", SKILL_REPLAY_PROFILE_ID}:
        raise BrokerRequestRejected("unsupported execution profile")
    target = request.get("target")
    if not isinstance(target, str) or not target or len(target) > 512 or "\x00" in target:
        raise BrokerRequestRejected("execution target is invalid")
    if profile_id == "python.pytest":
        path = PurePosixPath(target)
        if path.is_absolute() or ":" in target or "\\" in target or any(
            part in {"", ".", ".."} for part in target.split("/")
        ):
            raise BrokerRequestRejected("pytest target must be workspace-relative")
    elif profile_id == "python.unittest":
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9]*(?:\.[A-Za-z_][A-Za-z0-9]*)*", target):
            raise BrokerRequestRejected("unittest target must be a dotted module name")
    timeout = request.get("timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 300:
        raise BrokerRequestRejected("timeout_seconds must be between 1 and 300")
    try:
        binding = _normalize_skill_binding(request.get("skill_binding"), expected_context=mission_context)
    except ValueError as exc:
        raise BrokerRequestRejected("skill_binding is invalid") from exc
    if profile_id == SKILL_REPLAY_PROFILE_ID:
        if binding is None:
            raise BrokerRequestRejected("Skill Replay requires an immutable Skill binding")
        if target != f"{binding['skill_id']}@{binding['skill_version']}":
            raise BrokerRequestRejected("Skill Replay target does not match its immutable binding")
    elif binding is not None:
        raise BrokerRequestRejected("generic test-runner requests cannot carry a Skill binding")
    return {**request, "mission_context": mission_context, "skill_binding": binding}


def _validate_workspace_root(raw_root: Path) -> Path:
    """Require a canonical root whose parent chain cannot be replaced by app users.

    The workspace itself may be writable by its owning application account;
    every ancestor must be controlled by root or this dedicated broker UID.
    A root-owned sticky directory (for example /tmp) is allowed as an ancestor.
    """
    root = Path(raw_root)
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("broker workspace root must be absolute and non-symlink")
    resolved = root.resolve(strict=True)
    if resolved != root or not resolved.is_dir():
        raise ValueError("broker workspace root must be a canonical directory")
    parent = resolved.parent
    while True:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValueError("broker workspace parent chain contains a non-directory or symlink")
        if info.st_uid not in {0, os.geteuid()}:
            raise ValueError("broker workspace parent must be controlled by root or broker")
        writable_by_others = bool(info.st_mode & 0o022)
        root_sticky = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
        if writable_by_others and not root_sticky:
            raise ValueError("broker workspace parent is writable by group or other users")
        if parent == Path("/"):
            break
        parent = parent.parent
    return resolved


def _skill_replay_output_from_runner(output: RunnerProcessOutput) -> dict:
    """Accept only the bounded JSON envelope emitted by the isolated replay bootstrap."""
    if output.timed_out:
        return {
            "schema_version": SKILL_REPLAY_OUTPUT_SCHEMA,
            "success": False,
            "value": None,
            "error": {"type": "TimeoutError", "message": "Skill Replay exceeded its execution deadline"},
            "logs": "",
        }
    if not isinstance(output.stdout, bytes) or len(output.stdout) > 32 * 1024:
        raise BrokerRequestRejected("isolated Skill Replay output envelope exceeds its limit")
    available = output.stdout_available_bytes
    if available is not None and (
        isinstance(available, bool) or not isinstance(available, int) or available != len(output.stdout)
    ):
        raise BrokerRequestRejected("isolated Skill Replay output envelope was truncated")
    try:
        envelope = json.loads(output.stdout.decode("utf-8"))
        normalized = _normalize_skill_replay_output(envelope)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise BrokerRequestRejected("isolated Skill Replay returned an invalid structured output envelope") from exc
    if normalized is None:
        raise BrokerRequestRejected("isolated Skill Replay output envelope is missing")
    expected_success = output.exit_code == 0
    if normalized["success"] != expected_success:
        raise BrokerRequestRejected("isolated Skill Replay output conflicts with process exit status")
    return normalized


class SandboxBrokerService:
    """Validate, de-duplicate, execute through an injected isolated runner, sign."""

    def __init__(
        self,
        *,
        workspace_roots: Mapping[str, Path],
        replay_store: BrokerReplayStore,
        executor: Callable[[object], RunnerProcessOutput],
        signing_key: Ed25519PrivateKey,
        key_id: str,
        runner_id: str = "evo-sandbox-broker",
        runner_version: str = "1",
        skill_artifact_store: object | None = None,
        skill_replay_executor: Callable[..., RunnerProcessOutput] | None = None,
        workspace_tenants: Mapping[str, object] | None = None,
    ):
        if not key_id or len(key_id) > 128:
            raise ValueError("broker key_id must be a non-empty bounded value")
        normalized_roots = {}
        for workspace_id, raw_root in workspace_roots.items():
            workspace_id = str(workspace_id)
            if not _WORKSPACE_ID_RE.fullmatch(workspace_id):
                raise ValueError("broker workspace registry contains an unsafe entry")
            normalized_roots[workspace_id] = _validate_workspace_root(Path(raw_root))
        self.workspace_roots = normalized_roots
        self.replay_store = replay_store
        self.executor = executor
        self.signing_key = signing_key
        self.key_id = key_id
        self.runner_id = runner_id
        self.runner_version = runner_version
        self.skill_artifact_store = skill_artifact_store
        self.skill_replay_executor = skill_replay_executor
        self.workspace_tenants = {}
        if workspace_tenants is not None:
            if not isinstance(workspace_tenants, Mapping) or set(workspace_tenants) != set(normalized_roots):
                raise ValueError("workspace_tenants must explicitly cover every registered workspace")
            for workspace_id, raw_tenants in workspace_tenants.items():
                if not isinstance(raw_tenants, (list, tuple, set, frozenset)) or not raw_tenants:
                    raise ValueError("each workspace must have a non-empty tenant allowlist")
                tenants = tuple(raw_tenants)
                if any(not isinstance(tenant, str) or not _TENANT_ID_RE.fullmatch(tenant) for tenant in tenants):
                    raise ValueError("workspace tenant allowlist contains invalid identities")
                if len(set(tenants)) != len(tenants):
                    raise ValueError("workspace tenant allowlist contains duplicate identities")
                self.workspace_tenants[workspace_id] = frozenset(tenants)

    def _authorize_workspace_tenant(self, workspace_id: str, tenant_id: str) -> None:
        allowed = self.workspace_tenants.get(workspace_id, frozenset())
        if tenant_id not in allowed:
            raise BrokerRequestRejected("Mission tenant is not authorized for this workspace")


    def stage_skill_candidate(self, request: object) -> dict:
        """Accept one draft Python Skill into Broker-owned storage and sign its receipt."""
        fields = {
            "schema_version", "request_id", "workspace_id", "mission_context",
            "skill_id", "skill_version", "code",
        }
        if not isinstance(request, dict) or set(request) != fields:
            raise BrokerRequestRejected("Skill candidate stage request has unsupported or missing fields")
        if request.get("schema_version") != SKILL_CANDIDATE_STAGE_REQUEST_SCHEMA:
            raise BrokerRequestRejected("unsupported Skill candidate stage request schema")
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not _UUID_RE.fullmatch(request_id):
            raise BrokerRequestRejected("Skill candidate stage request_id is invalid")
        workspace_id = request.get("workspace_id")
        if not isinstance(workspace_id, str) or workspace_id not in self.workspace_roots:
            raise BrokerRequestRejected("workspace_id is not registered with this broker")
        try:
            context = _normalize_mission_context(request.get("mission_context"))
        except ValueError as exc:
            raise BrokerRequestRejected("Skill candidate Mission context is invalid") from exc
        self._authorize_workspace_tenant(workspace_id, context["tenant_id"])
        skill_id = request.get("skill_id")
        version = request.get("skill_version")
        code = request.get("code")
        if not isinstance(skill_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", skill_id):
            raise BrokerRequestRejected("Skill candidate ID is invalid")
        if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}", version):
            raise BrokerRequestRejected("Skill candidate version is invalid")
        if not isinstance(code, str) or not code.strip():
            raise BrokerRequestRejected("Skill candidate source is empty")
        try:
            code_bytes = code.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise BrokerRequestRejected("Skill candidate source is not valid UTF-8") from exc
        if len(code_bytes) > 256 * 1024:
            raise BrokerRequestRejected("Skill candidate source exceeds the 256 KiB limit")
        try:
            module = ast.parse(code, filename=f"{skill_id}.py", mode="exec")
        except SyntaxError as exc:
            raise BrokerRequestRejected("Skill candidate source is not valid Python") from exc
        class _ModuleRunBindingVisitor(ast.NodeVisitor):
            """Find module-scope writes to run without entering function/class bodies."""

            def __init__(self):
                self.entries = []
                self.other_bindings = []

            def visit_FunctionDef(self, node):
                if node.name == "run":
                    self.entries.append(node)
                # A function body executes later in its own local/global scope.

            def visit_AsyncFunctionDef(self, node):
                if node.name == "run":
                    self.other_bindings.append(node)
                # Do not inspect deferred function bodies.

            def visit_ClassDef(self, node):
                # Class namespace assignments cannot replace the module entrypoint.
                return

            def visit_Name(self, node):
                if node.id == "run" and isinstance(node.ctx, (ast.Store, ast.Del)):
                    self.other_bindings.append(node)

            def visit_Import(self, node):
                for alias in node.names:
                    if (alias.asname or alias.name.split(".", 1)[0]) == "run":
                        self.other_bindings.append(node)

            def visit_ImportFrom(self, node):
                for alias in node.names:
                    if (alias.asname or alias.name) == "run":
                        self.other_bindings.append(node)

        bindings = _ModuleRunBindingVisitor()
        for statement in module.body:
            bindings.visit(statement)
        entry = bindings.entries[0] if len(bindings.entries) == 1 else None
        if (
            entry is None
            or bindings.other_bindings
            or len(entry.args.posonlyargs) + len(entry.args.args) != 1
            or entry.args.vararg is not None
            or entry.args.kwarg is not None
            or entry.args.kwonlyargs
            or entry.args.defaults
            or entry.args.kw_defaults
        ):
            raise BrokerRequestRejected(
                "Skill candidate must define exactly one synchronous module-level run(context)"
            )
        if self.skill_artifact_store is None:
            raise BrokerRequestRejected("Broker Skill Artifact Store is not configured")
        cached_response = self.replay_store.claim(request_id, request)
        if cached_response is not None:
            return cached_response
        candidate = SimpleNamespace(
            id=skill_id, version=version, code=code, trust_level="draft",
        )
        try:
            identity = self.skill_artifact_store.stage_candidate(
                tenant_id=context["tenant_id"], skill=candidate,
            )
        except Exception as exc:
            raise BrokerRequestRejected("Broker could not stage Skill candidate") from exc
        artifact = {
            "schema_version": SKILL_CANDIDATE_ARTIFACT_SCHEMA,
            "tenant_id": context["tenant_id"],
            "skill_id": identity["skill_id"],
            "skill_version": identity["skill_version"],
            "content_sha256": identity["content_sha256"],
            "trust_level": "draft",
        }
        signed_payload = {
            "schema_version": SKILL_CANDIDATE_STAGE_RESPONSE_SCHEMA,
            "request_id": request_id,
            "workspace_id": workspace_id,
            "mission_context": context,
            "candidate_artifact": artifact,
        }
        signature = self.signing_key.sign(_canonical_json(signed_payload))
        response = {
            **signed_payload,
            "signature": {
                "algorithm": BROKER_SIGNATURE_ALGORITHM,
                "key_id": self.key_id,
                "value": base64.b64encode(signature).decode("ascii"),
            },
        }
        self.replay_store.complete(request_id, request, response)
        return response

    def promote_skill_candidate(self, request: object) -> dict:
        """Publish one staged draft only when an independent Validator signed its exact identity."""
        fields = {
            "schema_version", "request_id", "workspace_id", "mission_context",
            "skill_id", "skill_version", "content_sha256", "trust_level",
            "validation_attestation",
        }
        if not isinstance(request, dict) or set(request) != fields:
            raise BrokerRequestRejected("Skill candidate promotion request has unsupported or missing fields")
        if request.get("schema_version") != SKILL_CANDIDATE_PROMOTION_REQUEST_SCHEMA:
            raise BrokerRequestRejected("unsupported Skill candidate promotion request schema")
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not _UUID_RE.fullmatch(request_id):
            raise BrokerRequestRejected("Skill candidate promotion request_id is invalid")
        workspace_id = request.get("workspace_id")
        if not isinstance(workspace_id, str) or workspace_id not in self.workspace_roots:
            raise BrokerRequestRejected("workspace_id is not registered with this broker")
        try:
            context = _normalize_mission_context(request.get("mission_context"))
        except ValueError as exc:
            raise BrokerRequestRejected("Skill candidate promotion Mission context is invalid") from exc
        self._authorize_workspace_tenant(workspace_id, context["tenant_id"])

        skill_id = request.get("skill_id")
        version = request.get("skill_version")
        digest = request.get("content_sha256")
        trust_level = request.get("trust_level")
        if not isinstance(skill_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", skill_id):
            raise BrokerRequestRejected("Skill candidate promotion ID is invalid")
        if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}", version):
            raise BrokerRequestRejected("Skill candidate promotion version is invalid")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise BrokerRequestRejected("Skill candidate promotion digest is invalid")
        if not isinstance(trust_level, str) or trust_level not in {"verified", "cloud"}:
            raise BrokerRequestRejected("Skill candidate promotion trust level is invalid")
        validation_attestation = request.get("validation_attestation")
        if not isinstance(validation_attestation, Mapping):
            raise BrokerRequestRejected("independent Validator attestation is missing")
        broker_request_id = validation_attestation.get("broker_request_id")
        broker_attestation_sha256 = validation_attestation.get("broker_attestation_sha256")
        if not isinstance(broker_request_id, str) or not _UUID_RE.fullmatch(broker_request_id):
            raise BrokerRequestRejected("Validator attestation Broker request ID is invalid")
        if not isinstance(broker_attestation_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", broker_attestation_sha256):
            raise BrokerRequestRejected("Validator attestation Broker response digest is invalid")
        if self.skill_artifact_store is None:
            raise BrokerRequestRejected("Broker Skill Artifact Store is not configured")

        # Resolve source only from Broker-owned staging storage. The promotion
        # caller cannot replace the staged source with caller-supplied code.
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": skill_id,
            "skill_version": version,
            "content_sha256": digest,
            "trust_level": "draft",
            "mission_context": context,
        }
        try:
            candidate = self.skill_artifact_store.load_for_binding(binding)
        except Exception as exc:
            raise BrokerRequestRejected("staged Skill candidate failed identity verification") from exc
        if getattr(candidate, "trust_level", None) != "draft":
            raise BrokerRequestRejected("only staged draft Skills can be promoted")

        cached_response = self.replay_store.claim(
            request_id, request, allow_indeterminate_resume=True,
        )
        if cached_response is not None:
            return cached_response
        promoted = SimpleNamespace(
            id=candidate.id,
            version=candidate.version,
            code=candidate.code,
            trust_level=trust_level,
        )
        try:
            identity = self.skill_artifact_store.publish(
                tenant_id=context["tenant_id"],
                skill=promoted,
                validation_attestation=validation_attestation,
                workspace_id=workspace_id,
                mission_context=context,
                broker_request_id=broker_request_id,
                broker_attestation_sha256=broker_attestation_sha256,
            )
        except Exception as exc:
            raise BrokerRequestRejected("independent Validator attestation was rejected") from exc

        validation_provenance = {
            "schema_version": "mission.skill-validation-provenance.v1",
            "validation_id": validation_attestation["validation_id"],
            "validator_id": validation_attestation["validator_id"],
            "policy_id": validation_attestation["policy_id"],
            "policy_sha256": validation_attestation["policy_sha256"],
            "checks_sha256": validation_attestation["checks_sha256"],
            "broker_request_id": broker_request_id,
            "broker_attestation_sha256": broker_attestation_sha256,
        }
        signed_payload = {
            "schema_version": SKILL_CANDIDATE_PROMOTION_RESPONSE_SCHEMA,
            "request_id": request_id,
            "workspace_id": workspace_id,
            "mission_context": context,
            "artifact": {"schema_version": ARTIFACT_SCHEMA, **identity},
            "validation_provenance": validation_provenance,
        }
        signature = self.signing_key.sign(_canonical_json(signed_payload))
        import base64
        response = {
            **signed_payload,
            "signature": {
                "algorithm": BROKER_SIGNATURE_ALGORITHM,
                "key_id": self.key_id,
                "value": base64.b64encode(signature).decode("ascii"),
            },
        }
        self.replay_store.complete(request_id, request, response)
        return response

    def lookup_replay_status(self, request: object) -> dict:
        fields={"schema_version","request_id","workspace_id","mission_context"}
        if not isinstance(request,dict) or set(request)!=fields:
            raise BrokerRequestRejected("Broker status request has unsupported or missing fields")
        if request.get("schema_version")!="mission.broker-replay-status-request.v1":
            raise BrokerRequestRejected("unsupported Broker status request schema")
        request_id=request.get("request_id")
        if not isinstance(request_id,str) or not _UUID_RE.fullmatch(request_id):
            raise BrokerRequestRejected("request_id is invalid")
        workspace_id=request.get("workspace_id")
        if not isinstance(workspace_id,str) or workspace_id not in self.workspace_roots:
            raise BrokerRequestRejected("workspace_id is not registered with this broker")
        try: context=_normalize_mission_context(request.get("mission_context"))
        except ValueError as exc: raise BrokerRequestRejected("Mission identity is invalid") from exc
        self._authorize_workspace_tenant(workspace_id,context["tenant_id"])
        outcome=self.replay_store.lookup(request_id,workspace_id=workspace_id,mission_context=context)
        return {"schema_version":"mission.broker-replay-status-response.v1","request_id":request_id,**outcome}

    def handle_request(self, request: object) -> dict:
        validated = validate_broker_request(request)
        request_id = validated["request_id"]
        workspace_id = validated["workspace_id"]
        root = self.workspace_roots.get(workspace_id)
        if root is None:
            raise BrokerRequestRejected("workspace_id is not registered with this broker")
        binding = validated["skill_binding"]
        if binding is not None:
            if self.skill_artifact_store is None or not callable(self.skill_replay_executor):
                raise BrokerRequestRejected(
                    "trusted Skill Artifact Store or isolated Skill Replay executor is not configured"
                )
            self._authorize_workspace_tenant(
                workspace_id, validated["mission_context"]["tenant_id"],
            )
        cached_response = self.replay_store.claim(request_id, validated)
        if cached_response is not None:
            return cached_response
        skill_artifact = None

        if binding is not None:
            try:
                skill = self.skill_artifact_store.load_for_binding(binding)
            except Exception as exc:
                raise BrokerRequestRejected("trusted Skill artifact failed independent verification") from exc
            if getattr(skill, "tenant_id", None) != validated["mission_context"]["tenant_id"]:
                raise BrokerRequestRejected("trusted Skill artifact tenant does not match Mission")
            spec = ExecutionProfileSpec(
                profile_id=SKILL_REPLAY_PROFILE_ID,
                target=validated["target"],
                argv=(),
                cwd=root,
                timeout_seconds=validated["timeout_seconds"],
                max_output_bytes=MAX_OUTPUT_BYTES,
                network_access=False,
            )
            output = self.skill_replay_executor(
                skill,
                validated["mission_context"],
                timeout_seconds=validated["timeout_seconds"],
            )
            skill_artifact = {
                "schema_version": SKILL_ARTIFACT_RESOLUTION_SCHEMA,
                "skill_id": binding["skill_id"],
                "skill_version": binding["skill_version"],
                "content_sha256": binding["content_sha256"],
                "trust_level": binding["trust_level"],
            }
        else:
            spec = resolve_execution_profile(root, {
                "profile_id": validated["profile_id"],
                "target": validated["target"],
                "timeout_seconds": validated["timeout_seconds"],
            })
            output = self.executor(spec)

        if not isinstance(output, RunnerProcessOutput):
            raise TypeError("broker executor must return RunnerProcessOutput")
        result = build_execution_result(
            spec,
            runner_id=self.runner_id,
            runner_version=self.runner_version,
            exit_code=output.exit_code,
            stdout=output.stdout,
            stderr=output.stderr,
            timed_out=output.timed_out,
            stdout_available_bytes=output.stdout_available_bytes,
            stderr_available_bytes=output.stderr_available_bytes,
        )
        skill_replay_output = (
            _skill_replay_output_from_runner(output) if binding is not None else None
        )
        signed_payload = {
            "schema_version": BROKER_RESPONSE_SCHEMA,
            "request_id": request_id,
            "workspace_id": workspace_id,
            "mission_context": validated["mission_context"],
            "skill_binding": binding,
            "skill_artifact": skill_artifact,
            "skill_replay_output": skill_replay_output,
            "result": result,
        }
        signature = self.signing_key.sign(_canonical_json(signed_payload))
        import base64
        response = {
            **signed_payload,
            "signature": {
                "algorithm": BROKER_SIGNATURE_ALGORITHM,
                "key_id": self.key_id,
                "value": base64.b64encode(signature).decode("ascii"),
            },
        }
        self.replay_store.complete(request_id, validated, response)
        return response


__all__ = [
    "BrokerReplayStore",
    "BrokerRequestRejected",
    "SandboxBrokerService",
    "validate_broker_request",
]
