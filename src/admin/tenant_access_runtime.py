"""Explicit, fail-closed tenant access checks for sensitive admin routes."""

from __future__ import annotations

import json
import os
from typing import Any


def tenant_role_for_user(
    user: dict[str, Any] | None,
    tenant_id: str,
    *,
    memberships_json: str | None = None,
) -> str | None:
    """Return the configured role for this authenticated user and tenant.

    Memberships are provisioned out-of-band through EVO_TENANT_MEMBERSHIPS_JSON.
    The shape is {"<user-id>": {"<tenant-id>": "tenant_admin|member|viewer"}}.
    Missing, malformed, or ambiguous configuration denies access.
    """
    if not isinstance(user, dict) or user.get("id") is None:
        return None
    normalized_tenant_id = str(tenant_id or "").strip()
    if not normalized_tenant_id:
        return None

    raw = memberships_json
    if raw is None:
        raw = os.getenv("EVO_TENANT_MEMBERSHIPS_JSON", "")
    try:
        memberships = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return None
    if not isinstance(memberships, dict):
        return None

    user_memberships = memberships.get(str(user.get("id")))
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
    return tenant_role_for_user(
        user, tenant_id, memberships_json=memberships_json
    ) is not None


__all__ = ["tenant_role_for_user", "user_can_access_tenant"]
