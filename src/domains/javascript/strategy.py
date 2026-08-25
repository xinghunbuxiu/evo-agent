"""
JavaScript 内置策略与评估器
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.orchestration import (
    EvaluationResult,
    EvaluatorProvider,
    StrategyDescriptor,
    StrategyProvider,
    StrategySelection,
)


class JavaScriptAnalyzeStrategy(StrategyProvider):
    @property
    def descriptor(self) -> StrategyDescriptor:
        return StrategyDescriptor(
            id="builtin.javascript.analyze.default",
            name="JS Analyze Default Strategy",
            capability_id="builtin.javascript",
            task_type="analyze",
            description="优先使用内置框架识别、指纹生成和经验记录链路",
            tags=["javascript", "analyze", "default"],
        )

    def score(
        self,
        workspace,
        tenant_id: str,
        parameters: Dict[str, Any],
        signals: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> StrategySelection:
        score = 1.0
        reasons = ["default analyze strategy"]
        if "javascript" in str(signals) or "javascript" in str(parameters.get("preferred_tags", [])):
            score += 1.5
            reasons.append("javascript signal/tag matched")
        if history:
            score += min(2.0, len(history) * 0.2)
            reasons.append(f"history available x{len(history)}")
        strategy_quality = _history_strategy_quality(history, self.descriptor.id)
        if strategy_quality is not None:
            score += strategy_quality * 2
            reasons.append(f"historical strategy quality={strategy_quality:.2f}")
        return StrategySelection(
            strategy_id=self.descriptor.id,
            capability_id=self.descriptor.capability_id,
            score=score,
            reasons=reasons,
        )


class JavaScriptReconstructStrategy(StrategyProvider):
    @property
    def descriptor(self) -> StrategyDescriptor:
        return StrategyDescriptor(
            id="builtin.javascript.reconstruct.scaffold",
            name="JS Reconstruct Scaffold Strategy",
            capability_id="builtin.javascript",
            task_type="reconstruct",
            description="优先生成可维护脚手架并记录重构经验",
            tags=["javascript", "reconstruct", "scaffold"],
        )

    def score(
        self,
        workspace,
        tenant_id: str,
        parameters: Dict[str, Any],
        signals: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> StrategySelection:
        score = 1.0
        reasons = ["default reconstruct strategy"]
        analysis_result = parameters.get("analysis_result", {})
        if analysis_result:
            score += 1.5
            reasons.append("analysis result available")
        if history:
            score += min(1.5, len(history) * 0.15)
            reasons.append(f"history available x{len(history)}")
        strategy_quality = _history_strategy_quality(history, self.descriptor.id)
        if strategy_quality is not None:
            score += strategy_quality * 2
            reasons.append(f"historical strategy quality={strategy_quality:.2f}")
        return StrategySelection(
            strategy_id=self.descriptor.id,
            capability_id=self.descriptor.capability_id,
            score=score,
            reasons=reasons,
        )


class JavaScriptEvaluator(EvaluatorProvider):
    id = "builtin.javascript.evaluator"
    name = "JavaScript Builtin Evaluator"

    def supports(self, capability_id: str, task_type: str) -> bool:
        return capability_id == "builtin.javascript" and task_type in {"analyze", "reconstruct"}

    def evaluate(
        self,
        capability_id: str,
        task_type: str,
        result: Dict[str, Any],
        history: List[Dict[str, Any]],
        parameters: Dict[str, Any],
    ) -> EvaluationResult:
        score = 0.5
        reasons: List[str] = []
        metrics: Dict[str, Any] = {}

        if task_type == "analyze":
            frameworks = result.get("frameworks", [])
            patterns = result.get("patterns", [])
            confidence = float(result.get("confidence", 0.0))
            score = min(1.0, 0.2 + confidence + (0.1 if frameworks else 0.0) + (0.05 * len(patterns)))
            metrics = {
                "framework_count": len(frameworks),
                "pattern_count": len(patterns),
                "confidence": confidence,
            }
            if frameworks:
                reasons.append("frameworks detected")
            if patterns:
                reasons.append("patterns detected")
            template = parameters.get("_skill_execution_template", {})
            if isinstance(template, dict):
                framework_hint = str(template.get("framework_hint") or "").strip().lower()
                if framework_hint and framework_hint in frameworks:
                    score = min(1.0, score + 0.05)
                    reasons.append("matched skill framework hint")
        elif task_type == "reconstruct":
            target_dir = result.get("target_dir")
            components = int(result.get("components", 0))
            score = min(1.0, 0.4 + (0.2 if target_dir else 0.0) + min(0.3, components * 0.1))
            metrics = {
                "has_target_dir": bool(target_dir),
                "components": components,
            }
            if target_dir:
                reasons.append("target dir generated")
            if components:
                reasons.append("components scaffolded")
            template = parameters.get("_skill_execution_template", {})
            acceptance = template.get("acceptance", {}) if isinstance(template, dict) and isinstance(template.get("acceptance"), dict) else {}
            components_min = int(acceptance.get("components_min", 0) or 0)
            if components_min and components >= components_min:
                score = min(1.0, score + 0.05)
                reasons.append("met skill component threshold")
            if acceptance.get("has_target_dir") and target_dir:
                score = min(1.0, score + 0.03)
                reasons.append("met skill target dir requirement")

        verdict = "pass" if score >= 0.75 else "review"
        template = parameters.get("_skill_execution_template", {})
        acceptance = template.get("acceptance", {}) if isinstance(template, dict) and isinstance(template.get("acceptance"), dict) else {}
        expected_verdict = str(acceptance.get("evaluation_verdict") or "").strip().lower()
        if expected_verdict == "pass" and score < 0.75:
            reasons.append("below skill acceptance baseline")
        if not reasons:
            reasons.append("baseline evaluation only")

        return EvaluationResult(
            evaluator_id=self.id,
            score=score,
            verdict=verdict,
            reasons=reasons,
            metrics=metrics,
        )


def _history_strategy_quality(history: List[Dict[str, Any]], strategy_id: str) -> float | None:
    scores: List[float] = []
    for item in history:
        metadata = item.get("metadata", {})
        strategy = metadata.get("strategy", {})
        evaluation = metadata.get("evaluation", {})
        if isinstance(strategy, dict) and strategy.get("strategy_id") == strategy_id:
            try:
                if isinstance(evaluation, dict) and "score" in evaluation:
                    scores.append(float(evaluation["score"]))
                elif "quality_score" in item:
                    scores.append(float(item["quality_score"]))
            except (TypeError, ValueError):
                continue
    if not scores:
        return None
    return sum(scores) / len(scores)


__all__ = [
    "JavaScriptAnalyzeStrategy",
    "JavaScriptReconstructStrategy",
    "JavaScriptEvaluator",
]
