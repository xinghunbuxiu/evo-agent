"""
Evo Core - 多租户管理

支持多用户/多项目隔离
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from .capability_types import legacy_domains_for_capability_type, normalize_capability_type

DEFAULT_KNOWLEDGE_POLICY = {
    "share_mode": "private_only",
    "allow_platform_promotion": False,
    "review_required": True,
}

DEFAULT_EXTERNAL_LEARNING_POLICY = {
    "allow_ai_assist": True,
    "allow_web_research": True,
    "allow_enterprise_sources": True,
    "source_priority": ["local_memory", "platform_shared", "enterprise_repo", "official_docs", "web_search", "ai_assist"],
    "validation_required": True,
    # OpenAI-compatible model provider (DeepSeek / local gateway / etc.)
    "model_provider": {
        "enabled": False,
        "label": "openai_compatible",
        "base_url": "",
        "api_key": "",
        "model": "",
    },
}


@dataclass
class Tenant:
    """租户定义"""
    id: str
    name: str
    domains: list[str]  # 该租户可访问的领域
    capability_types: list[str]
    config: Dict[str, Any]


class TenantManager:
    """租户管理器"""
    
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.tenants_dir = workspace / ".tenants"
        self.tenants_dir.mkdir(parents=True, exist_ok=True)
    
    def _normalize_capability_types(self, capability_types: list[str] | None = None, domains: list[str] | None = None) -> list[str]:
        raw_values = capability_types or domains or ["javascript", "android", "pc", "dev"]
        normalized: list[str] = []
        for item in raw_values:
            normalized_item = normalize_capability_type(item)
            if normalized_item not in normalized:
                normalized.append(normalized_item)
        return normalized

    def _capability_types_to_domains(self, capability_types: list[str]) -> list[str]:
        domains: list[str] = []
        for capability_type in capability_types:
            for domain in legacy_domains_for_capability_type(capability_type):
                if domain not in domains:
                    domains.append(domain)
        return domains

    def create_tenant(self, tenant_id: str, name: str, domains: list[str] = None) -> Tenant:
        """创建租户"""
        tenant_dir = self.tenants_dir / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建标准目录结构
        for subdir in ["experiences", "skills", "strategies", "data"]:
            (tenant_dir / subdir).mkdir(exist_ok=True)
        
        capability_types = self._normalize_capability_types(domains=domains)
        tenant = Tenant(
            id=tenant_id,
            name=name,
            domains=self._capability_types_to_domains(capability_types),
            capability_types=capability_types,
            config={
                "plugins": {
                    "enabled": [],
                    "disabled": [],
                },
                "knowledge_policy": dict(DEFAULT_KNOWLEDGE_POLICY),
                "external_learning_policy": dict(DEFAULT_EXTERNAL_LEARNING_POLICY),
                "strategy_overrides": {},
            }
        )
        
        # 保存租户信息
        with open(tenant_dir / "tenant.json", "w") as f:
            json.dump({
                "id": tenant.id,
                "name": tenant.name,
                "domains": tenant.domains,
                "capability_types": tenant.capability_types,
                "config": tenant.config,
            }, f, indent=2)
        
        return tenant
    
    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """获取租户"""
        tenant_file = self.tenants_dir / tenant_id / "tenant.json"
        if not tenant_file.is_file():
            return None
        
        with open(tenant_file) as f:
            data = json.load(f)
            capability_types = self._normalize_capability_types(
                capability_types=data.get("capability_types"),
                domains=data.get("domains"),
            )
            normalized = {
                **data,
                "domains": self._capability_types_to_domains(capability_types),
                "capability_types": capability_types,
            }
            if normalized != data:
                tenant = Tenant(**normalized)
                self._save_tenant(tenant)
                return tenant
            return Tenant(**normalized)
    
    def list_tenants(self) -> list[str]:
        """列出所有租户"""
        if not self.tenants_dir.is_dir():
            return []
        return [d.name for d in self.tenants_dir.iterdir() if d.is_dir()]

    def get_plugin_policy(self, tenant_id: str) -> Dict[str, list[str]]:
        """读取租户插件启停策略。"""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"enabled": [], "disabled": []}

        plugins = tenant.config.get("plugins", {}) if isinstance(tenant.config, dict) else {}
        enabled = plugins.get("enabled", []) if isinstance(plugins, dict) else []
        disabled = plugins.get("disabled", []) if isinstance(plugins, dict) else []
        return {
            "enabled": enabled if isinstance(enabled, list) else [],
            "disabled": disabled if isinstance(disabled, list) else [],
        }

    def set_plugin_policy(
        self,
        tenant_id: str,
        enabled: Optional[list[str]] = None,
        disabled: Optional[list[str]] = None,
    ) -> Tenant:
        """更新租户插件启停策略。"""
        tenant = self.get_tenant(tenant_id)
        if tenant is None:
            tenant = self.create_tenant(tenant_id, tenant_id)

        tenant.config = tenant.config or {}
        tenant.config["plugins"] = {
            "enabled": enabled or [],
            "disabled": disabled or [],
        }
        self._save_tenant(tenant)
        return tenant

    def get_strategy_overrides(self, tenant_id: str) -> Dict[str, Dict[str, Any]]:
        """读取租户策略运行时覆盖配置。"""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {}

        config = tenant.config if isinstance(tenant.config, dict) else {}
        overrides = config.get("strategy_overrides", {})
        if not isinstance(overrides, dict):
            return {}

        normalized: Dict[str, Dict[str, Any]] = {}
        changed = False
        now = datetime.now()
        for strategy_id, value in overrides.items():
            if isinstance(strategy_id, str) and isinstance(value, dict):
                expires_at = value.get("expires_at")
                active = bool(value.get("active", True))
                if expires_at and isinstance(expires_at, str):
                    try:
                        if datetime.fromisoformat(expires_at) <= now:
                            changed = True
                            continue
                    except ValueError:
                        pass
                if not active:
                    continue
                normalized[strategy_id] = value
        if changed:
            config["strategy_overrides"] = normalized
            tenant.config = config
            self._save_tenant(tenant)
        return normalized

    def set_strategy_override(
        self,
        tenant_id: str,
        strategy_id: str,
        *,
        weight_delta: float = 0.0,
        preferred: bool = False,
        blocked: bool = False,
        source: Optional[str] = None,
        note: Optional[str] = None,
        updated_at: Optional[str] = None,
        expires_at: Optional[str] = None,
        active: bool = True,
    ) -> Tenant:
        """写入单条策略运行时覆盖。"""
        tenant = self.get_tenant(tenant_id)
        if tenant is None:
            tenant = self.create_tenant(tenant_id, tenant_id)

        tenant.config = tenant.config or {}
        overrides = tenant.config.get("strategy_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}

        overrides[strategy_id] = {
            "weight_delta": weight_delta,
            "preferred": preferred,
            "blocked": blocked,
            "source": source or "manual",
            "note": note or "",
            "updated_at": updated_at,
            "expires_at": expires_at,
            "active": active,
        }
        tenant.config["strategy_overrides"] = overrides
        self._save_tenant(tenant)
        return tenant

    def clear_strategy_override(self, tenant_id: str, strategy_id: str) -> Tenant:
        """删除单条策略运行时覆盖。"""
        tenant = self.get_tenant(tenant_id)
        if tenant is None:
            tenant = self.create_tenant(tenant_id, tenant_id)

        tenant.config = tenant.config or {}
        overrides = tenant.config.get("strategy_overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
        overrides.pop(strategy_id, None)
        tenant.config["strategy_overrides"] = overrides
        self._save_tenant(tenant)
        return tenant

    def _save_tenant(self, tenant: Tenant) -> None:
        tenant_dir = self.tenants_dir / tenant.id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        with open(tenant_dir / "tenant.json", "w") as f:
            json.dump({
                "id": tenant.id,
                "name": tenant.name,
                "domains": tenant.domains,
                "capability_types": tenant.capability_types,
                "config": tenant.config,
            }, f, indent=2)

    def get_git_knowledge_config(self, tenant_id: str) -> Dict[str, Any]:
        tenant = self.get_tenant(tenant_id)
        if not tenant or not isinstance(tenant.config, dict):
            return {}
        git_config = tenant.config.get("git_knowledge", {})
        return git_config if isinstance(git_config, dict) else {}

    def set_git_knowledge_config(self, tenant_id: str, git_knowledge: Dict[str, Any]) -> Tenant:
        tenant = self.get_tenant(tenant_id)
        if tenant is None:
            tenant = self.create_tenant(tenant_id, tenant_id)
        tenant.config = tenant.config or {}
        tenant.config["git_knowledge"] = git_knowledge
        self._save_tenant(tenant)
        return tenant

    def get_knowledge_policy(self, tenant_id: str) -> Dict[str, Any]:
        tenant = self.get_tenant(tenant_id)
        if not tenant or not isinstance(tenant.config, dict):
            return dict(DEFAULT_KNOWLEDGE_POLICY)
        current = tenant.config.get("knowledge_policy", {})
        if not isinstance(current, dict):
            current = {}
        return {
            **DEFAULT_KNOWLEDGE_POLICY,
            **current,
        }

    def set_knowledge_policy(
        self,
        tenant_id: str,
        *,
        share_mode: str,
        allow_platform_promotion: bool,
        review_required: bool,
    ) -> Tenant:
        tenant = self.get_tenant(tenant_id)
        if tenant is None:
            tenant = self.create_tenant(tenant_id, tenant_id)
        tenant.config = tenant.config or {}
        tenant.config["knowledge_policy"] = {
            "share_mode": share_mode,
            "allow_platform_promotion": allow_platform_promotion,
            "review_required": review_required,
        }
        self._save_tenant(tenant)
        return tenant

    def get_external_learning_policy(self, tenant_id: str) -> Dict[str, Any]:
        default_provider = dict(DEFAULT_EXTERNAL_LEARNING_POLICY.get("model_provider") or {})
        tenant = self.get_tenant(tenant_id)
        if not tenant or not isinstance(tenant.config, dict):
            return {
                **DEFAULT_EXTERNAL_LEARNING_POLICY,
                "model_provider": default_provider,
            }
        current = tenant.config.get("external_learning_policy", {})
        if not isinstance(current, dict):
            current = {}
        merged = {
            **DEFAULT_EXTERNAL_LEARNING_POLICY,
            **current,
        }
        raw_provider = current.get("model_provider") if isinstance(current.get("model_provider"), dict) else {}
        merged["model_provider"] = {
            **default_provider,
            **raw_provider,
            "enabled": bool(raw_provider.get("enabled", default_provider.get("enabled"))),
            "label": str(raw_provider.get("label") or default_provider.get("label") or "openai_compatible").strip()
            or "openai_compatible",
            "base_url": str(raw_provider.get("base_url") or "").strip().rstrip("/"),
            "api_key": str(raw_provider.get("api_key") or "").strip(),
            "model": str(raw_provider.get("model") or "").strip(),
        }
        return merged

    def set_external_learning_policy(
        self,
        tenant_id: str,
        *,
        allow_ai_assist: bool,
        allow_web_research: bool,
        allow_enterprise_sources: bool,
        source_priority: list[str],
        validation_required: bool,
        model_provider: dict | None = None,
    ) -> Tenant:
        tenant = self.get_tenant(tenant_id)
        if tenant is None:
            tenant = self.create_tenant(tenant_id, tenant_id)
        tenant.config = tenant.config or {}
        existing_policy = tenant.config.get("external_learning_policy")
        existing_provider = (
            existing_policy.get("model_provider")
            if isinstance(existing_policy, dict) and isinstance(existing_policy.get("model_provider"), dict)
            else {}
        )
        default_provider = dict(DEFAULT_EXTERNAL_LEARNING_POLICY.get("model_provider") or {})
        incoming = model_provider if isinstance(model_provider, dict) else {}
        next_provider = {
            **default_provider,
            **existing_provider,
        }
        for key in ("enabled", "label", "base_url", "model"):
            if key in incoming:
                next_provider[key] = incoming.get(key)
        if "api_key" in incoming:
            raw_key = str(incoming.get("api_key") or "").strip()
            if raw_key and "*" not in raw_key:
                next_provider["api_key"] = raw_key
        next_provider = {
            "enabled": bool(next_provider.get("enabled")),
            "label": str(next_provider.get("label") or "openai_compatible").strip() or "openai_compatible",
            "base_url": str(next_provider.get("base_url") or "").strip().rstrip("/"),
            "api_key": str(next_provider.get("api_key") or "").strip(),
            "model": str(next_provider.get("model") or "").strip(),
        }
        tenant.config["external_learning_policy"] = {
            "allow_ai_assist": allow_ai_assist,
            "allow_web_research": allow_web_research,
            "allow_enterprise_sources": allow_enterprise_sources,
            "source_priority": source_priority or list(DEFAULT_EXTERNAL_LEARNING_POLICY["source_priority"]),
            "validation_required": validation_required,
            "model_provider": next_provider,
        }
        self._save_tenant(tenant)
        return tenant


__all__ = ["Tenant", "TenantManager"]
