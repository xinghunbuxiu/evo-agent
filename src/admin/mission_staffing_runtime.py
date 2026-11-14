"""Explicit Talent Center employee selection rules."""

from __future__ import annotations

from typing import Any


def resolve_selected_employee(*, members: list[dict[str, Any]], selected_member_id: str) -> dict[str, Any] | None:
    """Resolve only an explicit, unique, active employee selection."""
    selected_id = str(selected_member_id or "").strip()
    if not selected_id:
        return None
    matches = [
        item for item in members
        if isinstance(item, dict) and str(item.get("member_id") or "").strip() == selected_id
    ]
    if len(matches) != 1:
        return None
    member = matches[0]
    if str(member.get("status") or "active").strip() != "active":
        return None
    if str(member.get("primary_role") or "").strip() == "talent_development":
        return None
    return member


__all__ = ["resolve_selected_employee"]
