"""Independent, policy-driven Validator for Broker-executed Skill candidates.

The Validator never executes Skill code. It verifies the Broker's signed replay
envelope and applies a root-controlled declarative acceptance policy to the
structured output before issuing an Ed25519 attestation.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import sqlite3
import stat
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .sandbox_broker_protocol import (
    SKILL_REPLAY_PROFILE_ID, broker_response_sha256, verify_broker_response,
)
from .skill_artifact_store import VALIDATION_ATTESTATION_SCHEMA, VALIDATION_SIGNATURE_ALGORITHM

VALIDATION_REQUEST_SCHEMA = "mission.skill-validation-request.v1"
VALIDATION_RESPONSE_SCHEMA = "mission.skill-validation-response.v1"
VALIDATION_POLICY_SCHEMA = "mission.skill-validation-policy.v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
_WORKSPACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_CONTEXT_FIELDS = {"tenant_id", "mission_run_id", "node_id", "task_id"}
_BINDING_FIELDS = {"schema_version", "skill_id", "skill_version", "content_sha256", "trust_level", "mission_context"}
_ATTESTATION_FIELDS = {
    "schema_version", "validation_id", "validator_id", "policy_id", "policy_sha256",
    "workspace_id", "tenant_id", "mission_run_id", "node_id", "task_id",
    "broker_request_id", "broker_attestation_sha256", "checks_sha256",
    "skill_id", "skill_version", "content_sha256", "trust_level", "passed", "signature",
}
_ALLOWED_TRUST_LEVELS = {"verified", "cloud"}
_ALLOWED_CHECKS = {"json_key_exists", "json_value_equals", "json_value_type"}
_ALLOWED_JSON_TYPES = {"null", "boolean", "number", "string", "array", "object"}


class SkillValidatorError(ValueError):
    """A Skill replay cannot be independently validated."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SkillValidatorError("validation payload is not strict JSON") from exc


def _identity(value: Any, field: str, pattern: re.Pattern[str] = _ID_RE) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise SkillValidatorError(f"{field} is invalid")
    return value


def _context(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _CONTEXT_FIELDS:
        raise SkillValidatorError("mission_context has unsupported or missing fields")
    return {key: _identity(value.get(key), key) for key in sorted(_CONTEXT_FIELDS)}


def _read_json_path(value: Any, path: Sequence[str | int]) -> Any:
    current = value
    for part in path:
        if isinstance(part, int):
            if not isinstance(current, list) or part < 0 or part >= len(current):
                raise KeyError("array index not found")
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                raise KeyError("object key not found")
            current = current[part]
    return current


def _normalize_check(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SkillValidatorError(f"policy check {index} must be an object")
    check_type = raw.get("type")
    if check_type not in _ALLOWED_CHECKS:
        raise SkillValidatorError(f"policy check {index} has an unsupported type")
    required = {"type", "key_path"}
    if check_type == "json_value_equals":
        required.add("expected")
    elif check_type == "json_value_type":
        required.add("expected_type")
    if set(raw) != required:
        raise SkillValidatorError(f"policy check {index} has unsupported or missing fields")
    path = raw.get("key_path")
    if (
        not isinstance(path, list) or not path or len(path) > 32
        or any(
            not isinstance(part, (str, int)) or isinstance(part, bool)
            or (isinstance(part, str) and (not part or len(part) > 128))
            or (isinstance(part, int) and (part < 0 or part > 10000))
            for part in path
        )
    ):
        raise SkillValidatorError(f"policy check {index} key_path is invalid")
    check = {"type": check_type, "key_path": list(path)}
    if check_type == "json_value_equals":
        _canonical_json({"expected": raw["expected"]})
        check["expected"] = raw["expected"]
    elif check_type == "json_value_type":
        expected_type = raw.get("expected_type")
        if expected_type not in _ALLOWED_JSON_TYPES:
            raise SkillValidatorError(f"policy check {index} expected_type is invalid")
        check["expected_type"] = expected_type
    return check


def normalize_validation_policies(value: Any) -> tuple[dict[str, Any], ...]:
    """Validate immutable acceptance rules loaded from a trusted deployment file."""
    if not isinstance(value, dict) or set(value) != {"schema_version", "policies"}:
        raise SkillValidatorError("validation policy document has unsupported or missing fields")
    if value.get("schema_version") != VALIDATION_POLICY_SCHEMA:
        raise SkillValidatorError("unsupported validation policy schema")
    policies = value.get("policies")
    if not isinstance(policies, list) or not policies or len(policies) > 10000:
        raise SkillValidatorError("validation policy document must contain 1..10000 policies")
    normalized = []
    seen_policy_ids: set[str] = set()
    seen_identities: set[tuple[str, str, str, str, str]] = set()
    for index, raw in enumerate(policies):
        fields = {
            "policy_id", "tenant_id", "skill_id", "skill_version",
            "content_sha256", "trust_level", "checks",
        }
        if not isinstance(raw, dict) or set(raw) != fields:
            raise SkillValidatorError(f"validation policy {index} has unsupported or missing fields")
        policy_id = _identity(raw.get("policy_id"), "policy_id")
        tenant_id = _identity(raw.get("tenant_id"), "tenant_id")
        skill_id = _identity(raw.get("skill_id"), "skill_id")
        version = _identity(raw.get("skill_version"), "skill_version", _VERSION_RE)
        digest = _identity(raw.get("content_sha256"), "content_sha256", _DIGEST_RE)
        trust = raw.get("trust_level")
        if not isinstance(trust, str) or trust not in _ALLOWED_TRUST_LEVELS:
            raise SkillValidatorError(f"validation policy {index} trust_level is invalid")
        checks = raw.get("checks")
        if not isinstance(checks, list) or not checks or len(checks) > 64:
            raise SkillValidatorError(f"validation policy {index} requires 1..64 checks")
        identity = (tenant_id, skill_id, version, digest, trust)
        if policy_id in seen_policy_ids or identity in seen_identities:
            raise SkillValidatorError("validation policies contain duplicate IDs or artifact identities")
        seen_policy_ids.add(policy_id)
        seen_identities.add(identity)
        normalized.append({
            "policy_id": policy_id, "tenant_id": tenant_id, "skill_id": skill_id,
            "skill_version": version, "content_sha256": digest, "trust_level": trust,
            "checks": [_normalize_check(check, i) for i, check in enumerate(checks)],
        })
    return tuple(normalized)


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unsupported"


def _check_output(value: Any, checks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for index, check in enumerate(checks):
        passed = False
        try:
            actual = _read_json_path(value, check["key_path"])
            if check["type"] == "json_key_exists":
                passed = True
            elif check["type"] == "json_value_equals":
                expected = check["expected"]
                passed = actual == expected and not (
                    isinstance(actual, bool) != isinstance(expected, bool)
                    and (isinstance(actual, (bool, int, float)) or isinstance(expected, (bool, int, float)))
                )
            elif check["type"] == "json_value_type":
                passed = _json_type(actual) == check["expected_type"]
        except (KeyError, IndexError, TypeError):
            passed = False
        results.append({"check_index": index, "type": check["type"], "passed": bool(passed)})
    return results


class SkillValidatorRequestStore:
    """Durable idempotency ledger for signed Validator responses.

    A request is claimed before validation. A crash before the signed response
    is committed leaves an indeterminate claim that cannot be executed again.
    Completed retries return the original response, including its signature.
    """

    MAX_RESPONSE_BYTES = 128 * 1024

    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)
        if not self.database_path.is_absolute() or self.database_path.is_symlink():
            raise SkillValidatorError("Validator replay database path must be absolute and non-symlink")
        parent = self.database_path.parent
        try:
            parent_info = parent.lstat()
        except OSError as exc:
            raise SkillValidatorError("Validator replay database directory must be provisioned") from exc
        if (
            not stat.S_ISDIR(parent_info.st_mode) or stat.S_ISLNK(parent_info.st_mode)
            or parent_info.st_uid != os.geteuid()
            or parent_info.st_mode & 0o077
            or parent.resolve(strict=True) != parent
        ):
            raise SkillValidatorError("Validator replay database directory is not private and trusted")
        self._prepare_database_file()
        self._initialize()

    def _prepare_database_file(self):
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.database_path, flags, 0o600)
        except FileExistsError:
            try:
                fd = os.open(
                    self.database_path,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                )
            except OSError as exc:
                raise SkillValidatorError("Validator replay database is unavailable or unsafe") from exc
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
            ):
                os.close(fd)
                raise SkillValidatorError("Validator replay database must be service-owned and mode 0600")
        except OSError as exc:
            raise SkillValidatorError("Validator replay database could not be created safely") from exc
        try:
            os.fchmod(fd, 0o600)
            os.fsync(fd)
        finally:
            os.close(fd)
        directory_fd = os.open(self.database_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _connect(self):
        if self.database_path.is_symlink():
            raise SkillValidatorError("Validator replay database must not be a symlink")
        connection = sqlite3.connect(
            str(self.database_path), timeout=30, isolation_level=None,
        )
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _secure_database_files(self):
        for path in (
            self.database_path,
            Path(str(self.database_path) + "-wal"),
            Path(str(self.database_path) + "-shm"),
        ):
            if not path.exists():
                continue
            info = path.lstat()
            if (
                not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or info.st_uid != os.geteuid() or info.st_mode & 0o077
            ):
                raise SkillValidatorError("Validator replay database files must be service-owned and private")

    def _initialize(self):
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS validator_requests (
                    request_id TEXT PRIMARY KEY,
                    request_digest TEXT NOT NULL,
                    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    response_json TEXT,
                    workspace_id TEXT, tenant_id TEXT, mission_run_id TEXT, node_id TEXT, task_id TEXT
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(validator_requests)").fetchall()}
            migrations = {"workspace_id":"TEXT","tenant_id":"TEXT","mission_run_id":"TEXT","node_id":"TEXT","task_id":"TEXT"}
            for name, sql_type in migrations.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE validator_requests ADD COLUMN {name} {sql_type}")
            self._secure_database_files()
        finally:
            connection.close()

    @staticmethod
    def _digest(request: dict) -> str:
        return hashlib.sha256(_canonical_json(request)).hexdigest()

    def claim(self, request_id: str, request: dict) -> dict | None:
        digest = self._digest(request)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT request_digest, response_json FROM validator_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is not None:
                connection.execute("COMMIT")
                if row[0] != digest:
                    raise SkillValidatorError("validation request_id was reused with a different digest")
                if row[1] is None:
                    raise SkillValidatorError(
                        "validation request is indeterminate; operator review is required"
                    )
                try:
                    response = json.loads(row[1])
                except (TypeError, json.JSONDecodeError) as exc:
                    raise SkillValidatorError(
                        "cached Validator response is corrupt; operator review is required"
                    ) from exc
                if not isinstance(response, dict):
                    raise SkillValidatorError("cached Validator response is invalid")
                return response
            context = request.get("mission_context")
            workspace_id = request.get("workspace_id")
            if not isinstance(context, Mapping) or not isinstance(workspace_id,str):
                raise SkillValidatorError("validation Mission identity is missing from replay ledger claim")
            normalized = _context(context)
            connection.execute(
                """INSERT INTO validator_requests(request_id,request_digest,workspace_id,tenant_id,mission_run_id,node_id,task_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (request_id,digest,workspace_id,normalized["tenant_id"],normalized["mission_run_id"],normalized["node_id"],normalized["task_id"]),
            )
            connection.execute("COMMIT")
            self._secure_database_files()
            return None
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def lookup(self, request_id: str, *, workspace_id: str, mission_context: Mapping[str, Any]) -> dict:
        """Read a validation outcome only for its exact persisted Mission identity."""
        try: uuid.UUID(request_id)
        except (ValueError,TypeError,AttributeError) as exc: raise SkillValidatorError("validation request_id is invalid") from exc
        workspace_id=_identity(workspace_id,"workspace_id",_WORKSPACE_RE)
        context=_context(mission_context)
        connection=self._connect()
        try:
            row=connection.execute(
                "SELECT response_json,workspace_id,tenant_id,mission_run_id,node_id,task_id FROM validator_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
        finally: connection.close()
        if row is None: return {"status":"not_found"}
        expected=(workspace_id,context["tenant_id"],context["mission_run_id"],context["node_id"],context["task_id"])
        if any(value is None for value in row[1:]) or tuple(row[1:])!=expected:
            raise SkillValidatorError("validation outcome is not available for this Mission identity")
        if row[0] is None: return {"status":"indeterminate"}
        try: response=json.loads(row[0])
        except (TypeError,json.JSONDecodeError) as exc: raise SkillValidatorError("cached Validator response is corrupt; operator review is required") from exc
        if not isinstance(response,dict) or response.get("request_id")!=request_id:
            raise SkillValidatorError("cached Validator response is invalid; operator review is required")
        return {"status":"completed","response":response}

    def complete(self, request_id: str, request: dict, response: dict) -> None:
        encoded = _canonical_json(response).decode("utf-8")
        if len(encoded.encode("utf-8")) > self.MAX_RESPONSE_BYTES:
            raise SkillValidatorError("Validator response exceeds the durable cache limit")
        digest = self._digest(request)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT request_digest, response_json FROM validator_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if row is None or row[0] != digest:
                raise SkillValidatorError("Validator request claim is missing or mismatched")
            if row[1] is not None and row[1] != encoded:
                raise SkillValidatorError("Validator completed response is immutable")
            connection.execute(
                "UPDATE validator_requests SET response_json = ? WHERE request_id = ? AND response_json IS NULL",
                (encoded, request_id),
            )
            connection.execute("COMMIT")
            self._secure_database_files()
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


class SkillValidatorService:
    """Independent attestor; owns the signing key and trusts only pinned Broker keys."""

    def __init__(
        self, *, validator_id: str, key_id: str, signing_key: Ed25519PrivateKey,
        broker_public_key: bytes, broker_key_id: str,
        workspace_ids: Sequence[str], policies: Sequence[Mapping[str, Any]],
        request_store: SkillValidatorRequestStore | None = None,
    ):
        self.validator_id = _identity(validator_id, "validator_id")
        self.key_id = _identity(key_id, "key_id")
        if not isinstance(signing_key, Ed25519PrivateKey):
            raise SkillValidatorError("Validator signing key must be Ed25519")
        try:
            self.broker_public_key = bytes(broker_public_key)
            Ed25519PublicKey.from_public_bytes(self.broker_public_key)
        except (ValueError, TypeError) as exc:
            raise SkillValidatorError("Broker public key is invalid") from exc
        self.signing_key = signing_key
        self.request_store = request_store
        self.broker_key_id = _identity(broker_key_id, "broker_key_id")
        if not isinstance(workspace_ids, Sequence) or isinstance(workspace_ids, (str, bytes)) or not workspace_ids:
            raise SkillValidatorError("workspace_ids must be a non-empty sequence")
        self.workspace_ids = frozenset(_identity(item, "workspace_id", _WORKSPACE_RE) for item in workspace_ids)
        normalized = normalize_validation_policies({"schema_version": VALIDATION_POLICY_SCHEMA, "policies": list(policies)})
        self.policies = {
            (item["tenant_id"], item["skill_id"], item["skill_version"], item["content_sha256"], item["trust_level"]): item
            for item in normalized
        }

    def validate(self, request: Any) -> dict[str, Any]:
        if self.request_store is None:
            return self._validate_uncached(request)
        expected_fields = {
            "schema_version", "request_id", "workspace_id", "mission_context",
            "skill_binding", "trust_level", "broker_attestation",
        }
        if (
            not isinstance(request, dict) or set(request) != expected_fields
            or request.get("schema_version") != VALIDATION_REQUEST_SCHEMA
            or not isinstance(request.get("request_id"), str)
        ):
            raise SkillValidatorError("validation request has unsupported or missing fields")
        try:
            uuid.UUID(request["request_id"])
        except (ValueError, TypeError, AttributeError) as exc:
            raise SkillValidatorError("validation request_id is invalid") from exc
        cached = self.request_store.claim(request["request_id"], request)
        if cached is not None:
            return cached
        response = self._validate_uncached(request)
        self.request_store.complete(request["request_id"], request, response)
        return response

    def _validate_uncached(self, request: Any) -> dict[str, Any]:
        fields = {
            "schema_version", "request_id", "workspace_id", "mission_context",
            "skill_binding", "trust_level", "broker_attestation",
        }
        if not isinstance(request, dict) or set(request) != fields:
            raise SkillValidatorError("validation request has unsupported or missing fields")
        if request.get("schema_version") != VALIDATION_REQUEST_SCHEMA:
            raise SkillValidatorError("unsupported validation request schema")
        request_id = request.get("request_id")
        try:
            uuid.UUID(request_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise SkillValidatorError("validation request_id is invalid") from exc
        workspace_id = _identity(request.get("workspace_id"), "workspace_id", _WORKSPACE_RE)
        if workspace_id not in self.workspace_ids:
            raise SkillValidatorError("workspace_id is not authorized for this Validator")
        context = _context(request.get("mission_context"))
        binding = request.get("skill_binding")
        if not isinstance(binding, Mapping) or set(binding) != _BINDING_FIELDS:
            raise SkillValidatorError("Skill binding has unsupported or missing fields")
        if binding.get("schema_version") != "mission.skill-replay-binding.v1":
            raise SkillValidatorError("unsupported Skill binding schema")
        if binding.get("trust_level") != "draft":
            raise SkillValidatorError("Validator only accepts a Broker replay of a draft candidate")
        skill_id = _identity(binding.get("skill_id"), "skill_id")
        version = _identity(binding.get("skill_version"), "skill_version", _VERSION_RE)
        digest = _identity(binding.get("content_sha256"), "content_sha256", _DIGEST_RE)
        binding_context = _context(binding.get("mission_context"))
        if binding_context != context:
            raise SkillValidatorError("Skill binding Mission context does not match validation request")
        trust = request.get("trust_level")
        if not isinstance(trust, str) or trust not in _ALLOWED_TRUST_LEVELS:
            raise SkillValidatorError("requested trust_level is invalid")
        policy = self.policies.get((context["tenant_id"], skill_id, version, digest, trust))
        if policy is None:
            raise SkillValidatorError("no trusted acceptance policy exists for this exact Skill artifact")

        broker_attestation = request.get("broker_attestation")
        if not isinstance(broker_attestation, dict):
            raise SkillValidatorError("signed Broker replay attestation is required")
        broker_request_id = _identity(broker_attestation.get("request_id"), "broker_request_id", _UUID_RE)
        try:
            verified_result = verify_broker_response(
                broker_attestation,
                public_key=self.broker_public_key,
                expected_key_id=self.broker_key_id,
                expected_request_id=broker_request_id,
                expected_workspace_id=workspace_id,
                expected_mission_context=context,
                expected_profile_id=SKILL_REPLAY_PROFILE_ID,
                expected_target=f"{skill_id}@{version}",
                expected_skill_binding=dict(binding),
            )
        except (TypeError, ValueError) as exc:
            raise SkillValidatorError("Broker replay attestation is invalid or untrusted") from exc
        replay_output = broker_attestation.get("skill_replay_output")
        if verified_result.get("execution_succeeded") is not True:
            raise SkillValidatorError("Broker reports that Skill execution did not succeed")
        if not isinstance(replay_output, dict) or replay_output.get("success") is not True:
            raise SkillValidatorError("Skill Replay did not produce a successful structured output")
        results = _check_output(replay_output.get("value"), policy["checks"])
        if not results or not all(item["passed"] for item in results):
            raise SkillValidatorError("Skill output failed the independent acceptance policy")

        policy_sha256 = hashlib.sha256(_canonical_json(policy)).hexdigest()
        broker_digest = broker_response_sha256(broker_attestation)
        checks_sha256 = hashlib.sha256(_canonical_json({"checks": results})).hexdigest()
        statement = {
            "schema_version": VALIDATION_ATTESTATION_SCHEMA,
            "validation_id": str(uuid.uuid4()),
            "validator_id": self.validator_id,
            "policy_id": policy["policy_id"],
            "policy_sha256": policy_sha256,
            "workspace_id": workspace_id,
            "tenant_id": context["tenant_id"],
            "mission_run_id": context["mission_run_id"],
            "node_id": context["node_id"],
            "task_id": context["task_id"],
            "broker_request_id": broker_request_id,
            "broker_attestation_sha256": broker_digest,
            "checks_sha256": checks_sha256,
            "skill_id": skill_id,
            "skill_version": version,
            "content_sha256": digest,
            "trust_level": trust,
            "passed": True,
        }
        signature = self.signing_key.sign(_canonical_json(statement))
        attestation = {
            **statement,
            "signature": {
                "algorithm": VALIDATION_SIGNATURE_ALGORITHM,
                "key_id": self.key_id,
                "value": base64.b64encode(signature).decode("ascii"),
            },
        }
        return {
            "schema_version": VALIDATION_RESPONSE_SCHEMA,
            "request_id": request_id,
            "attestation": attestation,
            "policy_id": policy["policy_id"],
            "checks": results,
        }


def verify_validation_response(
    response: Any, *, public_key: bytes, expected_key_id: str,
    expected_request_id: str, expected_identity: Mapping[str, str],
) -> dict[str, Any]:
    """Verify the Validator statement, exact replay lineage and signed check digest."""
    if not isinstance(response, dict) or set(response) != {
        "schema_version", "request_id", "attestation", "policy_id", "checks",
    }:
        raise SkillValidatorError("Validator response has unsupported or missing fields")
    if response.get("schema_version") != VALIDATION_RESPONSE_SCHEMA or response.get("request_id") != expected_request_id:
        raise SkillValidatorError("Validator response does not match the request")
    attestation = response.get("attestation")
    if not isinstance(attestation, dict) or set(attestation) != _ATTESTATION_FIELDS:
        raise SkillValidatorError("Validator attestation has unsupported or missing fields")
    if attestation.get("schema_version") != VALIDATION_ATTESTATION_SCHEMA or attestation.get("passed") is not True:
        raise SkillValidatorError("Validator did not attest a passed validation")
    for field in ("validation_id", "validator_id"):
        _identity(attestation.get(field), field)
    _identity(attestation.get("policy_id"), "policy_id")
    _identity(attestation.get("workspace_id"), "workspace_id", _WORKSPACE_RE)
    _identity(attestation.get("policy_sha256"), "policy_sha256", _DIGEST_RE)
    _identity(attestation.get("broker_request_id"), "broker_request_id", _UUID_RE)
    _identity(attestation.get("broker_attestation_sha256"), "broker_attestation_sha256", _DIGEST_RE)
    _identity(attestation.get("checks_sha256"), "checks_sha256", _DIGEST_RE)
    for field in ("tenant_id", "mission_run_id", "node_id", "task_id"):
        _identity(attestation.get(field), field)
    if response.get("policy_id") != attestation.get("policy_id"):
        raise SkillValidatorError("Validator response policy ID does not match its signed attestation")
    checks = response.get("checks")
    if not isinstance(checks, list) or not checks or len(checks) > 64 or any(
        not isinstance(item, dict) or set(item) != {"check_index", "type", "passed"}
        or item.get("check_index") != index
        or item.get("type") not in _ALLOWED_CHECKS
        or item.get("passed") is not True
        for index, item in enumerate(checks)
    ):
        raise SkillValidatorError("Validator response contains failed or malformed policy checks")
    checks_sha256 = hashlib.sha256(_canonical_json({"checks": checks})).hexdigest()
    if checks_sha256 != attestation["checks_sha256"]:
        raise SkillValidatorError("Validator check results do not match the signed attestation")
    expected_fields = (
        "workspace_id", "tenant_id", "mission_run_id", "node_id", "task_id",
        "broker_request_id", "broker_attestation_sha256",
        "skill_id", "skill_version", "content_sha256", "trust_level",
    )
    for field in expected_fields:
        if attestation.get(field) != expected_identity.get(field):
            raise SkillValidatorError("Validator attestation does not bind the expected replay and artifact")
    signature = attestation.get("signature")
    if not isinstance(signature, dict) or set(signature) != {"algorithm", "key_id", "value"}:
        raise SkillValidatorError("Validator signature metadata is invalid")
    if signature.get("algorithm") != VALIDATION_SIGNATURE_ALGORITHM or signature.get("key_id") != expected_key_id:
        raise SkillValidatorError("Validator signer is not trusted")
    encoded = signature.get("value")
    if not isinstance(encoded, str) or not encoded:
        raise SkillValidatorError("Validator signature is missing")
    unsigned = {key: attestation[key] for key in _ATTESTATION_FIELDS if key != "signature"}
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            base64.b64decode(encoded, validate=True), _canonical_json(unsigned),
        )
    except (ValueError, TypeError, binascii.Error, InvalidSignature) as exc:
        raise SkillValidatorError("Validator signature verification failed") from exc
    return attestation


__all__ = [
    "VALIDATION_REQUEST_SCHEMA", "VALIDATION_RESPONSE_SCHEMA", "VALIDATION_POLICY_SCHEMA",
    "SkillValidatorError", "normalize_validation_policies", "SkillValidatorService",
    "verify_validation_response",
]
