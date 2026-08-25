"""协作策略与交付物模板：纯配置读取，零业务工种硬编码。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _policies_file(workspace: Path) -> Path:
    path = workspace / ".admin" / "collaboration_policies.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _templates_file(workspace: Path) -> Path:
    path = workspace / ".admin" / "deliverable_templates.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _default_policies() -> dict[str, Any]:
    return {
        "version": 1,
        "default_policy_id": "default_cross_work_type",
        "message_templates": {
            "collaboration_ready_v1": (
                "所需能力 {{needed_capability}} 已由 {{provider_member_name}} 交付并通过审核。"
                "请在本任务当前阶段收尾后对接。{{deliverable_summary}}"
            ),
        },
        "policies": [
            {
                "policy_id": "default_cross_work_type",
                "title": "默认跨工种协作",
                "rules": [
                    {
                        "when_capability": "*",
                        "resolve_by": "trainer_manual",
                        "reviewer_role": "talent_development_officer",
                        "notify_on_approved": ["requester", "orchestrator"],
                        "message_template_id": "collaboration_ready_v1",
                    },
                ],
            },
        ],
    }


def _default_templates() -> dict[str, Any]:
    return {
        "version": 1,
        "items": [
            {
                "template_id": "api_contract_v1",
                "title": "HTTP API 契约",
                "capability_types": ["auth_api", "rest_api", "api_contract"],
                "fields": ["path", "method", "request", "response", "errors", "notes"],
            },
        ],
    }


def load_collaboration_policies(workspace: Path) -> dict[str, Any]:
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


def load_deliverable_templates(workspace: Path) -> dict[str, Any]:
    path = _templates_file(workspace)
    if not path.is_file():
        payload = _default_templates()
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = _default_templates()
    if not isinstance(payload, dict):
        payload = _default_templates()
    return payload


def get_deliverable_template(workspace: Path, template_id: str | None) -> dict[str, Any] | None:
    target = str(template_id or "").strip()
    if not target:
        return None
    items = load_deliverable_templates(workspace).get("items", [])
    if not isinstance(items, list):
        return None
    return next(
        (item for item in items if isinstance(item, dict) and str(item.get("template_id") or "").strip() == target),
        None,
    )


def _capability_matches(rule_capability: str, needed_capability: str) -> bool:
    rule = str(rule_capability or "").strip()
    needed = str(needed_capability or "").strip()
    if not needed:
        return False
    if rule in {"*", "any"}:
        return True
    return rule == needed


def resolve_collaboration_rule(
    workspace: Path,
    *,
    needed_capability: str,
    policy_id: str | None = None,
) -> dict[str, Any]:
    payload = load_collaboration_policies(workspace)
    policies = payload.get("policies") if isinstance(payload.get("policies"), list) else []
    target_policy_id = str(policy_id or payload.get("default_policy_id") or "default_cross_work_type").strip()
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
    matched = next(
        (
            rule for rule in rules
            if isinstance(rule, dict) and _capability_matches(str(rule.get("when_capability") or ""), needed_capability)
        ),
        None,
    )
    if not isinstance(matched, dict):
        matched = next((rule for rule in rules if isinstance(rule, dict)), {})
    message_templates = payload.get("message_templates") if isinstance(payload.get("message_templates"), dict) else {}
    template_id = str(matched.get("message_template_id") or "collaboration_ready_v1").strip()
    return {
        "policy_id": str(policy.get("policy_id") if isinstance(policy, dict) else target_policy_id),
        "rule": matched if isinstance(matched, dict) else {},
        "message_template_id": template_id,
        "message_template": str(message_templates.get(template_id) or message_templates.get("collaboration_ready_v1") or "").strip(),
        "deliverable_template": get_deliverable_template(workspace, str(matched.get("deliverable_template_id") or "").strip() or None),
    }


def render_message_template(template: str, variables: dict[str, Any]) -> str:
    content = str(template or "").strip()
    for key, value in variables.items():
        content = content.replace(f"{{{{{key}}}}}", str(value or "").strip())
    return content.strip()


def summarize_collaboration_policies(workspace: Path) -> dict[str, Any]:
    policies_payload = load_collaboration_policies(workspace)
    templates_payload = load_deliverable_templates(workspace)
    policy_items = policies_payload.get("policies") if isinstance(policies_payload.get("policies"), list) else []
    template_items = templates_payload.get("items") if isinstance(templates_payload.get("items"), list) else []
    return {
        "default_policy_id": policies_payload.get("default_policy_id"),
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
        "deliverable_templates": [
            {
                "template_id": item.get("template_id"),
                "title": item.get("title"),
                "capability_types": item.get("capability_types", []),
            }
            for item in template_items
            if isinstance(item, dict)
        ],
        "message_template_ids": list(
            (policies_payload.get("message_templates") or {}).keys()
            if isinstance(policies_payload.get("message_templates"), dict)
            else []
        ),
    }


__all__ = [
    "get_deliverable_template",
    "load_collaboration_policies",
    "load_deliverable_templates",
    "render_message_template",
    "resolve_collaboration_rule",
    "summarize_collaboration_policies",
]
