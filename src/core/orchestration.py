"""
Evo Core - 策略与评估编排协议

目标：
1. 决策不只选择 capability，还要选择更细粒度的策略。
2. 执行后要有统一评估入口，便于后续成长层利用评估结果学习。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class StrategyDescriptor:
    id: str
    name: str
    capability_id: str
    task_type: str
    description: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class StrategySelection:
    strategy_id: str
    capability_id: str
    score: float
    reasons: List[str] = field(default_factory=list)
    runtime_adjustments: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "capability_id": self.capability_id,
            "score": self.score,
            "reasons": self.reasons,
            "runtime_adjustments": self.runtime_adjustments,
        }


@dataclass
class EvaluationResult:
    evaluator_id: str
    score: float
    verdict: str
    reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluator_id": self.evaluator_id,
            "score": self.score,
            "verdict": self.verdict,
            "reasons": self.reasons,
            "metrics": self.metrics,
        }


class StrategyProvider(ABC):
    @property
    @abstractmethod
    def descriptor(self) -> StrategyDescriptor:
        raise NotImplementedError

    def supports(self, capability_id: str, task_type: str) -> bool:
        descriptor = self.descriptor
        return descriptor.capability_id == capability_id and descriptor.task_type == task_type

    @abstractmethod
    def score(
        self,
        workspace: Path,
        tenant_id: str,
        parameters: Dict[str, Any],
        signals: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> StrategySelection:
        raise NotImplementedError


class EvaluatorProvider(ABC):
    id: str
    name: str

    @abstractmethod
    def supports(self, capability_id: str, task_type: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def evaluate(
        self,
        capability_id: str,
        task_type: str,
        result: Dict[str, Any],
        history: List[Dict[str, Any]],
        parameters: Dict[str, Any],
    ) -> EvaluationResult:
        raise NotImplementedError


class StrategyRegistry:
    def __init__(self):
        self._providers: Dict[str, StrategyProvider] = {}

    def register(self, provider: StrategyProvider) -> None:
        strategy_id = provider.descriptor.id
        if strategy_id in self._providers:
            raise ValueError(f"Strategy already registered: {strategy_id}")
        self._providers[strategy_id] = provider

    def matching(self, capability_id: str, task_type: str) -> List[StrategyProvider]:
        return [
            provider for provider in self._providers.values()
            if provider.supports(capability_id, task_type)
        ]


class EvaluatorRegistry:
    def __init__(self):
        self._providers: Dict[str, EvaluatorProvider] = {}

    def register(self, provider: EvaluatorProvider) -> None:
        if provider.id in self._providers:
            raise ValueError(f"Evaluator already registered: {provider.id}")
        self._providers[provider.id] = provider

    def matching(self, capability_id: str, task_type: str) -> List[EvaluatorProvider]:
        return [
            provider for provider in self._providers.values()
            if provider.supports(capability_id, task_type)
        ]


_strategy_registry: Optional[StrategyRegistry] = None
_evaluator_registry: Optional[EvaluatorRegistry] = None


def get_strategy_registry() -> StrategyRegistry:
    global _strategy_registry
    if _strategy_registry is None:
        _strategy_registry = StrategyRegistry()
    return _strategy_registry


def get_evaluator_registry() -> EvaluatorRegistry:
    global _evaluator_registry
    if _evaluator_registry is None:
        _evaluator_registry = EvaluatorRegistry()
    return _evaluator_registry


__all__ = [
    "StrategyDescriptor",
    "StrategySelection",
    "EvaluationResult",
    "StrategyProvider",
    "EvaluatorProvider",
    "StrategyRegistry",
    "EvaluatorRegistry",
    "get_strategy_registry",
    "get_evaluator_registry",
]
