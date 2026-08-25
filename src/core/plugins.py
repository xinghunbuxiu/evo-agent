"""
Evo Core - 插件加载器

支持从本地目录动态发现并加载企业/第三方扩展：
- capability providers
- strategy providers
- evaluator providers
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional

from .capabilities import CapabilityProvider, CapabilityRegistry, get_capability_registry
from .orchestration import (
    EvaluatorProvider,
    EvaluatorRegistry,
    StrategyProvider,
    StrategyRegistry,
    get_evaluator_registry,
    get_strategy_registry,
)
from .capability_types import infer_capability_type, normalize_capability_type


@dataclass
class PluginRegistrationResult:
    plugin_name: str
    module_path: str
    manifest_path: str = ""
    version: str = ""
    capability_types: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    strategies: List[str] = field(default_factory=list)
    evaluators: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class PluginLoadSummary:
    plugin_dirs: List[str]
    loaded: List[PluginRegistrationResult] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_dirs": self.plugin_dirs,
            "loaded": [
                {
                    "plugin_name": item.plugin_name,
                    "module_path": item.module_path,
                    "manifest_path": item.manifest_path,
                    "version": item.version,
                    "capability_types": item.capability_types,
                    "capabilities": item.capabilities,
                    "strategies": item.strategies,
                    "evaluators": item.evaluators,
                    "errors": item.errors,
                }
                for item in self.loaded
            ],
            "skipped": self.skipped,
        }


class PluginLoader:
    """本地插件加载器。"""

    capability_sources: Dict[str, str] = {}
    strategy_sources: Dict[str, str] = {}
    evaluator_sources: Dict[str, str] = {}
    manifests: Dict[str, Dict[str, Any]] = {}

    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistry] = None,
        strategy_registry: Optional[StrategyRegistry] = None,
        evaluator_registry: Optional[EvaluatorRegistry] = None,
    ):
        self.capability_registry = capability_registry or get_capability_registry()
        self.strategy_registry = strategy_registry or get_strategy_registry()
        self.evaluator_registry = evaluator_registry or get_evaluator_registry()

    def load_from_paths(self, plugin_dirs: List[Path]) -> PluginLoadSummary:
        summary = PluginLoadSummary(plugin_dirs=[str(path) for path in plugin_dirs])

        for plugin_dir in plugin_dirs:
            if not plugin_dir.exists():
                summary.skipped.append(f"{plugin_dir} (missing)")
                continue

            plugin_files = sorted(plugin_dir.glob("*/plugin.py"))
            if not plugin_files:
                plugin_files = sorted(plugin_dir.glob("plugin.py"))

            for plugin_file in plugin_files:
                try:
                    result = self._load_plugin(plugin_file)
                    summary.loaded.append(result)
                except Exception as exc:
                    summary.skipped.append(f"{plugin_file}: {exc}")

        return summary

    def load_default(self, workspace: Optional[Path] = None) -> PluginLoadSummary:
        workspace = workspace or Path.cwd()
        plugin_paths = self._resolve_default_plugin_dirs(workspace)
        return self.load_from_paths(plugin_paths)

    def _resolve_default_plugin_dirs(self, workspace: Path) -> List[Path]:
        configured = os.getenv("EVO_PLUGIN_DIRS", "")
        dirs: List[Path] = []
        if configured:
            dirs.extend(Path(item).expanduser() for item in configured.split(os.pathsep) if item.strip())

        dirs.append(workspace / "plugins")
        return dirs

    def _load_plugin(self, plugin_file: Path) -> PluginRegistrationResult:
        manifest = self._load_manifest(plugin_file.parent)
        module_name = f"evo_plugin_{plugin_file.parent.name}_{abs(hash(str(plugin_file)))}"
        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load plugin spec: {plugin_file}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        plugin_name = manifest.get("name") or getattr(module, "PLUGIN_NAME", plugin_file.parent.name)
        result = PluginRegistrationResult(
            plugin_name=plugin_name,
            module_path=str(plugin_file),
            manifest_path=str(plugin_file.parent / "manifest.json"),
            version=str(manifest.get("version", "")),
        )
        self.manifests[plugin_name] = manifest
        result.capability_types = self._resolve_plugin_capability_types(manifest)

        register_fn = self._extract_module_items(module, "register")
        if not register_fn:
            raise RuntimeError("plugin.py must expose register()")

        registered = register_fn()
        if not isinstance(registered, dict):
            raise RuntimeError("register() must return a dict")

        for provider in registered.get("capabilities", []):
            self._register_capability(provider, result)
        for provider in registered.get("strategies", []):
            self._register_strategy(provider, result)
        for provider in registered.get("evaluators", []):
            self._register_evaluator(provider, result)

        return result

    def _load_manifest(self, plugin_dir: Path) -> Dict[str, Any]:
        manifest_path = plugin_dir / "manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError(f"missing manifest.json in {plugin_dir}")
        with open(manifest_path) as f:
            manifest = json.load(f)

        required = ["name", "version", "compatibility"]
        missing = [key for key in required if key not in manifest]
        if missing:
            raise RuntimeError(f"manifest missing required fields: {missing}")
        return manifest

    def _extract_module_items(self, module: ModuleType, name: str):
        return getattr(module, name, None)

    def _register_capability(self, provider: CapabilityProvider, result: PluginRegistrationResult) -> None:
        self.capability_registry.register(provider)
        result.capabilities.append(provider.descriptor.id)
        self.capability_sources[provider.descriptor.id] = result.plugin_name
        capability_type = infer_capability_type(
            capability_type=getattr(provider.descriptor, "capability_type", None),
            capability_id=provider.descriptor.id,
            tags=provider.descriptor.tags,
        )
        if capability_type not in result.capability_types:
            result.capability_types.append(capability_type)

    def _register_strategy(self, provider: StrategyProvider, result: PluginRegistrationResult) -> None:
        self.strategy_registry.register(provider)
        result.strategies.append(provider.descriptor.id)
        self.strategy_sources[provider.descriptor.id] = result.plugin_name

    def _register_evaluator(self, provider: EvaluatorProvider, result: PluginRegistrationResult) -> None:
        self.evaluator_registry.register(provider)
        result.evaluators.append(provider.id)
        self.evaluator_sources[provider.id] = result.plugin_name

    def _resolve_plugin_capability_types(self, manifest: Dict[str, Any]) -> List[str]:
        values = manifest.get("capability_types", [])
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            return []
        normalized: List[str] = []
        for item in values:
            if not isinstance(item, str):
                continue
            capability_type = normalize_capability_type(item)
            if capability_type not in normalized:
                normalized.append(capability_type)
        return normalized

    @classmethod
    def get_capability_plugin(cls, capability_id: str) -> Optional[str]:
        return cls.capability_sources.get(capability_id)

    @classmethod
    def get_strategy_plugin(cls, strategy_id: str) -> Optional[str]:
        return cls.strategy_sources.get(strategy_id)

    @classmethod
    def get_evaluator_plugin(cls, evaluator_id: str) -> Optional[str]:
        return cls.evaluator_sources.get(evaluator_id)


__all__ = [
    "PluginRegistrationResult",
    "PluginLoadSummary",
    "PluginLoader",
]
