"""Explicit, fail-closed tenant access checks for sensitive admin routes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate membership key: {key}")
        result[key] = value
    return result


def _load_memberships(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        path_value = os.getenv("EVO_TENANT_MEMBERSHIPS_FILE", "").strip()
        if path_value:
            try:
                raw = Path(path_value).expanduser().read_text(encoding="utf-8")
            except OSError:
                return None
        else:
            raw = os.getenv("EVO_TENANT_MEMBERSHIPS_JSON", "")
    try:
        memberships = json.loads(raw, object_pairs_hook=_reject_duplicate_keys) if raw else {}
    except (TypeError, ValueError):
        return None
    return memberships if isinstance(memberships, dict) else None


def tenant_role_for_user(
    user: dict[str, Any] | None,
    tenant_id: str,
    *,
    memberships_json: str | None = None,
) -> str | None:
    """Return a configured role; missing, malformed, or ambiguous config denies access.

    File-based provisioning uses EVO_TENANT_MEMBERSHIPS_FILE. The JSON environment
    variable remains available for small deployments and tests.
    """
    if not isinstance(user, dict) or user.get("id") is None:
        return None
    provider = str(user.get("auth_provider") or "").strip()
    if provider not in {"password", "gitee"}:
        return None
    normalized_tenant_id = str(tenant_id or "").strip()
    if not normalized_tenant_id:
        return None

    memberships = _load_memberships(memberships_json)
    if memberships is None:
        return None
    subject_id = f"{provider}:{user.get('id')}"
    user_memberships = memberships.get(subject_id)
    if not isinstance(user_memberships, dict):
        return None
    role = user_memberships.get(normalized_tenant_id)
    if role not in {"tenant_admin", "member", "viewer"}:
        return None
    return role


def user_can_access_tenant(
    user: dict[str, Any] | None,
    tenant_id: str,
    *,
    memberships_json: str | None = None,
) -> bool:
    return tenant_role_for_user(user, tenant_id, memberships_json=memberships_json) is not None


__all__ = ["tenant_role_for_user", "user_can_access_tenant"]
