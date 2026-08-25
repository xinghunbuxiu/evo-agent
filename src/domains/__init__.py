"""
Evo 内置能力注册入口。

这里保留现有 domains 目录，但语义调整为：
内置 capability providers 的集合，而不是写死的产品边界。

真正决定知识归属和后续扩展方向的，应逐步迁移到 capability_type。
"""

from __future__ import annotations

from core.capabilities import CapabilityRegistry, get_capability_registry
from core.orchestration import (
    EvaluatorRegistry,
    StrategyRegistry,
    get_evaluator_registry,
    get_strategy_registry,
)
from .javascript.provider import JavaScriptCapabilityProvider
from .javascript.strategy import (
    JavaScriptAnalyzeStrategy,
    JavaScriptEvaluator,
    JavaScriptReconstructStrategy,
)


def register_builtin_capabilities(registry: CapabilityRegistry | None = None) -> CapabilityRegistry:
    registry = registry or get_capability_registry()

    registered_ids = {descriptor.id for descriptor in registry.list_descriptors()}
    provider = JavaScriptCapabilityProvider()
    if provider.descriptor.id not in registered_ids:
        registry.register(provider)

    return registry


def register_builtin_orchestration(
    strategy_registry: StrategyRegistry | None = None,
    evaluator_registry: EvaluatorRegistry | None = None,
) -> tuple[StrategyRegistry, EvaluatorRegistry]:
    strategy_registry = strategy_registry or get_strategy_registry()
    evaluator_registry = evaluator_registry or get_evaluator_registry()

    existing_strategies = {provider.descriptor.id for provider in strategy_registry.matching("builtin.javascript", "analyze")}
    analyze_strategy = JavaScriptAnalyzeStrategy()
    reconstruct_strategy = JavaScriptReconstructStrategy()
    if analyze_strategy.descriptor.id not in existing_strategies:
        strategy_registry.register(analyze_strategy)
    existing_reconstruct = {provider.descriptor.id for provider in strategy_registry.matching("builtin.javascript", "reconstruct")}
    if reconstruct_strategy.descriptor.id not in existing_reconstruct:
        strategy_registry.register(reconstruct_strategy)

    existing_evaluators = {provider.id for provider in evaluator_registry.matching("builtin.javascript", "analyze")}
    evaluator = JavaScriptEvaluator()
    if evaluator.id not in existing_evaluators:
        evaluator_registry.register(evaluator)

    return strategy_registry, evaluator_registry


__all__ = ["register_builtin_capabilities", "register_builtin_orchestration"]
