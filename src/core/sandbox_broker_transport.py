"""Length-prefixed Unix-domain socket transport for the sandbox broker.

Intended for a systemd socket-activated, root-owned deployment. The socket
filesystem permissions and allowed UID list are deployment policy; requests
are additionally checked against kernel peer credentials before parsing.
"""
from __future__ import annotations

import json
import socket
import struct
from typing import Iterable

from .sandbox_broker import BrokerRequestRejected, SandboxBrokerService


MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
_FRAME = struct.Struct("!I")


class BrokerTransportError(RuntimeError):
    """Transport framing, peer-authentication, or connection failure."""


def _recv_exact(connection: socket.socket, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise BrokerTransportError("connection closed during frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_frame(connection: socket.socket, limit: int) -> bytes:
    size = _FRAME.unpack(_recv_exact(connection, _FRAME.size))[0]
    if size < 1 or size > limit:
        raise BrokerTransportError("frame length is outside the allowed range")
    return _recv_exact(connection, size)


def _send_frame(connection: socket.socket, payload: bytes, limit: int) -> None:
    if not payload or len(payload) > limit:
        raise BrokerTransportError("response frame exceeds the allowed size")
    connection.sendall(_FRAME.pack(len(payload)) + payload)


def _peer_uid(connection: socket.socket) -> int:
    if not hasattr(socket, "SO_PEERCRED"):
        raise BrokerTransportError("kernel peer credential checks are unavailable")
    credentials = connection.getsockopt(
        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"),
    )
    _pid, uid, _gid = struct.unpack("3i", credentials)
    return uid


def handle_broker_connection(
    connection: socket.socket,
    *,
    service: SandboxBrokerService,
    allowed_uids: Iterable[int],
) -> None:
    """Handle exactly one request; unauthorized peers are rejected before JSON parsing."""
    allowed = frozenset(allowed_uids)
    try:
        peer_uid = _peer_uid(connection)
        if peer_uid not in allowed:
            raise BrokerTransportError("peer UID is not authorized")
        raw = _recv_frame(connection, MAX_REQUEST_BYTES)
        try:
            request = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BrokerTransportError("request frame is not valid UTF-8 JSON") from exc
        response = service.handle_request(request)
        payload = json.dumps(
            response, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
    except BrokerRequestRejected:
        payload = b'{"error":{"code":"request_rejected","message":"broker rejected request"}}'
    except BrokerTransportError:
        raise
    except Exception:
        # Do not expose filesystem paths, exception messages, or private key state.
        payload = b'{"error":{"code":"broker_execution_failed","message":"broker execution failed"}}'
    _send_frame(connection, payload, MAX_RESPONSE_BYTES)


def request_broker(
    socket_path: str,
    request: dict,
    *,
    timeout_seconds: float = 30.0,
) -> dict:
    """Send one bounded request over a trusted Unix socket and parse one response."""
    if not hasattr(socket, "AF_UNIX"):
        raise BrokerTransportError("Unix-domain sockets are unavailable on this platform")
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool):
        raise ValueError("timeout_seconds must be numeric")
    if not 0 < timeout_seconds <= 330:
        raise ValueError("timeout_seconds must be greater than zero and at most 330")
    payload = json.dumps(
        request, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    if not payload or len(payload) > MAX_REQUEST_BYTES:
        raise BrokerTransportError("request exceeds the maximum frame size")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout_seconds)
        try:
            connection.connect(socket_path)
            _send_frame(connection, payload, MAX_REQUEST_BYTES)
            response_bytes = _recv_frame(connection, MAX_RESPONSE_BYTES)
        except OSError as exc:
            raise BrokerTransportError("could not complete broker socket exchange") from exc
    try:
        response = json.loads(response_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerTransportError("broker returned invalid UTF-8 JSON") from exc
    if not isinstance(response, dict):
        raise BrokerTransportError("broker response must be a JSON object")
    return response


__all__ = [
    "BrokerTransportError",
    "handle_broker_connection",
    "request_broker",
]
