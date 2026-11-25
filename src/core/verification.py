"""Deterministic, read-only verification of Mission workspace artifacts.

Only declarative checks are accepted. This module never executes worker-provided
commands or code, and every artifact path is confined to the workspace.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath
from typing import Any


VERIFIER_ID = "evo.workspace-artifact-verifier"
VERIFIER_VERSION = "1.0.0"
SCHEMA_VERSION = "mission.verification.v1"
SUPPORTED_CHECK_TYPES = {"file_exists", "file_contains", "json_value_equals"}

SIGNATURE_ALGORITHM = "hmac-sha256"
SIGNING_KEY_FILENAME = "mission_verification_signing.key"


@contextmanager
def _verification_key_lock(lock_path: Path):
    """Serialize first-time key creation across local processes and platforms."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            import fcntl
        except ImportError:  # pragma: no cover - Windows
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _verification_signing_key(workspace: Path, *, create: bool) -> bytes | None:
    """Load a workspace-local signing key; create it atomically for the trusted runtime."""
    admin_dir = Path(workspace) / ".admin"
    key_path = admin_dir / SIGNING_KEY_FILENAME
    if create:
        admin_dir.mkdir(parents=True, exist_ok=True)
    if not admin_dir.is_dir():
        return None
    with _verification_key_lock(key_path.with_suffix(key_path.suffix + ".lock")):
        if key_path.is_symlink():
            raise ValueError("verification signing key must not be a symlink")
        if not key_path.exists():
            if not create:
                return None
            key = secrets.token_bytes(32)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(str(key_path), flags, 0o600)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(key)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                try:
                    key_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise
        if key_path.is_symlink() or not key_path.is_file():
            raise ValueError("verification signing key is not a regular file")
        key = key_path.read_bytes()
        if len(key) != 32:
            raise ValueError("verification signing key has an invalid length")
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        return key


def _verification_signature_payload(evidence: dict[str, Any], tenant_id: str) -> bytes:
    unsigned = {key: value for key, value in evidence.items() if key != "signature"}
    envelope = {"tenant_id": str(tenant_id or "default"), "evidence": unsigned}
    return json.dumps(
        envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sign_verification_evidence(
    workspace: Path, tenant_id: str, evidence: dict[str, Any]
) -> dict[str, Any]:
    """Sign runtime-owned verification evidence before it enters strategy feedback."""
    if not isinstance(evidence, dict):
        raise ValueError("verification evidence must be an object")
    signed = dict(evidence)
    key = _verification_signing_key(Path(workspace), create=True)
    assert key is not None
    digest = hmac.new(key, _verification_signature_payload(signed, tenant_id), hashlib.sha256).hexdigest()
    signed["signature"] = {
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": hashlib.sha256(key).hexdigest()[:16],
        "value": digest,
    }
    return signed


def verify_verification_evidence(
    workspace: Path, tenant_id: str, evidence: Any
) -> bool:
    """Verify integrity and tenant binding; unsigned legacy claims fail closed."""
    if not isinstance(evidence, dict):
        return False
    signature = evidence.get("signature")
    if not isinstance(signature, dict) or signature.get("algorithm") != SIGNATURE_ALGORITHM:
        return False
    try:
        key = _verification_signing_key(Path(workspace), create=False)
        if key is None:
            return False
        expected_key_id = hashlib.sha256(key).hexdigest()[:16]
        if not hmac.compare_digest(str(signature.get("key_id") or ""), expected_key_id):
            return False
        expected = hmac.new(
            key, _verification_signature_payload(evidence, tenant_id), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(str(signature.get("value") or ""), expected)
    except (OSError, TypeError, ValueError):
        return False


def normalize_verification_contract(value: Any) -> dict[str, Any]:
    """Validate and return the small, deterministic Mission verification DSL."""
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("verification contract schema_version is unsupported")
    checks = value.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("verification contract requires at least one check")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(checks):
        if not isinstance(raw, dict):
            raise ValueError(f"verification check {index} must be an object")
        check_id = str(raw.get("check_id") or "").strip()
        check_type = str(raw.get("type") or "").strip()
        relative_path = str(raw.get("path") or "").strip()
        if not check_id or check_id in seen_ids:
            raise ValueError(f"verification check {index} has a missing or duplicate check_id")
        if check_type not in SUPPORTED_CHECK_TYPES:
            raise ValueError(f"verification check {check_id!r} uses an unsupported type")
        if (
            not relative_path
            or Path(relative_path).is_absolute()
            or PureWindowsPath(relative_path).is_absolute()
            or PureWindowsPath(relative_path).drive
            or "\\" in relative_path
            or ":" in relative_path
            or "\x00" in relative_path
        ):
            raise ValueError(f"verification check {check_id!r} requires a portable relative path")
        if any(part in {"", ".", ".."} for part in Path(relative_path).parts):
            raise ValueError(f"verification check {check_id!r} has an unsafe path")
        item: dict[str, Any] = {
            "check_id": check_id,
            "type": check_type,
            "path": relative_path,
        }
        if check_type == "file_contains":
            expected = raw.get("expected")
            if not isinstance(expected, str) or not expected:
                raise ValueError(f"verification check {check_id!r} requires non-empty expected text")
            item["expected"] = expected
        elif check_type == "json_value_equals":
            key_path = raw.get("key_path")
            if not isinstance(key_path, list) or not key_path or any(
                not isinstance(part, (str, int)) or isinstance(part, bool) for part in key_path
            ):
                raise ValueError(f"verification check {check_id!r} requires a non-empty key_path")
            if "expected" not in raw:
                raise ValueError(f"verification check {check_id!r} requires expected value")
            item["key_path"] = list(key_path)
            item["expected"] = raw["expected"]
        seen_ids.add(check_id)
        normalized.append(item)
    return {"schema_version": SCHEMA_VERSION, "checks": normalized}


def _workspace_file(workspace: Path, relative_path: str) -> Path:
    root = Path(workspace).resolve()
    candidate = (root / relative_path).resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("artifact path escapes workspace") from exc
    if not candidate.is_file():
        raise ValueError("artifact is not a regular file")
    if candidate.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("artifact exceeds the 2 MiB verification limit")
    return candidate


def _read_json_path(value: Any, key_path: list[str | int]) -> Any:
    current = value
    for part in key_path:
        if isinstance(part, int):
            if not isinstance(current, list) or part < 0 or part >= len(current):
                raise KeyError("JSON array index not found")
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                raise KeyError("JSON object key not found")
            current = current[part]
    return current


def verify_workspace_artifacts(
    *, workspace, tenant_id: str, mission_run: dict, action: dict, task
) -> dict[str, Any] | None:
    """Independently inspect declared files and return check-level evidence.

    The verifier reads only files inside the configured workspace. It does not trust
    task.result, worker-reported booleans, arbitrary paths, or executable commands.
    """
    if not isinstance(action, dict):
        return None
    try:
        contract = normalize_verification_contract(action.get("verification_contract"))
    except (TypeError, ValueError):
        return None

    results: list[dict[str, Any]] = []
    for check in contract["checks"]:
        passed = False
        try:
            artifact = _workspace_file(Path(workspace), check["path"])
            if check["type"] == "file_exists":
                passed = True
            elif check["type"] == "file_contains":
                passed = check["expected"] in artifact.read_text(encoding="utf-8")
            elif check["type"] == "json_value_equals":
                payload = json.loads(artifact.read_text(encoding="utf-8"))
                actual = _read_json_path(payload, check["key_path"])
                passed = actual == check["expected"]
        except (OSError, UnicodeError, ValueError, KeyError, IndexError, json.JSONDecodeError):
            passed = False
        results.append({"check_id": check["check_id"], "passed": bool(passed)})

    return {
        "verifier_id": VERIFIER_ID,
        "verifier_version": VERIFIER_VERSION,
        "checks": results,
    }
