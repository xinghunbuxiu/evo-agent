"""Versioned, asymmetric-authenticated contract for a privileged sandbox broker.

The broker owns workspace-path resolution, container construction and the
Ed25519 signing key. This module is the unprivileged client-side contract only;
it does not start a broker, access Docker, or execute code.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import uuid
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .execution_profiles import ExecutionProfileSpec
from .execution_results import EXECUTION_RESULT_SCHEMA


BROKER_REQUEST_SCHEMA = "mission.sandbox-broker-request.v1"
BROKER_RESPONSE_SCHEMA = "mission.sandbox-broker-response.v1"
BROKER_SIGNATURE_ALGORITHM = "ed25519"
_WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REQUEST_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def build_broker_request(
    workspace_id: str, spec: ExecutionProfileSpec, *, request_id: str | None = None,
) -> dict[str, Any]:
    """Build a path-free request; the privileged broker maps workspace_id to a root."""
    workspace_id = str(workspace_id or "").strip()
    if not _WORKSPACE_ID_RE.fullmatch(workspace_id):
        raise ValueError("workspace_id must be a registered opaque identifier")
    request_id = str(request_id or uuid.uuid4()).lower()
    if not _REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("request_id must be a UUID")
    if spec.profile_id not in {"python.unittest", "python.pytest"}:
        raise ValueError("unsupported broker execution profile")
    if not isinstance(spec.timeout_seconds, int) or isinstance(spec.timeout_seconds, bool):
        raise ValueError("timeout_seconds must be an integer")
    if not 1 <= spec.timeout_seconds <= 300:
        raise ValueError("timeout_seconds is outside the broker policy range")

    # Deliberately omit argv, cwd, environment, mount paths, and caller-selected
    # container options. The broker must resolve all of those from root-owned policy.
    return {
        "schema_version": BROKER_REQUEST_SCHEMA,
        "request_id": request_id,
        "workspace_id": workspace_id,
        "profile_id": spec.profile_id,
        "target": spec.target,
        "timeout_seconds": spec.timeout_seconds,
    }


def verify_broker_response(
    response: Any,
    *,
    public_key: bytes,
    expected_key_id: str,
    expected_request_id: str,
) -> dict[str, Any]:
    """Verify broker attestation before returning its signed execution result."""
    if not isinstance(response, dict):
        raise ValueError("broker response must be an object")
    if set(response) != {"schema_version", "request_id", "result", "signature"}:
        raise ValueError("broker response has unsupported or missing fields")
    if response.get("schema_version") != BROKER_RESPONSE_SCHEMA:
        raise ValueError("unsupported broker response schema")
    if response.get("request_id") != expected_request_id:
        raise ValueError("broker response request_id does not match the request")

    result = response.get("result")
    signature = response.get("signature")
    if not isinstance(result, dict) or result.get("schema_version") != EXECUTION_RESULT_SCHEMA:
        raise ValueError("broker response has an invalid execution result")
    if not isinstance(signature, dict) or set(signature) != {"algorithm", "key_id", "value"}:
        raise ValueError("broker response signature metadata is invalid")
    if signature.get("algorithm") != BROKER_SIGNATURE_ALGORITHM:
        raise ValueError("unsupported broker signature algorithm")
    if signature.get("key_id") != expected_key_id or not expected_key_id:
        raise ValueError("broker signing key ID does not match the trusted key")

    encoded = signature.get("value")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("broker signature value is missing")
    try:
        signature_bytes = base64.b64decode(encoded, validate=True)
        key = Ed25519PublicKey.from_public_bytes(public_key)
        key.verify(
            signature_bytes,
            _canonical_json({
                "schema_version": BROKER_RESPONSE_SCHEMA,
                "request_id": expected_request_id,
                "result": result,
            }),
        )
    except (ValueError, TypeError, binascii.Error, InvalidSignature) as exc:
        raise ValueError("broker response signature verification failed") from exc
    return result


__all__ = [
    "BROKER_REQUEST_SCHEMA",
    "BROKER_RESPONSE_SCHEMA",
    "BROKER_SIGNATURE_ALGORITHM",
    "build_broker_request",
    "verify_broker_response",
]
