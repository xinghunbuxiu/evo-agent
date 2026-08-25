"""
示例插件：JavaScript 扩展策略与评估器

企业后续可以按同样结构追加自己的 capability / strategy / evaluator。
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.orchestration import EvaluationResult, EvaluatorProvider, StrategyDescriptor, StrategyProvider, StrategySelection

PLUGIN_NAME = "example-js-extension"


class EnterpriseAnalyzeFastStrategy(StrategyProvider):
    @property
    def descriptor(self) -> StrategyDescriptor:
        return StrategyDescriptor(
            id="plugin.example.javascript.analyze.fast",
            name="Enterprise JS Fast Analyze",
            capability_id="builtin.javascript",
            task_type="analyze",
            description="针对企业快速分流场景的分析策略示例",
            tags=["javascript", "enterprise", "fast"],
        )

    def score(
        self,
        workspace,
        tenant_id: str,
        parameters: Dict[str, Any],
        signals: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> StrategySelection:
        preferred_tags = parameters.get("preferred_tags", [])
        score = 0.8
        reasons = ["enterprise fast analyze plugin"]
        if "enterprise" in preferred_tags or "fast" in preferred_tags:
            score += 7.0
            reasons.append("enterprise/fast tag matched")
        if "urgent" in str(signals):
            score += 2.0
            reasons.append("urgent signal matched")
        return StrategySelection(
            strategy_id=self.descriptor.id,
            capability_id=self.descriptor.capability_id,
            score=score,
            reasons=reasons,
        )


class EnterpriseEvaluator(EvaluatorProvider):
    id = "plugin.example.javascript.evaluator"
    name = "Enterprise Example Evaluator"

    def supports(self, capability_id: str, task_type: str) -> bool:
        return capability_id == "builtin.javascript" and task_type == "analyze"

    def evaluate(
        self,
        capability_id: str,
        task_type: str,
        result: Dict[str, Any],
        history: List[Dict[str, Any]],
        parameters: Dict[str, Any],
    ) -> EvaluationResult:
        confidence = float(result.get("confidence", 0.0))
        frameworks = result.get("frameworks", [])
        score = min(1.0, 0.3 + confidence + (0.1 if frameworks else 0.0))
        verdict = "pass" if score >= 0.85 else "review"
        return EvaluationResult(
            evaluator_id=self.id,
            score=score,
            verdict=verdict,
            reasons=["example plugin evaluator"],
            metrics={"frameworks": len(frameworks), "confidence": confidence},
        )


def register():
    return {
        "capabilities": [],
        "strategies": [EnterpriseAnalyzeFastStrategy()],
        "evaluators": [EnterpriseEvaluator()],
    }
