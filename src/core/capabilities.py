"""
Evo Core - 可插拔能力协议与注册中心

目标：
1. 核心内核只依赖能力协议，不依赖具体领域目录。
2. 内置 JavaScript/Android/PC 能力与未来企业定制能力统一接入。
3. 为后续决策层、成长层、企业扩展层提供稳定边界。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CapabilityDescriptor:
    """能力元数据描述。"""

    id: str
    name: str
    version: str
    provider_kind: str = "builtin"
    capability_type: str = "general_dev"
    description: str = ""
    supported_tasks: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    customizable: bool = True


@dataclass
class TaskContext:
    """统一任务上下文。"""

    workspace: Path
    tenant_id: str = "default"
    task_type: str = "analyze"
    input_path: Optional[Path] = None
    source_dir: Optional[Path] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    signals: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TaskResult:
    """统一任务结果。"""

    success: bool
    capability_id: str
    task_type: str
    summary: str = ""
    confidence: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)
    feedback: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "capability_id": self.capability_id,
            "task_type": self.task_type,
            "summary": self.summary,
            "confidence": self.confidence,
            **self.data,
            "feedback": self.feedback,
        }


class CapabilityProvider(ABC):
    """
    可插拔能力协议。

    未来企业可以通过实现这个协议接入：
    - 自定义分析器
    - 自定义重构器
    - 自定义经验回写/评估逻辑
    """

    @property
    @abstractmethod
    def descriptor(self) -> CapabilityDescriptor:
        raise NotImplementedError

    def supports_task(self, task_type: str) -> bool:
        return task_type in self.descriptor.supported_tasks

    def init_workspace(self, workspace: Path, tenant_id: str = "default") -> Dict[str, Any]:
        return {
            "success": True,
            "workspace": str(workspace),
            "tenant_id": tenant_id,
            "capability_id": self.descriptor.id,
            "status": "ready",
        }

    @abstractmethod
    def execute(self, context: TaskContext) -> TaskResult:
        raise NotImplementedError


class CapabilityRegistry:
    """能力注册中心。"""

    def __init__(self):
        self._providers: Dict[str, CapabilityProvider] = {}

    def register(self, provider: CapabilityProvider) -> None:
        capability_id = provider.descriptor.id
        if capability_id in self._providers:
            raise ValueError(f"Capability already registered: {capability_id}")
        self._providers[capability_id] = provider

    def get(self, capability_id: str) -> CapabilityProvider:
        if capability_id not in self._providers:
            raise KeyError(f"Unknown capability: {capability_id}")
        return self._providers[capability_id]

    def list_descriptors(self) -> List[CapabilityDescriptor]:
        return [provider.descriptor for provider in self._providers.values()]

    def list_providers(self) -> List[CapabilityProvider]:
        return list(self._providers.values())

    def matching_providers(self, task_type: str) -> List[CapabilityProvider]:
        return [
            provider for provider in self._providers.values()
            if provider.supports_task(task_type)
        ]

    def find_for_task(self, task_type: str, preferred_tags: Optional[List[str]] = None) -> Optional[CapabilityProvider]:
        preferred_tags = preferred_tags or []

        matching = self.matching_providers(task_type)
        if not matching:
            return None

        if preferred_tags:
            preferred = [
                provider for provider in matching
                if any(tag in provider.descriptor.tags for tag in preferred_tags)
            ]
            if preferred:
                return preferred[0]

        return matching[0]

    def execute(
        self,
        task_type: str,
        workspace: Path,
        tenant_id: str = "default",
        capability_id: Optional[str] = None,
        input_path: Optional[Path] = None,
        source_dir: Optional[Path] = None,
        parameters: Optional[Dict[str, Any]] = None,
        signals: Optional[Dict[str, Any]] = None,
    ) -> TaskResult:
        provider = self.get(capability_id) if capability_id else self.find_for_task(task_type)
        if not provider:
            raise ValueError(f"No capability available for task: {task_type}")

        context = TaskContext(
            workspace=workspace,
            tenant_id=tenant_id,
            task_type=task_type,
            input_path=input_path,
            source_dir=source_dir,
            parameters=parameters or {},
            signals=signals or {},
        )
        return provider.execute(context)


_registry: Optional[CapabilityRegistry] = None


def get_capability_registry() -> CapabilityRegistry:
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry


__all__ = [
    "CapabilityDescriptor",
    "TaskContext",
    "TaskResult",
    "CapabilityProvider",
    "CapabilityRegistry",
    "get_capability_registry",
]
