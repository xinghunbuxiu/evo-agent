"""Authenticated Unix-socket transport for the independent Skill Validator."""
from __future__ import annotations

import json
import socket
import struct
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from .skill_validator import VALIDATION_REQUEST_SCHEMA, SkillValidatorError, verify_validation_response

MAX_VALIDATOR_REQUEST_BYTES = 1024 * 1024
MAX_VALIDATOR_RESPONSE_BYTES = 128 * 1024
_FRAME = struct.Struct("!I")


class SkillValidatorTransportError(RuntimeError):
    """Validator socket, framing, peer-authentication, or attestation failure."""


def _allowed_uids(values: Iterable[int]) -> frozenset[int]:
    entries = tuple(values)
    if not entries or any(isinstance(uid, bool) or not isinstance(uid, int) or uid < 0 for uid in entries):
        raise ValueError("allowed_uids must contain non-negative integer UIDs")
    if len(set(entries)) != len(entries):
        raise ValueError("allowed_uids must not contain duplicates")
    return frozenset(entries)


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    deadline = time.monotonic() + 10.0
    chunks = []
    remaining = size
    while remaining:
        connection.settimeout(max(0.001, deadline - time.monotonic()))
        try:
            chunk = connection.recv(remaining)
        except (OSError, socket.timeout) as exc:
            raise SkillValidatorTransportError("Validator socket receive failed") from exc
        if not chunk:
            raise SkillValidatorTransportError("Validator connection closed during frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_frame(connection: socket.socket, limit: int) -> bytes:
    size = _FRAME.unpack(_recv_exact(connection, _FRAME.size))[0]
    if size < 1 or size > limit:
        raise SkillValidatorTransportError("Validator frame length is outside the allowed range")
    return _recv_exact(connection, size)


def _send_frame(connection: socket.socket, payload: bytes, limit: int) -> None:
    if not payload or len(payload) > limit:
        raise SkillValidatorTransportError("Validator response exceeds the frame limit")
    connection.settimeout(10.0)
    connection.sendall(_FRAME.pack(len(payload)) + payload)


def _peer_uid(connection: socket.socket) -> int:
    if not hasattr(socket, "SO_PEERCRED"):
        raise SkillValidatorTransportError("kernel peer credential checks are unavailable")
    raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    _pid, uid, _gid = struct.unpack("3i", raw)
    return uid


def handle_validator_connection(
    connection: socket.socket, *, service, allowed_uids: Iterable[int],
) -> None:
    allowed = _allowed_uids(allowed_uids)
    connection.settimeout(5.0)
    if _peer_uid(connection) not in allowed:
        raise SkillValidatorTransportError("peer UID is not authorized")
    raw = _recv_frame(connection, MAX_VALIDATOR_REQUEST_BYTES)
    try:
        request = json.loads(raw.decode("utf-8"))
        if isinstance(request,dict) and request.get("schema_version")=="mission.skill-validation-status-request.v1":
            response=service.lookup_request_status(request)
        else:
            response = service.validate(request)
        payload = json.dumps(
            response, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except SkillValidatorError:
        payload = b'{"error":{"code":"validation_rejected","message":"Validator rejected the request"}}'
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        payload = b'{"error":{"code":"invalid_request","message":"Validator request is invalid"}}'
    _send_frame(connection, payload, MAX_VALIDATOR_RESPONSE_BYTES)


def serve_validator_listener(
    listener: socket.socket, *, service, allowed_uids: Iterable[int],
    stop_event: threading.Event | None = None, max_workers: int = 4,
) -> None:
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or not 1 <= max_workers <= 16:
        raise ValueError("max_workers must be between 1 and 16")
    allowed = _allowed_uids(allowed_uids)
    slots = threading.BoundedSemaphore(max_workers)
    listener.settimeout(0.5)

    def handle(connection: socket.socket) -> None:
        try:
            with connection:
                handle_validator_connection(connection, service=service, allowed_uids=allowed)
        except (SkillValidatorTransportError, OSError, socket.timeout):
            pass
        finally:
            slots.release()

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="skill-validator") as pool:
        while stop_event is None or not stop_event.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if stop_event is not None and stop_event.is_set():
                    break
                raise
            if not slots.acquire(blocking=False):
                connection.close()
                continue
            pool.submit(handle, connection)


def request_skill_validation(
    socket_path: str, *, request: dict, validator_public_key: bytes,
    expected_key_id: str, expected_identity: dict[str, str],
    timeout_seconds: float = 30.0,
) -> dict:
    if not hasattr(socket, "AF_UNIX"):
        raise SkillValidatorTransportError("Unix-domain sockets are unavailable")
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not 0 < timeout_seconds <= 330:
        raise ValueError("timeout_seconds must be between zero and 330")
    if not isinstance(request, dict) or request.get("schema_version") != VALIDATION_REQUEST_SCHEMA:
        raise ValueError("request is not a Skill Validator request")
    if "request_id" not in request:
        request = {**request, "request_id": str(uuid.uuid4())}
    try:
        payload = json.dumps(
            request, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("Validator request is not strict JSON") from exc
    if not payload or len(payload) > MAX_VALIDATOR_REQUEST_BYTES:
        raise SkillValidatorTransportError("Validator request exceeds the frame limit")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout_seconds)
        try:
            connection.connect(socket_path)
            connection.sendall(_FRAME.pack(len(payload)) + payload)
            response_bytes = _recv_frame(connection, MAX_VALIDATOR_RESPONSE_BYTES)
        except OSError as exc:
            raise SkillValidatorTransportError("could not complete Validator socket exchange") from exc
    try:
        response = json.loads(response_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkillValidatorTransportError("Validator returned invalid UTF-8 JSON") from exc
    if not isinstance(response, dict):
        raise SkillValidatorTransportError("Validator response must be an object")
    if "error" in response:
        raise SkillValidatorTransportError("independent Validator rejected the Skill candidate")
    try:
        return verify_validation_response(
            response, public_key=validator_public_key,
            expected_key_id=expected_key_id,
            expected_request_id=request["request_id"],
            expected_identity=expected_identity,
        )
    except SkillValidatorError as exc:
        raise SkillValidatorTransportError("Validator attestation verification failed") from exc


def request_skill_validator_status(
    socket_path: str, *, request_id: str, workspace_id: str,
    mission_context: dict[str,str], timeout_seconds: float = 10.0,
) -> dict:
    """Query the durable outcome for one original Validator request identity."""
    request={"schema_version":"mission.skill-validation-status-request.v1",
             "request_id":request_id,"workspace_id":workspace_id,
             "mission_context":dict(mission_context)}
    try:
        payload=json.dumps(request,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    except (TypeError,ValueError,UnicodeError) as exc:
        raise ValueError("Validator status request is not strict JSON") from exc
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout_seconds)
        try:
            connection.connect(socket_path)
            connection.sendall(_FRAME.pack(len(payload))+payload)
            response_bytes=_recv_frame(connection,MAX_VALIDATOR_RESPONSE_BYTES)
        except OSError as exc:
            raise SkillValidatorTransportError("could not complete Validator status query") from exc
    try: response=json.loads(response_bytes.decode("utf-8"))
    except (UnicodeDecodeError,json.JSONDecodeError) as exc: raise SkillValidatorTransportError("Validator returned invalid status JSON") from exc
    if not isinstance(response,dict) or response.get("schema_version")!="mission.skill-validation-status-response.v1" or response.get("request_id")!=request_id:
        raise SkillValidatorTransportError("Validator status response is malformed or rejected")
    if response.get("status") not in {"not_found","indeterminate","completed"}:
        raise SkillValidatorTransportError("Validator status value is invalid")
    if response["status"]=="completed" and not isinstance(response.get("response"),dict):
        raise SkillValidatorTransportError("Validator completed response is missing")
    return response


__all__ = [
    "SkillValidatorTransportError", "handle_validator_connection",
    "serve_validator_listener", "request_skill_validation",
    "request_skill_validator_status",
]
