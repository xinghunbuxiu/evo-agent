"""Core request validation and replay protection for a privileged sandbox broker.

This module is the broker-side policy core. A deployment must still wrap it in
a root-owned Unix socket service and inject a container executor whose isolation
policy is enforced by the host. No Docker or subprocess fallback is provided.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .execution_profiles import resolve_execution_profile
from .execution_results import build_execution_result
from .sandbox_broker_protocol import (
    BROKER_REQUEST_SCHEMA,
    BROKER_RESPONSE_SCHEMA,
    BROKER_SIGNATURE_ALGORITHM,
    _canonical_json,
)
from .sandbox_runner import RunnerProcessOutput


_REQUEST_FIELDS = {
    "schema_version", "request_id", "workspace_id",
    "profile_id", "target", "timeout_seconds",
}
_WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class BrokerRequestRejected(ValueError):
    """A broker request failed schema, policy, or replay validation."""


class BrokerReplayStore:
    """Persistent request-ID ledger; IDs are never silently reused after restart."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        if self.database_path.is_symlink():
            raise ValueError("broker replay database must not be a symlink")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(
            str(self.database_path), timeout=10, isolation_level=None,
        )
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS broker_requests (
                    request_id TEXT PRIMARY KEY,
                    request_digest TEXT NOT NULL,
                    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def claim(self, request_id: str, request: dict) -> None:
        digest = hashlib.sha256(_canonical_json(request)).hexdigest()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO broker_requests(request_id, request_digest) VALUES (?, ?)",
                    (request_id, digest),
                )
            except sqlite3.IntegrityError as exc:
                connection.execute("ROLLBACK")
                raise BrokerRequestRejected("request_id has already been used") from exc
            connection.execute("COMMIT")
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
    profile_id = request.get("profile_id")
    if profile_id not in {"python.unittest", "python.pytest"}:
        raise BrokerRequestRejected("unsupported execution profile")
    target = request.get("target")
    if not isinstance(target, str) or not target or len(target) > 512 or "\x00" in target:
        raise BrokerRequestRejected("execution target is invalid")
    if profile_id == "python.pytest":
        path = PurePosixPath(target)
        if path.is_absolute() or "\\" in target or any(
            part in {"", ".", ".."} for part in path.parts
        ):
            raise BrokerRequestRejected("pytest target must be workspace-relative")
    elif not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", target):
        raise BrokerRequestRejected("unittest target must be a dotted module name")
    timeout = request.get("timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 300:
        raise BrokerRequestRejected("timeout_seconds must be between 1 and 300")
    return dict(request)


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
    ):
        if not key_id or len(key_id) > 128:
            raise ValueError("broker key_id must be a non-empty bounded value")
        self.workspace_roots = {
            str(workspace_id): Path(root) for workspace_id, root in workspace_roots.items()
        }
        self.replay_store = replay_store
        self.executor = executor
        self.signing_key = signing_key
        self.key_id = key_id
        self.runner_id = runner_id
        self.runner_version = runner_version

    def handle_request(self, request: object) -> dict:
        validated = validate_broker_request(request)
        request_id = validated["request_id"]
        workspace_id = validated["workspace_id"]
        root = self.workspace_roots.get(workspace_id)
        if root is None:
            raise BrokerRequestRejected("workspace_id is not registered with this broker")
        self.replay_store.claim(request_id, validated)

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
        )
        signed_payload = {
            "schema_version": BROKER_RESPONSE_SCHEMA,
            "request_id": request_id,
            "result": result,
        }
        signature = self.signing_key.sign(_canonical_json(signed_payload))
        import base64
        return {
            **signed_payload,
            "signature": {
                "algorithm": BROKER_SIGNATURE_ALGORITHM,
                "key_id": self.key_id,
                "value": base64.b64encode(signature).decode("ascii"),
            },
        }


__all__ = [
    "BrokerReplayStore",
    "BrokerRequestRejected",
    "SandboxBrokerService",
    "validate_broker_request",
]
