"""接单路由策略：纯配置读取，零业务工种硬编码。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _policies_file(workspace: Path) -> Path:
    path = workspace / ".admin" / "intake_routing_policies.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _default_policies() -> dict[str, Any]:
    return {
        "version": 1,
        "default_policy_id": "default_commercial_intake",
        "capability_aliases": {
            "content": ["content_draft", "channel_publish", "content_ops"],
            "publish": ["channel_publish", "content_draft"],
            "analytics": ["channel_analytics", "ops_analytics"],
        },
        "policies": [
            {
                "policy_id": "default_commercial_intake",
                "title": "默认商业接单路由",
                "rules": [
                    {
                        "when_capability": "*",
                        "resolve_by": "idle_member_by_capability",
                        "prefer_operation_prefix": "operation_",
                        "require_independent_ready": False,
                    },
                ],
            },
        ],
    }


def load_intake_routing_policies(workspace: Path) -> dict[str, Any]:
    path = _policies_file(workspace)
    if not path.is_file():
        payload = _default_policies()
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = _default_policies()
    if not isinstance(payload, dict):
        payload = _default_policies()
    return payload


def _capability_matches(rule_capability: str, needed: str) -> bool:
    rule = str(rule_capability or "").strip()
    target = str(needed or "").strip()
    if not target:
        return False
    if rule in {"*", "any"}:
        return True
    return rule == target


def expand_capabilities(workspace: Path, capabilities: list[str]) -> list[str]:
    policies = load_intake_routing_policies(workspace)
    aliases = policies.get("capability_aliases") if isinstance(policies.get("capability_aliases"), dict) else {}
    expanded: list[str] = []
    seen: set[str] = set()
    for raw in capabilities:
        key = str(raw or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        expanded.append(key)
        for alias in aliases.get(key, []) if isinstance(aliases.get(key), list) else []:
            alias_key = str(alias or "").strip()
            if alias_key and alias_key not in seen:
                seen.add(alias_key)
                expanded.append(alias_key)
    return expanded


def resolve_intake_rule(
    workspace: Path,
    *,
    needed_capabilities: list[str],
    policy_id: str | None = None,
) -> dict[str, Any]:
    payload = load_intake_routing_policies(workspace)
    policies = payload.get("policies") if isinstance(payload.get("policies"), list) else []
    target_policy_id = str(policy_id or payload.get("default_policy_id") or "default_commercial_intake").strip()
    policy = next(
        (
            item for item in policies
            if isinstance(item, dict) and str(item.get("policy_id") or "").strip() == target_policy_id
        ),
        None,
    )
    if not isinstance(policy, dict) and policies:
        policy = policies[0] if isinstance(policies[0], dict) else None
    rules = policy.get("rules") if isinstance(policy, dict) and isinstance(policy.get("rules"), list) else []
    expanded = expand_capabilities(workspace, needed_capabilities)
    matched = None
    for capability in expanded:
        matched = next(
            (
                rule for rule in rules
                if isinstance(rule, dict) and _capability_matches(str(rule.get("when_capability") or ""), capability)
            ),
            None,
        )
        if isinstance(matched, dict) and str(matched.get("when_capability") or "") not in {"*", "any"}:
            break
    if not isinstance(matched, dict):
        matched = next(
            (
                rule for rule in rules
                if isinstance(rule, dict) and str(rule.get("when_capability") or "") in {"*", "any"}
            ),
            None,
        )
    if not isinstance(matched, dict):
        matched = next((rule for rule in rules if isinstance(rule, dict)), {})
    return {
        "policy_id": str(policy.get("policy_id") if isinstance(policy, dict) else target_policy_id),
        "rule": matched if isinstance(matched, dict) else {},
        "expanded_capabilities": expanded,
    }


def summarize_intake_policies(workspace: Path) -> dict[str, Any]:
    payload = load_intake_routing_policies(workspace)
    policy_items = payload.get("policies") if isinstance(payload.get("policies"), list) else []
    return {
        "default_policy_id": payload.get("default_policy_id"),
        "policy_count": len([item for item in policy_items if isinstance(item, dict)]),
        "policies": [
            {
                "policy_id": item.get("policy_id"),
                "title": item.get("title"),
                "rule_count": len(item.get("rules", [])) if isinstance(item.get("rules"), list) else 0,
            }
            for item in policy_items
            if isinstance(item, dict)
        ],
        "capability_alias_keys": sorted(
            str(key) for key in (payload.get("capability_aliases") or {}).keys()
        ) if isinstance(payload.get("capability_aliases"), dict) else [],
    }
