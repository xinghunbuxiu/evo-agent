"""
成长/共享策略的纯函数运行时。
"""

from __future__ import annotations


def resolve_effective_growth_policy(*, tenant_manager, tenant_id: str, work_type_policy: dict | None) -> dict:
    tenant_policy = tenant_manager.get_knowledge_policy(tenant_id)
    work_type_policy = work_type_policy if isinstance(work_type_policy, dict) else {}
    share_default = str(work_type_policy.get("share_default") or "").strip().lower()
    effective = dict(tenant_policy)
    source = "tenant_default"
    if share_default == "private_only":
        effective["share_mode"] = "private_only"
        effective["allow_platform_promotion"] = False
        effective["review_required"] = True
        source = "work_type_override"
    elif share_default == "reviewed_share":
        effective["share_mode"] = "reviewed_share"
        effective["allow_platform_promotion"] = bool(tenant_policy.get("allow_platform_promotion", False))
        effective["review_required"] = True
        source = "work_type_override"
    elif share_default == "platform_share":
        effective["share_mode"] = "platform_share"
        effective["allow_platform_promotion"] = True
        effective["review_required"] = bool(tenant_policy.get("review_required", True))
        source = "work_type_override"
    return {
        **effective,
        "source": source,
        "work_type_mode": work_type_policy.get("mode"),
        "share_default": share_default or None,
    }


def growth_policy_decision_label(policy: dict | None) -> str:
    policy = policy if isinstance(policy, dict) else {}
    share_mode = str(policy.get("share_mode") or "private_only")
    allow_platform = bool(policy.get("allow_platform_promotion", False))
    review_required = bool(policy.get("review_required", True))
    if share_mode == "private_only":
        return "private_memory_only"
    if allow_platform and not review_required:
        return "platform_promotable"
    if allow_platform and review_required:
        return "review_before_platform"
    return "reviewed_share_only"


def effective_platform_promotion_status(policy: dict | None) -> dict:
    policy = policy if isinstance(policy, dict) else {}
    share_mode = str(policy.get("share_mode") or "private_only")
    allow_platform_promotion = bool(policy.get("allow_platform_promotion", False))
    review_required = bool(policy.get("review_required", True))
    allowed = share_mode != "private_only" and allow_platform_promotion
    reason = (
        "work type policy is private_only"
        if share_mode == "private_only"
        else "platform promotion disabled by effective policy"
        if not allow_platform_promotion
        else "review required before platform promotion"
        if review_required
        else "promotion allowed"
    )
    return {
        "allowed": allowed,
        "share_mode": share_mode,
        "allow_platform_promotion": allow_platform_promotion,
        "review_required": review_required,
        "reason": reason,
        "source": policy.get("source"),
    }
