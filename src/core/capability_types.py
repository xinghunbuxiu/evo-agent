"""
Evo Core - Capability Type Taxonomy

把历史 domain 概念逐步收敛成 capability_type：
- plugin 负责接入能力核
- capability_type 负责描述能力类别
- skill / experience / strategy 负责在该类别下持续成长
"""

from __future__ import annotations

from typing import Any


CAPABILITY_TYPE_ALIASES = {
    "js": "javascript_reverse",
    "javascript": "javascript_reverse",
    "javascript_reverse": "javascript_reverse",
    "android": "android_reverse",
    "android_reverse": "android_reverse",
    "pc": "pc_reverse",
    "pc_reverse": "pc_reverse",
    "dev": "general_dev",
    "general_dev": "general_dev",
    "crawler": "crawler",
    "automation": "automation",
    "document": "document_parse",
    "document_parse": "document_parse",
    "pdf": "document_parse",
}


CAPABILITY_TYPE_CATALOG = {
    "javascript_reverse": {
        "name": "JavaScript Reverse",
        "description": "JavaScript 逆向、分析、重构与经验沉淀",
        "legacy_domains": ["js", "javascript"],
    },
    "android_reverse": {
        "name": "Android Reverse",
        "description": "Android 逆向、脱壳、协议分析与案例沉淀",
        "legacy_domains": ["android"],
    },
    "pc_reverse": {
        "name": "PC Reverse",
        "description": "PC 客户端逆向、协议与自动化分析",
        "legacy_domains": ["pc"],
    },
    "general_dev": {
        "name": "General Dev",
        "description": "开发辅助、脚本处理、通用工程能力",
        "legacy_domains": ["dev"],
    },
    "crawler": {
        "name": "Crawler",
        "description": "网页抓取、反爬识别、采集策略与经验",
        "legacy_domains": [],
    },
    "automation": {
        "name": "Automation",
        "description": "浏览器/桌面/工作流自动化与编排能力",
        "legacy_domains": [],
    },
    "document_parse": {
        "name": "Document Parse",
        "description": "PDF/Office/文本材料解析、抽取、结构化",
        "legacy_domains": [],
    },
}


def normalize_capability_type(value: str | None, default: str = "general_dev") -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    return CAPABILITY_TYPE_ALIASES.get(raw, raw.replace("-", "_"))


def infer_capability_type(
    *,
    capability_type: str | None = None,
    domain: str | None = None,
    capability_id: str | None = None,
    tags: list[str] | None = None,
    default: str = "general_dev",
) -> str:
    if capability_type:
        return normalize_capability_type(capability_type, default=default)
    if domain:
        return normalize_capability_type(domain, default=default)
    for item in tags or []:
        normalized = normalize_capability_type(item, default="")
        if normalized:
            return normalized
    raw_capability_id = str(capability_id or "").lower()
    if "javascript" in raw_capability_id:
        return "javascript_reverse"
    if "android" in raw_capability_id:
        return "android_reverse"
    if ".pc" in raw_capability_id or raw_capability_id.startswith("pc"):
        return "pc_reverse"
    return default


def capability_type_label(value: str | None) -> str:
    normalized = normalize_capability_type(value)
    return str(CAPABILITY_TYPE_CATALOG.get(normalized, {}).get("name") or normalized)


def capability_type_catalog() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key, value in CAPABILITY_TYPE_CATALOG.items():
        items.append({
            "id": key,
            "name": value.get("name", key),
            "description": value.get("description", ""),
            "legacy_domains": value.get("legacy_domains", []),
        })
    return items


def legacy_domains_for_capability_type(value: str | None) -> list[str]:
    normalized = normalize_capability_type(value)
    config = CAPABILITY_TYPE_CATALOG.get(normalized, {})
    legacy = [str(item) for item in config.get("legacy_domains", []) if str(item).strip()]
    return legacy or [normalized]


__all__ = [
    "CAPABILITY_TYPE_ALIASES",
    "CAPABILITY_TYPE_CATALOG",
    "normalize_capability_type",
    "infer_capability_type",
    "capability_type_label",
    "capability_type_catalog",
    "legacy_domains_for_capability_type",
]
