"""
Evo Core - 最小自主决策引擎

当前目标：
1. 不再由调用方手工指定 provider。
2. 基于任务类型、标签偏好、显式输入与历史经验自动选能力。
3. 把决策原因和候选评分带回结果，成为后续成长层的输入。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .capabilities import (
    CapabilityProvider,
    CapabilityRegistry,
    TaskContext,
    TaskResult,
    get_capability_registry,
)
from .learning import Experience, ExperienceStore
from .learning import normalize_task_type
from .skill_system import SkillRegistry
from .orchestration import (
    EvaluationResult,
    EvaluatorRegistry,
    StrategyRegistry,
    StrategySelection,
    get_evaluator_registry,
    get_strategy_registry,
)
from .plugins import PluginLoader
from .tenant import TenantManager


@dataclass
class CandidateScore:
    capability_id: str
    score: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class DecisionRecord:
    task_type: str
    selected_capability_id: str
    scores: List[CandidateScore]
    strategy: Optional[Dict[str, Any]] = None
    preferred_tags: List[str] = field(default_factory=list)
    domain_hint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_type": self.task_type,
            "selected_capability_id": self.selected_capability_id,
            "strategy": self.strategy,
            "preferred_tags": self.preferred_tags,
            "domain_hint": self.domain_hint,
            "scores": [
                {
                    "capability_id": item.capability_id,
                    "score": item.score,
                    "reasons": item.reasons,
                }
                for item in self.scores
            ],
        }


class DecisionEngine:
    """最小可用自主决策引擎。"""

    def __init__(self, workspace: Path, registry: Optional[CapabilityRegistry] = None):
        self.workspace = workspace
        self.registry = registry or get_capability_registry()
        self.strategy_registry: StrategyRegistry = get_strategy_registry()
        self.evaluator_registry: EvaluatorRegistry = get_evaluator_registry()
        self.tenant_manager = TenantManager(workspace)

    def decide(
        self,
        task_type: str,
        workspace: Optional[Path] = None,
        tenant_id: str = "default",
        capability_id: Optional[str] = None,
        preferred_tags: Optional[List[str]] = None,
        domain_hint: Optional[str] = None,
        signals: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> DecisionRecord:
        preferred_tags = preferred_tags or []
        signals = signals or {}
        parameters = parameters or {}
        workspace = workspace or self.workspace

        if capability_id:
            provider = self.registry.get(capability_id)
            if not self._is_plugin_allowed(
                tenant_id,
                PluginLoader.get_capability_plugin(provider.descriptor.id),
            ):
                raise ValueError(
                    f"Capability {provider.descriptor.id} is disabled for tenant {tenant_id}"
                )
            strategy = self._select_strategy(
                workspace=workspace,
                capability_id=provider.descriptor.id,
                task_type=task_type,
                tenant_id=tenant_id,
                preferred_tags=preferred_tags,
                signals=signals,
                parameters=parameters,
            )
            return DecisionRecord(
                task_type=task_type,
                selected_capability_id=provider.descriptor.id,
                strategy=strategy.to_dict() if strategy else None,
                preferred_tags=preferred_tags,
                domain_hint=domain_hint,
                scores=[
                    CandidateScore(
                        capability_id=provider.descriptor.id,
                        score=999.0,
                        reasons=["explicit capability selected"],
                    )
                ],
            )

        candidates = [
            provider
            for provider in self.registry.matching_providers(task_type)
            if self._is_plugin_allowed(
                tenant_id,
                PluginLoader.get_capability_plugin(provider.descriptor.id),
            )
        ]
        if not candidates:
            raise ValueError(f"No capability candidates for task: {task_type}")

        experiences = self._load_relevant_experiences(
            workspace,
            tenant_id,
            domain_hint,
            preferred_tags,
            task_type=task_type,
        )
        scored = [
            self._score_candidate(
                provider=provider,
                task_type=task_type,
                preferred_tags=preferred_tags,
                signals=signals,
                experiences=experiences,
                parameters={
                    **parameters,
                    "tenant_id": tenant_id,
                },
            )
            for provider in candidates
        ]
        scored.sort(key=lambda item: item.score, reverse=True)

        selected_capability_id = scored[0].capability_id
        strategy = self._select_strategy(
            workspace=workspace,
            capability_id=selected_capability_id,
            task_type=task_type,
            tenant_id=tenant_id,
            preferred_tags=preferred_tags,
            signals=signals,
            parameters=parameters,
        )

        return DecisionRecord(
            task_type=task_type,
            selected_capability_id=selected_capability_id,
            strategy=strategy.to_dict() if strategy else None,
            preferred_tags=preferred_tags,
            domain_hint=domain_hint,
            scores=scored,
        )

    def execute(
        self,
        task_type: str,
        workspace: Optional[Path] = None,
        tenant_id: str = "default",
        capability_id: Optional[str] = None,
        input_path: Optional[Path] = None,
        source_dir: Optional[Path] = None,
        parameters: Optional[Dict[str, Any]] = None,
        signals: Optional[Dict[str, Any]] = None,
    ) -> TaskResult:
        workspace = workspace or self.workspace
        parameters = parameters or {}
        signals = signals or {}
        preferred_tags = list(parameters.get("preferred_tags", []) or [])
        domain_hint = parameters.get("domain_hint")

        decision = self.decide(
            task_type=task_type,
            workspace=workspace,
            tenant_id=tenant_id,
            capability_id=capability_id,
            preferred_tags=preferred_tags,
            domain_hint=domain_hint,
            signals=signals,
            parameters=parameters,
        )
        provider = self.registry.get(decision.selected_capability_id)
        history = self._build_history(
            workspace=workspace,
            tenant_id=tenant_id,
            preferred_tags=preferred_tags,
            domain_hint=domain_hint,
        )

        execution_parameters = {
            **parameters,
            "_decision": decision.to_dict(),
            "_strategy": decision.strategy or {},
            "_matched_verified_skills": self._runtime_verified_skill_payload(
                workspace=workspace,
                tenant_id=tenant_id,
                capability_id=decision.selected_capability_id,
                task_type=task_type,
                preferred_tags=preferred_tags,
                signals=signals,
                parameters=parameters,
            ),
        }
        execution_parameters["_skill_execution_template"] = self._build_skill_execution_template(
            execution_parameters.get("_matched_verified_skills", [])
        )

        context = TaskContext(
            workspace=workspace,
            tenant_id=tenant_id,
            task_type=task_type,
            input_path=input_path,
            source_dir=source_dir,
            parameters=execution_parameters,
            signals=signals,
            history=history,
        )
        result = provider.execute(context)
        evaluation = self._evaluate_result(
            tenant_id=tenant_id,
            capability_id=decision.selected_capability_id,
            task_type=task_type,
            result=result.to_dict(),
            history=history,
            parameters=execution_parameters,
        )
        result.feedback = {
            **result.feedback,
            "decision": decision.to_dict(),
            "matched_verified_skills": execution_parameters.get("_matched_verified_skills", []),
            "skill_execution_template": execution_parameters.get("_skill_execution_template", {}),
            "history_size": len(history),
            "evaluation": evaluation.to_dict() if evaluation else None,
        }
        self._record_execution_experience(
            workspace=workspace,
            tenant_id=tenant_id,
            task_type=task_type,
            input_path=input_path,
            source_dir=source_dir,
            preferred_tags=preferred_tags,
            domain_hint=domain_hint,
            decision=decision,
            result=result,
            evaluation=evaluation,
            parameters=parameters,
            signals=signals,
        )
        return result

    def _select_strategy(
        self,
        workspace: Path,
        capability_id: str,
        task_type: str,
        tenant_id: str,
        preferred_tags: List[str],
        signals: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Optional[StrategySelection]:
        history = self._build_history(
            workspace=workspace,
            tenant_id=tenant_id,
            preferred_tags=preferred_tags,
            domain_hint=parameters.get("domain_hint"),
        )
        candidates = [
            provider
            for provider in self.strategy_registry.matching(capability_id, task_type)
            if self._is_plugin_allowed(
                tenant_id,
                PluginLoader.get_strategy_plugin(provider.descriptor.id),
            )
        ]
        if not candidates:
            return None
        overrides = self.tenant_manager.get_strategy_overrides(tenant_id)
        scored = []
        current_signature = self._build_runtime_signature(
            task_type=task_type,
            preferred_tags=preferred_tags,
            signals=signals,
            parameters=parameters,
        )
        for provider in candidates:
            selection = provider.score(
                workspace=workspace,
                tenant_id=tenant_id,
                parameters=parameters,
                signals=signals,
                history=history,
            )
            override = overrides.get(selection.strategy_id, {})
            if isinstance(override, dict):
                selection.runtime_adjustments = {
                    "override_active": True,
                    "weight_delta": override.get("weight_delta", 0.0),
                    "preferred": bool(override.get("preferred")),
                    "blocked": bool(override.get("blocked")),
                    "source": override.get("source"),
                    "updated_at": override.get("updated_at"),
                    "expires_at": override.get("expires_at"),
                }
                if bool(override.get("blocked")):
                    selection.score = -999.0
                    selection.reasons.append("tenant override blocked strategy")
                else:
                    weight_delta = 0.0
                    try:
                        weight_delta = float(override.get("weight_delta", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        weight_delta = 0.0
                    if weight_delta:
                        selection.score += weight_delta
                        selection.reasons.append(f"tenant override weight {weight_delta:+.2f}")
                    if bool(override.get("preferred")):
                        selection.score += 3.0
                        selection.reasons.append("tenant override preferred strategy")
            domain_hint = parameters.get("domain_hint")
            growth_bias = self._growth_event_bias(
                workspace,
                tenant_id,
                selection.strategy_id,
                task_type=task_type,
                domain_hint=domain_hint,
                current_signature={
                    **current_signature,
                    "strategy_id": selection.strategy_id,
                },
            )
            if growth_bias != 0:
                selection.score += growth_bias
                selection.reasons.append(f"growth memory bias {growth_bias:+.2f}")
                selection.runtime_adjustments = {
                    **selection.runtime_adjustments,
                    "growth_memory_bias": growth_bias,
                }
            signature_bias = self._strategy_signature_bias(
                workspace=workspace,
                tenant_id=tenant_id,
                strategy_id=selection.strategy_id,
                task_type=task_type,
                domain_hint=domain_hint,
                current_signature={
                    **current_signature,
                    "strategy_id": selection.strategy_id,
                },
            )
            if signature_bias != 0:
                selection.score += signature_bias
                selection.reasons.append(f"signature memory bias {signature_bias:+.2f}")
                selection.runtime_adjustments = {
                    **selection.runtime_adjustments,
                    "signature_memory_bias": signature_bias,
                }
            platform_shared = self._platform_shared_bias(
                workspace=workspace,
                strategy_id=selection.strategy_id,
                task_type=task_type,
                domain_hint=domain_hint,
            )
            platform_shared_bias = float(platform_shared.get("bias", 0.0) or 0.0)
            if platform_shared_bias != 0:
                selection.score += platform_shared_bias
                selection.reasons.append(f"platform shared bias {platform_shared_bias:+.2f}")
                selection.runtime_adjustments = {
                    **selection.runtime_adjustments,
                    "platform_shared_bias": platform_shared_bias,
                    "platform_shared_hits": platform_shared.get("hits", 0),
                    "platform_shared_titles": platform_shared.get("titles", []),
                }
            verified_strategy_bias = self._verified_skill_strategy_bias(
                workspace=workspace,
                tenant_id=tenant_id,
                strategy_id=selection.strategy_id,
                task_type=task_type,
                preferred_tags=preferred_tags,
                signals=signals,
                parameters=parameters,
            )
            if verified_strategy_bias["bias"] > 0:
                selection.score += verified_strategy_bias["bias"]
                selection.reasons.append(
                    f"verified skill strategy bias +{verified_strategy_bias['bias']:.2f}: {verified_strategy_bias['skill_ids']}"
                )
                selection.runtime_adjustments = {
                    **selection.runtime_adjustments,
                    "verified_skill_bias": verified_strategy_bias["bias"],
                    "verified_skill_ids": verified_strategy_bias["skill_ids"],
                }
            scored.append(selection)
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[0]

    def _evaluate_result(
        self,
        tenant_id: str,
        capability_id: str,
        task_type: str,
        result: Dict[str, Any],
        history: List[Dict[str, Any]],
        parameters: Dict[str, Any],
    ) -> Optional[EvaluationResult]:
        evaluators = [
            evaluator
            for evaluator in self.evaluator_registry.matching(capability_id, task_type)
            if self._is_plugin_allowed(
                tenant_id,
                PluginLoader.get_evaluator_plugin(evaluator.id),
            )
        ]
        if not evaluators:
            return None
        evaluations = [
            evaluator.evaluate(
                capability_id=capability_id,
                task_type=task_type,
                result=result,
                history=history,
                parameters=parameters,
            )
            for evaluator in evaluators
        ]
        evaluations.sort(key=lambda item: item.score, reverse=True)
        return evaluations[0]

    def _record_execution_experience(
        self,
        workspace: Path,
        tenant_id: str,
        task_type: str,
        input_path: Optional[Path],
        source_dir: Optional[Path],
        preferred_tags: List[str],
        domain_hint: Optional[str],
        decision: DecisionRecord,
        result: TaskResult,
        evaluation: Optional[EvaluationResult],
        parameters: Dict[str, Any],
        signals: Dict[str, Any],
    ) -> None:
        domain = domain_hint or (preferred_tags[0] if preferred_tags else "javascript")
        summary_source = input_path or source_dir or workspace
        quality_score = evaluation.score if evaluation else result.confidence
        evaluation_dict = evaluation.to_dict() if evaluation else {}
        evaluation_metrics = evaluation_dict.get("metrics", {}) if isinstance(evaluation_dict, dict) else {}
        issue_category = (
            parameters.get("issue_category")
            or self._infer_issue_category(
                task_type=task_type,
                evaluation=evaluation_dict,
                metrics=evaluation_metrics,
            )
        )
        learning_signature = self._build_runtime_signature(
            task_type=task_type,
            preferred_tags=preferred_tags,
            signals={
                **signals,
                **evaluation_metrics,
                "confidence": evaluation_metrics.get("confidence", quality_score),
            },
            parameters={
                **parameters,
                "issue_category": issue_category,
            },
            capability_id=decision.selected_capability_id,
            strategy_id=(decision.strategy or {}).get("strategy_id"),
        )
        metadata = {
            "capability_id": decision.selected_capability_id,
            "strategy": decision.strategy or {},
            "evaluation": evaluation_dict if evaluation else None,
            "feedback": result.feedback,
            "result_summary": result.summary,
            "learning_signature": learning_signature,
        }
        exp = Experience(
            id=self._make_experience_id(
                tenant_id=tenant_id,
                domain=domain,
                task_type=task_type,
                summary_source=str(summary_source),
                strategy_id=(decision.strategy or {}).get("strategy_id", "none"),
            ),
            domain=domain,
            task_type=task_type,
            input_summary=str(summary_source),
            output_summary=result.summary or f"{task_type}:{decision.selected_capability_id}",
            quality_score=quality_score,
            metadata=metadata,
        )
        ExperienceStore(workspace, tenant_id).save(exp)

    def _make_experience_id(
        self,
        tenant_id: str,
        domain: str,
        task_type: str,
        summary_source: str,
        strategy_id: str,
    ) -> str:
        raw = f"{tenant_id}|{domain}|{normalize_task_type(task_type)}|{summary_source}|{strategy_id}"
        return f"orch_{hashlib.sha1(raw.encode()).hexdigest()[:12]}"

    def _load_relevant_experiences(
        self,
        workspace: Path,
        tenant_id: str,
        domain_hint: Optional[str],
        preferred_tags: List[str],
        task_type: Optional[str] = None,
    ) -> List[Experience]:
        domains: List[str] = []
        if domain_hint:
            domains.append(domain_hint)

        for tag in preferred_tags:
            if tag not in domains:
                domains.append(tag)

        if not domains:
            domains.append("javascript")

        experiences: List[Experience] = []
        store = ExperienceStore(workspace, tenant_id)
        seen_ids: set[str] = set()
        for domain in domains:
            if task_type:
                candidates = [
                    *store.load_by_task(domain, task_type=task_type, limit=20),
                    *store.load_by_task(domain, task_type="role_reflection", limit=8),
                ]
            else:
                candidates = store.load_by_domain(domain, limit=20)
            for exp in candidates:
                if exp.id in seen_ids:
                    continue
                seen_ids.add(exp.id)
                experiences.append(exp)
        return experiences

    def _build_history(
        self,
        workspace: Path,
        tenant_id: str,
        preferred_tags: List[str],
        domain_hint: Optional[str],
    ) -> List[Dict[str, Any]]:
        experiences = self._load_relevant_experiences(workspace, tenant_id, domain_hint, preferred_tags)
        return [exp.to_dict() for exp in experiences[:10]]

    def _score_candidate(
        self,
        provider: CapabilityProvider,
        task_type: str,
        preferred_tags: List[str],
        signals: Dict[str, Any],
        experiences: List[Experience],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> CandidateScore:
        score = 1.0
        reasons = ["base task support"]
        parameters = parameters or {}
        current_signature = self._build_runtime_signature(
            task_type=task_type,
            preferred_tags=preferred_tags,
            signals=signals,
            parameters=parameters,
            capability_id=provider.descriptor.id,
        )

        descriptor = provider.descriptor
        if task_type in descriptor.supported_tasks:
            score += 1.0
            reasons.append("supports requested task")

        matched_tags = [tag for tag in preferred_tags if tag in descriptor.tags]
        if matched_tags:
            score += 2.0 * len(matched_tags)
            reasons.append(f"preferred tags matched: {matched_tags}")

        signal_tags = [tag for tag in descriptor.tags if tag in str(signals)]
        if signal_tags:
            score += 1.5
            reasons.append(f"signal match: {signal_tags}")

        recent_success = [
            exp for exp in experiences
            if normalize_task_type(exp.task_type) == normalize_task_type(task_type)
            and exp.quality_score >= 0.7
            and self._experience_matches_provider(exp, descriptor.tags)
        ]
        if recent_success:
            weighted_scores = [self._experience_effective_score(exp) for exp in recent_success]
            avg_quality = sum(weighted_scores) / len(weighted_scores)
            score += avg_quality * 3
            reasons.append(f"historical success x{len(recent_success)} avg={avg_quality:.2f}")
            signature_bias = self._signature_experience_bias(
                experiences=recent_success,
                current_signature=current_signature,
            )
            if signature_bias > 0:
                score += signature_bias
                reasons.append(f"signature memory bias +{signature_bias:.2f}")

        verified_skill_bias = self._verified_skill_bias(
            workspace=self.workspace,
            tenant_id=parameters.get("tenant_id", "default"),
            provider=provider,
            task_type=task_type,
            preferred_tags=preferred_tags,
            signals=signals,
            parameters=parameters,
        )
        if verified_skill_bias["bias"] > 0:
            score += verified_skill_bias["bias"]
            reasons.append(
                f"verified skill bias +{verified_skill_bias['bias']:.2f}: {verified_skill_bias['skill_ids']}"
            )

        role_reflection_bias = self._role_reflection_bias(
            provider=provider,
            experiences=experiences,
            preferred_tags=preferred_tags,
            task_type=task_type,
        )
        if role_reflection_bias["bias"] > 0:
            score += role_reflection_bias["bias"]
            reasons.append(
                f"role reflection bias +{role_reflection_bias['bias']:.2f}: {role_reflection_bias['sources']}"
            )

        return CandidateScore(
            capability_id=descriptor.id,
            score=score,
            reasons=reasons,
        )

    def _role_reflection_bias(
        self,
        *,
        provider: CapabilityProvider,
        experiences: List[Experience],
        preferred_tags: List[str],
        task_type: str,
    ) -> Dict[str, Any]:
        descriptor = provider.descriptor
        matched: List[str] = []
        best_bias = 0.0
        normalized_task_type = normalize_task_type(task_type)
        for exp in experiences:
            if normalize_task_type(exp.task_type) != "role_reflection":
                continue
            metadata = exp.metadata if isinstance(exp.metadata, dict) else {}
            payload = metadata.get("professional_experience", {}) if isinstance(metadata.get("professional_experience"), dict) else {}
            card = payload.get("card", {}) if isinstance(payload.get("card"), dict) else {}
            role = str(payload.get("primary_role") or "").strip()
            role_tags = {exp.domain, role, str(card.get("job_id") or "").strip()}
            role_tags.update(tag for tag in preferred_tags if tag)
            if not any(tag and tag in descriptor.tags for tag in role_tags):
                continue
            stage = str(card.get("stage") or "").strip()
            base = min(max(float(exp.quality_score or 0.0), 0.0), 1.0)
            stage_bonus = 0.18 if stage in {"stable", "stabilizing"} else 0.1 if stage == "delivering" else 0.04
            task_bonus = 0.08 if normalized_task_type in descriptor.supported_tasks else 0.0
            current_bias = min(0.75, round(base * 0.42 + stage_bonus + task_bonus, 3))
            if current_bias <= 0:
                continue
            source_name = str(payload.get("member_name") or payload.get("member_id") or role or exp.id).strip()
            matched.append(source_name)
            best_bias = max(best_bias, current_bias)
        return {
            "bias": round(best_bias, 3),
            "sources": matched[:2],
        }

    def _verified_skill_bias(
        self,
        *,
        workspace: Path,
        tenant_id: str,
        provider: CapabilityProvider,
        task_type: str,
        preferred_tags: List[str],
        signals: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        descriptor = provider.descriptor
        matched_ids = [
            skill["id"]
            for skill in self._runtime_verified_skill_payload(
                workspace=workspace,
                tenant_id=tenant_id,
                capability_id=descriptor.capability_type,
                task_type=task_type,
                preferred_tags=preferred_tags,
                signals=signals,
                parameters=parameters,
                match_by="capability_type",
            )
        ]

        if not matched_ids:
            return {"bias": 0.0, "skill_ids": []}

        bias = min(3.2, 1.6 + 0.8 * len(matched_ids))
        return {
            "bias": round(bias, 3),
            "skill_ids": matched_ids[:3],
        }

    def _verified_skill_strategy_bias(
        self,
        *,
        workspace: Path,
        tenant_id: str,
        strategy_id: str,
        task_type: str,
        preferred_tags: List[str],
        signals: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        matched_skills = self._collect_verified_skills(
            workspace=workspace,
            tenant_id=tenant_id,
            task_type=task_type,
            preferred_tags=preferred_tags,
            signals=signals,
            parameters=parameters,
        )
        matched_ids: List[str] = []
        strategy_text = strategy_id.lower()
        for skill in matched_skills:
            if task_type == "reconstruct" and "reconstruct" in strategy_text:
                matched_ids.append(skill.id)
                continue
            if task_type == "analyze" and "analyze" in strategy_text:
                matched_ids.append(skill.id)

        if not matched_ids:
            return {"bias": 0.0, "skill_ids": []}

        bias = 1.35 if task_type == "reconstruct" else 0.95
        return {
            "bias": round(bias, 3),
            "skill_ids": matched_ids[:3],
        }

    def _runtime_verified_skill_payload(
        self,
        *,
        workspace: Path,
        tenant_id: str,
        capability_id: str,
        task_type: str,
        preferred_tags: List[str],
        signals: Dict[str, Any],
        parameters: Dict[str, Any],
        match_by: str = "provider_id",
    ) -> List[Dict[str, Any]]:
        matches = self._collect_verified_skills(
            workspace=workspace,
            tenant_id=tenant_id,
            task_type=task_type,
            preferred_tags=preferred_tags,
            signals=signals,
            parameters=parameters,
        )
        payload: List[Dict[str, Any]] = []
        for skill in matches:
            parameters_map = skill.parameters if isinstance(skill.parameters, dict) else {}
            if match_by == "provider_id":
                if not self._skill_matches_provider_id(skill=skill, capability_id=capability_id):
                    continue
            elif match_by == "capability_type":
                if getattr(skill, "capability_type", None) != capability_id:
                    continue
            payload.append({
                "id": skill.id,
                "name": skill.name,
                "domain": skill.domain,
                "capability_type": skill.capability_type,
                "trust_level": skill.trust_level.value,
                "success_rate": skill.success_rate,
                "usage_count": skill.usage_count,
                "framework_hint": parameters_map.get("framework_hint"),
                "accepted_tasks": parameters_map.get("accepted_tasks", []),
                "mission_kind": parameters_map.get("mission_kind"),
                "acceptance": parameters_map.get("acceptance", {}),
            })
        return payload[:3]

    def _collect_verified_skills(
        self,
        *,
        workspace: Path,
        tenant_id: str,
        task_type: str,
        preferred_tags: List[str],
        signals: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> List[Any]:
        registry = SkillRegistry(workspace, tenant_id)
        domain = parameters.get("domain_hint") or (preferred_tags[0] if preferred_tags else "javascript")
        listed = registry.list_skills(domain=domain)
        verified_skills = listed.get("local_verified", []) if isinstance(listed, dict) else []
        if not isinstance(verified_skills, list):
            verified_skills = []

        framework_hint = self._skill_framework_hint(signals=signals, parameters=parameters)
        matched: List[Any] = []
        for skill in verified_skills:
            accepted_tasks = skill.parameters.get("accepted_tasks", []) if isinstance(skill.parameters, dict) else []
            if accepted_tasks and task_type not in accepted_tasks:
                continue
            skill_framework = (
                skill.parameters.get("framework_hint")
                if isinstance(skill.parameters, dict)
                else None
            )
            if framework_hint and skill_framework and framework_hint != skill_framework:
                continue
            matched.append(skill)
        return matched

    def _skill_matches_provider_id(self, *, skill: Any, capability_id: str) -> bool:
        if getattr(skill, "capability_type", None) == capability_id:
            return True
        try:
            descriptor = self.registry.get(capability_id).descriptor
        except Exception:
            return False
        return getattr(skill, "capability_type", None) == descriptor.capability_type

    def _build_skill_execution_template(self, matched_skills: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not matched_skills:
            return {}
        primary = matched_skills[0] if isinstance(matched_skills[0], dict) else {}
        acceptance = primary.get("acceptance", {}) if isinstance(primary.get("acceptance"), dict) else {}
        framework_hint = primary.get("framework_hint")
        return {
            "skill_id": primary.get("id"),
            "skill_name": primary.get("name"),
            "framework_hint": framework_hint,
            "mission_kind": primary.get("mission_kind"),
            "accepted_tasks": primary.get("accepted_tasks", []),
            "acceptance": {
                "evaluation_verdict": acceptance.get("evaluation_verdict"),
                "has_target_dir": acceptance.get("has_target_dir"),
                "components_min": acceptance.get("components_min"),
            },
            "scaffold_profile": {
                "target_subdir": framework_hint or "default",
                "page_shell_sections": ["route-meta", "asset-hints", "source-reference", "next-actions"],
                "component_stub_style": "traceable",
                "route_manifest_mode": "rich",
                "naming_convention": "PascalCase",
            },
        }

    def _skill_framework_hint(
        self,
        *,
        signals: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Optional[str]:
        direct = str(parameters.get("framework_hint") or signals.get("framework_hint") or "").strip().lower()
        if direct:
            return direct
        summary_parts = [
            str(parameters.get("input_path") or ""),
            str(parameters.get("source_dir") or ""),
            str(signals.get("analysis_summary") or ""),
            str(signals.get("reconstruct_summary") or ""),
        ]
        summary = " ".join(summary_parts).lower()
        if "react" in summary:
            return "react"
        if "vue" in summary:
            return "vue"
        return None

    def _experience_matches_provider(self, exp: Experience, provider_tags: List[str]) -> bool:
        metadata_text = str(exp.metadata)
        if exp.domain in provider_tags:
            return True
        return any(tag in metadata_text for tag in provider_tags)

    def _build_runtime_signature(
        self,
        *,
        task_type: str,
        preferred_tags: List[str],
        signals: Dict[str, Any],
        parameters: Dict[str, Any],
        capability_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        domain_hint = parameters.get("domain_hint") or (preferred_tags[0] if preferred_tags else None)
        previous_metrics = (
            signals.get("previous_metrics", {})
            if isinstance(signals.get("previous_metrics"), dict)
            else {}
        )
        components_value = signals.get("components", previous_metrics.get("components"))
        has_target_dir = (
            signals.get("has_target_dir")
            if "has_target_dir" in signals
            else previous_metrics.get("has_target_dir")
        )
        framework_count = self._safe_int(
            signals.get("framework_count", previous_metrics.get("framework_count"))
        )
        if framework_count == 0 and domain_hint == "javascript":
            framework_count = 1
        pattern_count = self._safe_int(
            signals.get("pattern_count", previous_metrics.get("pattern_count"))
        )
        confidence_hint = self._safe_float(
            signals.get(
                "confidence",
                previous_metrics.get("confidence", signals.get("previous_evaluation_score")),
            )
        )
        issue_category = (
            parameters.get("issue_category")
            or signals.get("issue_category")
            or signals.get("previous_issue_category")
        )
        return {
            "issue_category": issue_category,
            "strategy_id": strategy_id,
            "capability_id": capability_id,
            "task_type": task_type,
            "components_bucket": self._components_bucket(components_value),
            "has_target_dir": bool(has_target_dir) if has_target_dir is not None else None,
            "framework_count": framework_count,
            "pattern_count": pattern_count,
            "confidence_band": self._confidence_band(confidence_hint),
        }

    def _signature_similarity(self, current: Dict[str, Any], historical: Dict[str, Any]) -> float:
        if not isinstance(current, dict) or not isinstance(historical, dict):
            return 0.0
        weighted_keys = [
            ("issue_category", 0.32),
            ("strategy_id", 0.24),
            ("capability_id", 0.12),
            ("task_type", 0.1),
            ("components_bucket", 0.1),
            ("confidence_band", 0.06),
            ("has_target_dir", 0.03),
            ("framework_count", 0.02),
            ("pattern_count", 0.01),
        ]
        score = 0.0
        for key, weight in weighted_keys:
            current_value = current.get(key)
            historical_value = historical.get(key)
            if current_value is None or historical_value is None:
                continue
            if current_value == historical_value:
                score += weight
        return min(score, 1.0)

    def _signature_experience_bias(
        self,
        *,
        experiences: List[Experience],
        current_signature: Dict[str, Any],
    ) -> float:
        best = 0.0
        for exp in experiences:
            signature = self._extract_experience_signature(exp)
            if not isinstance(signature, dict):
                continue
            similarity = self._signature_similarity(current_signature, signature)
            quality = self._experience_effective_score(exp)
            best = max(best, similarity * min(max(quality, 0.0), 1.0))
        return round(min(best * 1.2, 1.2), 3)

    def _strategy_signature_bias(
        self,
        *,
        workspace: Path,
        tenant_id: str,
        strategy_id: str,
        task_type: str,
        domain_hint: Optional[str],
        current_signature: Dict[str, Any],
    ) -> float:
        experiences = self._load_relevant_experiences(
            workspace=workspace,
            tenant_id=tenant_id,
            domain_hint=domain_hint,
            preferred_tags=[domain_hint] if domain_hint else [],
            task_type=task_type,
        )
        matched: List[Experience] = []
        for exp in experiences:
            metadata = exp.metadata if isinstance(exp.metadata, dict) else {}
            strategy = metadata.get("strategy", {}) if isinstance(metadata.get("strategy"), dict) else {}
            if strategy.get("strategy_id") != strategy_id:
                continue
            matched.append(exp)
        if not matched:
            return 0.0
        return round(min(self._signature_experience_bias(experiences=matched, current_signature=current_signature), 1.0), 3)

    def _experience_effective_score(self, exp: Experience) -> float:
        evaluation = exp.metadata.get("evaluation")
        if isinstance(evaluation, dict):
            try:
                return float(evaluation.get("score", exp.quality_score))
            except (TypeError, ValueError):
                return exp.quality_score
        return exp.quality_score

    def _growth_event_bias(
        self,
        workspace: Path,
        tenant_id: str,
        strategy_id: str,
        task_type: Optional[str] = None,
        domain_hint: Optional[str] = None,
        current_signature: Optional[Dict[str, Any]] = None,
    ) -> float:
        events = ExperienceStore(workspace, tenant_id).load_by_task("evolution", "growth_event", limit=20)
        bias = 0.0
        matched = 0
        for exp in events:
            metadata = exp.metadata if isinstance(exp.metadata, dict) else {}
            growth_event = metadata.get("growth_event", {})
            if not isinstance(growth_event, dict):
                continue
            if growth_event.get("strategy_id") != strategy_id:
                continue
            event_task_type = growth_event.get("task_type")
            event_domain = growth_event.get("domain")
            decay = self._growth_event_decay(exp.created_at)
            weight = decay
            if task_type and event_task_type == task_type:
                weight += 0.35
            if domain_hint and event_domain == domain_hint:
                weight += 0.25
            signature = growth_event.get("signature")
            if current_signature and isinstance(signature, dict):
                weight += self._signature_similarity(current_signature, signature) * 0.8
            matched += 1
            event_type = str(growth_event.get("event_type", ""))
            if event_type in {"manual_accept", "auto_accept"}:
                bias += 0.8 * weight
            elif event_type == "manual_observe":
                bias += 0.25 * weight
            elif event_type in {"manual_reject", "manual_rollback", "auto_rollback"}:
                bias -= 0.7 * weight
        if matched == 0:
            return 0.0
        return max(-1.5, min(1.5, bias))

    def _growth_event_decay(self, created_at: str | None) -> float:
        if not created_at:
            return 0.35
        try:
            age_days = max(0.0, (datetime.now() - datetime.fromisoformat(created_at)).total_seconds() / 86400.0)
        except ValueError:
            return 0.35
        if age_days <= 3:
            return 1.0
        if age_days <= 7:
            return 0.8
        if age_days <= 14:
            return 0.55
        if age_days <= 30:
            return 0.35
        return 0.15

    def _extract_experience_signature(self, exp: Experience) -> Optional[Dict[str, Any]]:
        metadata = exp.metadata if isinstance(exp.metadata, dict) else {}
        signature = metadata.get("learning_signature")
        if isinstance(signature, dict) and signature:
            return signature
        evaluation = metadata.get("evaluation", {}) if isinstance(metadata.get("evaluation"), dict) else {}
        metrics = evaluation.get("metrics", {}) if isinstance(evaluation.get("metrics"), dict) else {}
        strategy = metadata.get("strategy", {}) if isinstance(metadata.get("strategy"), dict) else {}
        fallback = self._build_runtime_signature(
            task_type=normalize_task_type(exp.task_type),
            preferred_tags=[exp.domain] if exp.domain else [],
            signals={
                **metrics,
                "confidence": metrics.get("confidence", self._experience_effective_score(exp)),
            },
            parameters={
                "domain_hint": exp.domain,
                "issue_category": self._infer_issue_category(
                    task_type=exp.task_type,
                    evaluation=evaluation,
                    metrics=metrics,
                ),
            },
            capability_id=metadata.get("capability_id"),
            strategy_id=strategy.get("strategy_id"),
        )
        return fallback if any(value is not None for value in fallback.values()) else None

    def _infer_issue_category(
        self,
        *,
        task_type: str,
        evaluation: Dict[str, Any],
        metrics: Dict[str, Any],
    ) -> Optional[str]:
        verdict = str(evaluation.get("verdict") or "").lower()
        if normalize_task_type(task_type) == "reconstruct":
            components = self._safe_int(metrics.get("components"))
            if verdict == "review" and components == 0:
                return "strategy_gap"
        if verdict == "failed":
            return "execution_error"
        return None

    def _components_bucket(self, value: Any) -> str:
        if value is None:
            return "unknown"
        components = self._safe_int(value)
        if components <= 0:
            return "zero"
        if components <= 3:
            return "few"
        return "many"

    def _confidence_band(self, value: Any) -> str:
        confidence = self._safe_float(value)
        if confidence <= 0:
            return "unknown"
        if confidence < 0.45:
            return "low"
        if confidence < 0.75:
            return "medium"
        return "high"

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value if value is not None else default)
        except (TypeError, ValueError):
            return default

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value if value is not None else default)
        except (TypeError, ValueError):
            return default

    def _platform_shared_bias(
        self,
        workspace: Path,
        strategy_id: str,
        task_type: Optional[str] = None,
        domain_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        promotions = self._load_platform_strategy_promotions(workspace)
        bias = 0.0
        hits = 0
        titles: List[str] = []

        for payload in promotions:
            if str(payload.get("strategy_id", "")) != strategy_id:
                continue

            review_entry = payload.get("review_entry", {})
            candidate = review_entry.get("upgrade_candidate", {}) if isinstance(review_entry, dict) else {}
            decision = str(candidate.get("decision", ""))
            if decision not in {"accept", "auto_accept"}:
                continue

            weight = self._growth_event_decay(str(payload.get("promoted_at") or ""))
            promoted_task_type = self._platform_shared_task_type(review_entry)
            promoted_domain = self._platform_shared_domain(strategy_id)
            if task_type and promoted_task_type == task_type:
                weight += 0.25
            if domain_hint and promoted_domain == domain_hint:
                weight += 0.2

            bias += 0.55 * weight
            hits += 1

            title = candidate.get("title") or strategy_id
            if isinstance(title, str) and title not in titles:
                titles.append(title)

        return {
            "bias": max(0.0, min(1.2, bias)),
            "hits": hits,
            "titles": titles[:3],
        }

    def _load_platform_strategy_promotions(self, workspace: Path) -> List[Dict[str, Any]]:
        root = workspace / ".platform_shared" / "strategy_promotions"
        if not root.is_dir():
            return []

        items: List[Dict[str, Any]] = []
        for file_path in sorted(root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                items.append(payload)
        return items[:20]

    def _platform_shared_task_type(self, review_entry: Dict[str, Any]) -> Optional[str]:
        strategy_id = str(review_entry.get("strategy_id", "")) if isinstance(review_entry, dict) else ""
        if "reconstruct" in strategy_id:
            return "reconstruct"
        if "analyze" in strategy_id:
            return "analyze"
        return None

    def _platform_shared_domain(self, strategy_id: str) -> Optional[str]:
        if ".javascript." in strategy_id or strategy_id.startswith("builtin.javascript"):
            return "javascript"
        return None

    def _is_plugin_allowed(self, tenant_id: str, plugin_name: Optional[str]) -> bool:
        if not plugin_name:
            return True

        policy = self.tenant_manager.get_plugin_policy(tenant_id)
        enabled = set(policy.get("enabled", []))
        disabled = set(policy.get("disabled", []))

        if plugin_name in disabled:
            return False
        if enabled:
            return plugin_name in enabled
        return True


__all__ = [
    "CandidateScore",
    "DecisionRecord",
    "DecisionEngine",
]
