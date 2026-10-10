"""
Evo Core - Mission Planner

把用户目标转成:
- mission summary
- task decomposition
- capability gap analysis
- recommended next actions

先提供最小可运行版本，服务 JS 逆向和自动化运营两类主线。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .capabilities import CapabilityRegistry, get_capability_registry
from .capability_types import capability_type_label, infer_capability_type
from .learning import ExperienceStore, normalize_task_type
from .skill_system import SkillRegistry

try:
    from workers.registry import load_worker_mission_kind_templates
except ImportError:
    load_worker_mission_kind_templates = None  # type: ignore[assignment]


MISSION_KIND_TEMPLATES: dict[str, dict[str, Any]] = {
    "automation_operation": {
        "title": "Automation Operation Mission",
        "description": "面向运营目标的自动化拆解、执行、异常处理和持续优化。",
        "primary_capability_type": "automation",
        "delivery": [
            "可执行的流程设计",
            "自动化节点与异常处理机制",
            "运行经验与优化建议",
        ],
        "tasks": [
            {
                "id": "understand_goal",
                "title": "理解运营目标",
                "objective": "识别运营目标、交付物、账号体系、节奏和限制条件。",
                "task_type": "plan",
                "capability_type": "automation",
                "acceptance": "明确输出目标、渠道、频率与限制。",
            },
            {
                "id": "prepare_material",
                "title": "准备素材与内容链",
                "objective": "确定需要的头像、文案、素材、模板和数据来源。",
                "task_type": "collect",
                "capability_type": "automation",
                "acceptance": "明确内容来源和生成/采集方式。",
            },
            {
                "id": "build_flow",
                "title": "搭建自动化流程",
                "objective": "形成登录、发布、反馈回收、重试和调度闭环。",
                "task_type": "execute",
                "capability_type": "automation",
                "acceptance": "流程链可执行，关键节点有错误处理。",
            },
            {
                "id": "learn_missing_parts",
                "title": "补足缺口能力",
                "objective": "对平台限制、验证码、上传链路、发布规则等缺口进行学习。",
                "task_type": "learn",
                "capability_type": "automation",
                "acceptance": "缺口被归类并形成可验证方案。",
            },
            {
                "id": "review_and_iterate",
                "title": "复盘并持续优化",
                "objective": "跟踪成效、复盘失败原因并持续沉淀运营经验。",
                "task_type": "promote",
                "capability_type": "automation",
                "acceptance": "形成可复用的经验和下一轮优化点。",
            },
        ],
    },
}


@dataclass
class MissionNode:
    id: str
    title: str
    objective: str
    task_type: str
    capability_type: str
    acceptance: str
    status: str
    reasoning: List[str] = field(default_factory=list)
    decision_trace: List[Dict[str, Any]] = field(default_factory=list)
    available_capability_ids: List[str] = field(default_factory=list)
    recommended_skill_ids: List[str] = field(default_factory=list)
    recommended_skills: List[Dict[str, Any]] = field(default_factory=list)
    knowledge_signals: Dict[str, Any] = field(default_factory=dict)
    role_reflection_context: Dict[str, Any] = field(default_factory=dict)
    gap_type: str = ""
    blockers: List[str] = field(default_factory=list)
    learning_objectives: List[str] = field(default_factory=list)
    validation_checks: List[str] = field(default_factory=list)
    priority: str = "medium"
    next_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "objective": self.objective,
            "task_type": self.task_type,
            "capability_type": self.capability_type,
            "acceptance": self.acceptance,
            "status": self.status,
            "reasoning": self.reasoning,
            "decision_trace": self.decision_trace,
            "available_capability_ids": self.available_capability_ids,
            "recommended_skill_ids": self.recommended_skill_ids,
            "recommended_skills": self.recommended_skills,
            "knowledge_signals": self.knowledge_signals,
            "role_reflection_context": self.role_reflection_context,
            "gap_type": self.gap_type,
            "blockers": self.blockers,
            "learning_objectives": self.learning_objectives,
            "validation_checks": self.validation_checks,
            "priority": self.priority,
            "next_actions": self.next_actions,
        }


class MissionPlanner:
    def __init__(self, workspace: Path, registry: Optional[CapabilityRegistry] = None):
        self.workspace = workspace
        self.registry = registry or get_capability_registry()

    def _mission_kind_templates(self) -> dict[str, dict[str, Any]]:
        templates = dict(MISSION_KIND_TEMPLATES)
        if callable(load_worker_mission_kind_templates):
            templates.update(load_worker_mission_kind_templates(self.workspace))
        return templates

    def plan(
        self,
        *,
        tenant_id: str,
        goal: str,
        mission_kind: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        resolved_kind = mission_kind or self._infer_mission_kind(goal, context)
        templates = self._mission_kind_templates()
        template = templates.get(resolved_kind, templates["automation_operation"])
        nodes = [
            self._build_node(
                tenant_id=tenant_id,
                node_template=node_template,
                goal=goal,
                context=context,
            )
            for node_template in template.get("tasks", [])
            if isinstance(node_template, dict)
        ]
        status_summary = self._summarize_nodes(nodes)
        work_type_summary = self._work_type_summary(context)
        gap_summary = self._gap_summary(nodes, context)
        learning_tasks = self._build_learning_tasks(
            tenant_id=tenant_id,
            goal=goal,
            mission_kind=resolved_kind,
            context=context,
            nodes=nodes,
        )
        return {
            "tenant_id": tenant_id,
            "goal": goal,
            "mission_kind": resolved_kind,
            "title": template.get("title"),
            "description": template.get("description"),
            "primary_capability_type": template.get("primary_capability_type"),
            "delivery_targets": work_type_summary.get("deliverables", template.get("delivery", []))
            if isinstance(work_type_summary, dict)
            else template.get("delivery", []),
            "work_type_summary": work_type_summary,
            "status_summary": status_summary,
            "gap_summary": gap_summary,
            "learning_tasks": learning_tasks,
            "nodes": [node.to_dict() for node in nodes],
            "recommended_next_actions": self._recommended_actions(nodes, gap_summary, learning_tasks),
        }

    def _infer_mission_kind(self, goal: str, context: dict[str, Any]) -> str:
        mission_hint = str(context.get("mission_kind") or "").strip().lower()
        templates = self._mission_kind_templates()
        if mission_hint in templates:
            return mission_hint
        work_type_id = str(context.get("work_type_id") or "").strip()
        if work_type_id in templates:
            return work_type_id
        return "automation_operation"

    def _build_node(
        self,
        *,
        tenant_id: str,
        node_template: dict[str, Any],
        goal: str,
        context: dict[str, Any],
    ) -> MissionNode:
        capability_type = infer_capability_type(capability_type=node_template.get("capability_type"))
        matching = [
            descriptor
            for descriptor in self.registry.list_descriptors()
            if descriptor.capability_type == capability_type
        ]
        available_capability_ids = [descriptor.id for descriptor in matching]
        knowledge_signals = self._knowledge_signals(tenant_id=tenant_id, capability_type=capability_type)
        role_reflection_context = self._role_reflection_context(
            tenant_id=tenant_id,
            capability_type=capability_type,
            context=context,
        )
        matched_skills = self._match_verified_skills(
            tenant_id=tenant_id,
            capability_type=capability_type,
            task_type=str(node_template.get("task_type") or ""),
            goal=goal,
            context=context,
        )
        recommended_skill_ids = [skill.id for skill in matched_skills[:3]]
        recommended_skills = [self._skill_summary(skill) for skill in matched_skills[:3]]
        blockers = self._node_blockers(goal=goal, context=context, task_type=str(node_template.get("task_type") or ""))
        if role_reflection_context.get("blocked_reason"):
            blockers.append(str(role_reflection_context.get("blocked_reason")))
        validation_checks = self._validation_checks(
            task_type=str(node_template.get("task_type") or ""),
            capability_type=capability_type,
            acceptance=str(node_template.get("acceptance") or ""),
            context=context,
        )
        gap_type = "ready"
        priority = self._priority_for_task(str(node_template.get("task_type") or ""))
        learning_objectives: list[str] = []

        if blockers:
            status = "needs_input"
            gap_type = "input_gap"
            reasoning = [
                f"当前节点缺少必要输入: {', '.join(blockers[:3])}",
                "先补输入，再做能力选择和实验更稳",
            ]
            if role_reflection_context.get("summary"):
                reasoning.append(f"最近岗位反馈提示: {role_reflection_context.get('summary')}")
            learning_objectives = [
                "补齐 mission 关键输入，避免后续实验方向失真",
                "补完输入后重新评估现有能力是否足够",
            ]
            next_actions = [
                f"优先补齐输入: {', '.join(blockers[:3])}",
                "补齐后重新生成 mission plan",
            ]
        elif available_capability_ids and (
            knowledge_signals["experience_count"] > 0
            or knowledge_signals["verified_skill_count"] > 0
        ):
            status = "reuse_existing"
            gap_type = "reuse_existing"
            reasoning = [
                f"已有 {len(available_capability_ids)} 个可用能力入口",
                f"已有 {knowledge_signals['experience_count']} 条相关经验",
            ]
            if knowledge_signals["verified_skill_count"] > 0:
                reasoning.append(f"已有 {knowledge_signals['verified_skill_count']} 条 verified 技能可直接复用")
            if recommended_skill_ids:
                reasoning.append(f"当前节点优先建议复用技能: {', '.join(recommended_skill_ids)}")
            if role_reflection_context.get("summary"):
                reasoning.append(f"最近岗位反思: {role_reflection_context.get('summary')}")
            next_actions = [
                "先复用现有能力和经验执行",
                "执行后再对缺口做二次学习",
            ]
            if role_reflection_context.get("next_experiment"):
                next_actions.insert(0, str(role_reflection_context.get("next_experiment")))
            learning_objectives = [
                "优先验证已有能力在当前案例上是否仍然稳定",
                "把本轮执行结果追加到经验层，更新成功边界",
            ]
        elif available_capability_ids:
            status = "ready"
            gap_type = "knowledge_gap"
            reasoning = [
                f"已发现可用能力入口 {', '.join(available_capability_ids[:3])}",
                "但该方向沉淀经验还不够多",
            ]
            if recommended_skill_ids:
                reasoning.append(f"可优先试用已验证技能 {', '.join(recommended_skill_ids)}")
            if role_reflection_context.get("summary"):
                reasoning.append(f"岗位最近的真实卡点/模式: {role_reflection_context.get('summary')}")
            next_actions = [
                "先做最小实验确认可行路径",
                "把实验结果沉淀为经验条目",
            ]
            if role_reflection_context.get("next_experiment"):
                next_actions.insert(0, str(role_reflection_context.get("next_experiment")))
            learning_objectives = [
                "围绕当前节点补第一批可复用经验",
                "确认现有能力在该工种/案例下的适用边界",
            ]
        else:
            status = "needs_learning"
            gap_type = "capability_gap"
            reasoning = [
                f"当前没有直接覆盖 {capability_type_label(capability_type)} 的能力入口",
                "需要先补能力或借邻近能力做实验",
            ]
            if role_reflection_context.get("summary"):
                reasoning.append(f"最近岗位反馈也指出了训练方向: {role_reflection_context.get('summary')}")
            next_actions = [
                "先建立最小能力核或复用相邻能力类型",
                "围绕该节点做定向学习与小实验",
            ]
            if role_reflection_context.get("next_experiment"):
                next_actions.insert(0, str(role_reflection_context.get("next_experiment")))
            learning_objectives = [
                f"建立覆盖 {capability_type_label(capability_type)} 的最小能力入口",
                "明确需要新增的技能、策略或插件边界",
            ]

        if node_template.get("task_type") in {"learn", "promote"} and knowledge_signals["experience_count"] == 0:
            status = "needs_learning"
            gap_type = "experience_gap"
            learning_objectives.append("当前经验不足，先用真实案例补首批可验证样本")

        # Keep an auditable evidence trail, not hidden chain-of-thought: each record
        # names the rule, observable evidence, and outcome used by the planner.
        if blockers:
            decision_rule = "mission.status.input_gap.v1"
        elif available_capability_ids and (
            knowledge_signals["experience_count"] > 0
            or knowledge_signals["verified_skill_count"] > 0
        ):
            decision_rule = "mission.status.reuse_existing.v1"
        elif available_capability_ids:
            decision_rule = "mission.status.knowledge_gap.v1"
        else:
            decision_rule = "mission.status.capability_gap.v1"
        if gap_type == "experience_gap":
            decision_rule = "mission.status.experience_gap.v1"
        decision_trace = [
            {
                "step": "input_validation",
                "rule_id": "mission.required_inputs.v1",
                "result": "blocked" if blockers else "passed",
                "evidence": {"blocker_codes": list(blockers)},
            },
            {
                "step": "capability_match",
                "rule_id": "mission.capability_match.v1",
                "result": "matched" if available_capability_ids else "missing",
                "evidence": {
                    "capability_type": capability_type,
                    "capability_ids": list(available_capability_ids),
                },
            },
            {
                "step": "knowledge_check",
                "rule_id": "mission.knowledge_signals.v1",
                "result": "available" if (
                    knowledge_signals["experience_count"] > 0
                    or knowledge_signals["verified_skill_count"] > 0
                ) else "insufficient",
                "evidence": {
                    "experience_count": knowledge_signals["experience_count"],
                    "verified_skill_count": knowledge_signals["verified_skill_count"],
                    "top_experience_ids": list(knowledge_signals.get("top_experience_ids", [])),
                    "top_verified_skill_ids": list(knowledge_signals.get("top_verified_skill_ids", [])),
                },
            },
            {
                "step": "status_decision",
                "rule_id": decision_rule,
                "result": status,
                "evidence": {
                    "gap_type": gap_type,
                    "reasoning_summary": list(reasoning),
                    "blocker_codes": list(blockers),
                },
            },
        ]

        return MissionNode(
            id=str(node_template.get("id") or "node"),
            title=str(node_template.get("title") or "Mission Node"),
            objective=str(node_template.get("objective") or ""),
            task_type=str(node_template.get("task_type") or "plan"),
            capability_type=capability_type,
            acceptance=str(node_template.get("acceptance") or ""),
            status=status,
            reasoning=reasoning,
            decision_trace=decision_trace,
            available_capability_ids=available_capability_ids,
            recommended_skill_ids=recommended_skill_ids,
            recommended_skills=recommended_skills,
            knowledge_signals=knowledge_signals,
            role_reflection_context=role_reflection_context,
            gap_type=gap_type,
            blockers=blockers,
            learning_objectives=self._unique_list(learning_objectives),
            validation_checks=validation_checks,
            priority=priority,
            next_actions=next_actions,
        )

    def _node_blockers(self, *, goal: str, context: dict[str, Any], task_type: str) -> list[str]:
        if not isinstance(context, dict):
            return []
        blockers: list[str] = []
        mission_text = " ".join(
            str(item or "")
            for item in [
                goal,
                context.get("source_path"),
                context.get("bundle_path"),
                context.get("source_dir"),
                context.get("channel"),
                context.get("work_type_id"),
            ]
        ).lower()
        if task_type in {"analyze", "reconstruct", "validate"} and not any(
            str(context.get(key) or "").strip() for key in ["source_path", "bundle_path", "source_dir", "path"]
        ):
            blockers.append("source_path_or_source_dir")
        work_type_id = str(context.get("work_type_id") or "").strip()
        capability_type = str(context.get("capability_type") or "").strip()
        if (
            "automation" in mission_text
            or "运营" in goal
            or capability_type == "automation"
            or work_type_id.endswith("_operations")
        ):
            if not str(context.get("channel") or "").strip():
                blockers.append("channel")
            if not str(context.get("deliverable_goal") or context.get("goal_hint") or "").strip():
                blockers.append("deliverable_goal")
        return blockers

    def _validation_checks(
        self,
        *,
        task_type: str,
        capability_type: str,
        acceptance: str,
        context: dict[str, Any],
    ) -> list[str]:
        checks: list[str] = []
        if task_type == "analyze":
            checks.extend([
                "是否识别出入口、框架、打包边界",
                "是否给出下一步切入点而不只是罗列信息",
            ])
        elif task_type == "reconstruct":
            checks.extend([
                "是否产出可接手的目录骨架或组件结构",
                "关键页面、路由、资源映射是否基本可读",
            ])
        elif task_type == "validate":
            checks.extend([
                "是否明确说明当前结果可交付还是仍需学习",
                "是否指出最影响稳定交付的风险点",
            ])
        elif task_type in {"learn", "promote"}:
            checks.extend([
                "是否形成可复用经验，而不是只留日志",
                "是否有下一轮可以直接复用的规则或技能候选",
            ])
        elif capability_type == "automation":
            checks.extend([
                "是否明确渠道限制、素材链和执行节奏",
                "是否给出失败后的重试与复盘路径",
            ])
        if acceptance:
            checks.append(f"验收目标: {acceptance}")
        return self._unique_list(checks)

    def _priority_for_task(self, task_type: str) -> str:
        if task_type in {"analyze", "understand_goal", "identify_target"}:
            return "high"
        if task_type in {"reconstruct", "build_flow", "learn"}:
            return "high"
        if task_type in {"validate", "promote", "review_and_iterate"}:
            return "medium"
        return "medium"

    def _knowledge_signals(self, *, tenant_id: str, capability_type: str) -> dict[str, Any]:
        store = ExperienceStore(self.workspace, tenant_id)
        experiences = store.load_by_capability_type(capability_type, limit=20)
        skill_registry = SkillRegistry(self.workspace, tenant_id)
        listed_skills = skill_registry.list_skills(domain="javascript")
        verified_skills = listed_skills.get("local_verified", []) if isinstance(listed_skills, dict) else []
        if not isinstance(verified_skills, list):
            verified_skills = []
        verified_skills = [
            skill for skill in verified_skills
            if getattr(skill, "capability_type", None) == capability_type
        ]
        growth_events = [
            exp for exp in experiences
            if isinstance(exp.metadata, dict) and exp.metadata.get("growth_event")
        ]
        role_reflections = [
            exp for exp in experiences
            if normalize_task_type(exp.task_type) == "role_reflection"
            and isinstance(exp.metadata, dict)
            and isinstance(exp.metadata.get("professional_experience"), dict)
        ]
        latest_role_reflection = role_reflections[0] if role_reflections else None
        latest_role_payload = (
            latest_role_reflection.metadata.get("professional_experience", {})
            if latest_role_reflection and isinstance(latest_role_reflection.metadata, dict)
            else {}
        )
        latest_role_card = latest_role_payload.get("card", {}) if isinstance(latest_role_payload.get("card"), dict) else {}
        return {
            "experience_count": len(experiences),
            "growth_event_count": len(growth_events),
            "role_reflection_count": len(role_reflections),
            "top_experience_ids": [exp.id for exp in experiences[:3]],
            "verified_skill_count": len(verified_skills),
            "top_verified_skill_ids": [skill.id for skill in verified_skills[:3]],
            "latest_role_reflection_id": latest_role_reflection.id if latest_role_reflection else None,
            "latest_role_reflection_summary": latest_role_reflection.output_summary if latest_role_reflection else None,
            "latest_role_reflection_stage": latest_role_card.get("stage"),
        }

    def _role_reflection_context(
        self,
        *,
        tenant_id: str,
        capability_type: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        domain = self._infer_skill_domain(capability_type=capability_type, context=context)
        store = ExperienceStore(self.workspace, tenant_id)
        for exp in store.load_by_task(domain, "role_reflection", limit=10):
            metadata = exp.metadata if isinstance(exp.metadata, dict) else {}
            payload = metadata.get("professional_experience", {}) if isinstance(metadata.get("professional_experience"), dict) else {}
            card = payload.get("card", {}) if isinstance(payload.get("card"), dict) else {}
            role = str(payload.get("primary_role") or "").strip()
            if capability_type == "automation" and role:
                if role not in {"", "automation_operation"} and not role.endswith("_operations"):
                    continue
            return {
                "experience_id": exp.id,
                "member_id": payload.get("member_id"),
                "member_name": payload.get("member_name"),
                "primary_role": role,
                "summary": exp.output_summary,
                "stage": card.get("stage"),
                "status": card.get("status"),
                "blocked_reason": card.get("professional_risk"),
                "next_experiment": card.get("next_experiment"),
            }
        return {}

    def _match_verified_skills(
        self,
        *,
        tenant_id: str,
        capability_type: str,
        task_type: str,
        goal: str,
        context: dict[str, Any],
    ) -> list[Any]:
        skill_registry = SkillRegistry(self.workspace, tenant_id)
        domain = self._infer_skill_domain(capability_type=capability_type, context=context)
        listed_skills = skill_registry.list_skills(domain=domain)
        verified_skills = listed_skills.get("local_verified", []) if isinstance(listed_skills, dict) else []
        if not isinstance(verified_skills, list):
            verified_skills = []

        framework_hint = self._infer_framework_hint(goal=goal, context=context)
        matched: list[Any] = []
        for skill in verified_skills:
            if getattr(skill, "capability_type", None) != capability_type:
                continue
            parameters = skill.parameters if isinstance(skill.parameters, dict) else {}
            accepted_tasks = parameters.get("accepted_tasks", [])
            if isinstance(accepted_tasks, list) and accepted_tasks and task_type not in accepted_tasks:
                continue
            skill_framework = str(parameters.get("framework_hint") or "").strip().lower()
            if framework_hint and skill_framework and framework_hint != skill_framework:
                continue
            matched.append(skill)
        return matched

    def _infer_skill_domain(self, *, capability_type: str, context: dict[str, Any]) -> str:
        explicit = str(context.get("domain") or context.get("domain_hint") or "").strip().lower()
        if explicit:
            return explicit
        if capability_type.endswith("_reverse"):
            return capability_type[: -len("_reverse")]
        if capability_type:
            return capability_type
        return "general"

    def _infer_framework_hint(self, *, goal: str, context: dict[str, Any]) -> str:
        text_parts = [
            goal,
            str(context.get("framework_hint") or ""),
            str(context.get("source_path") or ""),
            str(context.get("bundle_path") or ""),
            str(context.get("source_dir") or ""),
        ]
        lowered = " ".join(part.lower() for part in text_parts if part)
        if "react" in lowered:
            return "react"
        if "vue" in lowered:
            return "vue"
        if "angular" in lowered:
            return "angular"
        return ""

    def _skill_summary(self, skill: Any) -> Dict[str, Any]:
        parameters = skill.parameters if isinstance(getattr(skill, "parameters", {}), dict) else {}
        return {
            "id": getattr(skill, "id", ""),
            "name": getattr(skill, "name", ""),
            "trust_level": getattr(getattr(skill, "trust_level", None), "value", ""),
            "success_rate": getattr(skill, "success_rate", 0.0),
            "usage_count": getattr(skill, "usage_count", 0),
            "framework_hint": parameters.get("framework_hint"),
            "accepted_tasks": parameters.get("accepted_tasks", []),
        }

    def _summarize_nodes(self, nodes: list[MissionNode]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for node in nodes:
            counts[node.status] = counts.get(node.status, 0) + 1
        overall_status = "ready"
        if counts.get("needs_learning"):
            overall_status = "needs_learning"
        elif counts.get("reuse_existing"):
            overall_status = "reuse_existing"
        return {
            "overall_status": overall_status,
            "node_count": len(nodes),
            "counts": counts,
        }

    def _recommended_actions(
        self,
        nodes: list[MissionNode],
        gap_summary: dict[str, Any],
        learning_tasks: list[dict[str, Any]],
    ) -> list[str]:
        actions: list[str] = []
        if gap_summary.get("input_gap_count"):
            actions.append("先补 mission 必要输入，再让系统判断真实能力缺口，避免误学")
        reflection_experiments = [
            str(node.role_reflection_context.get("next_experiment") or "").strip()
            for node in nodes
            if isinstance(node.role_reflection_context, dict) and str(node.role_reflection_context.get("next_experiment") or "").strip()
        ]
        if reflection_experiments:
            actions.append(f"优先参考岗位最近的下一步实验: {reflection_experiments[0]}")
        if any(node.status == "needs_learning" for node in nodes):
            actions.append("先挑出 needs_learning 节点做最小实验，不要一开始就全量铺开")
        if any(node.status == "reuse_existing" for node in nodes):
            actions.append("优先复用现有经验最厚的节点，尽快形成第一个可交付闭环")
        if learning_tasks:
            actions.append("把 learning_tasks 作为后台自治学习队列，逐个验证后再晋升为 verified 技能/经验")
        if not actions:
            actions.append("当前能力已基本可覆盖，建议直接进入执行与验证阶段")
        actions.append("把成功节点沉淀成经验/技能/策略，供下一轮 mission 直接复用")
        return self._unique_list(actions)

    def _gap_summary(self, nodes: list[MissionNode], context: dict[str, Any]) -> dict[str, Any]:
        gap_counts: dict[str, int] = {}
        high_priority_nodes: list[str] = []
        blockers: list[str] = []
        for node in nodes:
            gap_key = node.gap_type or node.status or "unknown"
            gap_counts[gap_key] = gap_counts.get(gap_key, 0) + 1
            if node.priority == "high" and node.status in {"needs_learning", "needs_input", "ready"}:
                high_priority_nodes.append(node.id)
            blockers.extend(node.blockers)
        return {
            "total_nodes": len(nodes),
            "input_gap_count": gap_counts.get("input_gap", 0),
            "capability_gap_count": gap_counts.get("capability_gap", 0),
            "experience_gap_count": gap_counts.get("experience_gap", 0),
            "knowledge_gap_count": gap_counts.get("knowledge_gap", 0),
            "reuse_existing_count": gap_counts.get("reuse_existing", 0),
            "high_priority_node_ids": high_priority_nodes[:5],
            "blockers": self._unique_list(blockers),
            "enabled_packages": context.get("enabled_packages", []) if isinstance(context.get("enabled_packages"), list) else [],
        }

    def _build_learning_tasks(
        self,
        *,
        tenant_id: str,
        goal: str,
        mission_kind: str,
        context: dict[str, Any],
        nodes: list[MissionNode],
    ) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for node in nodes:
            if node.status not in {"needs_learning", "needs_input", "ready"}:
                continue
            if node.status == "reuse_existing":
                continue
            tasks.append({
                "task_id": f"draft_{tenant_id}_{mission_kind}_{node.id}",
                "tenant_id": tenant_id,
                "mission_kind": mission_kind,
                "node_id": node.id,
                "title": node.title,
                "status": node.status,
                "priority": node.priority,
                "gap_type": node.gap_type,
                "capability_type": node.capability_type,
                "goal": goal,
                "blockers": node.blockers,
                "learning_objectives": node.learning_objectives,
                "validation_checks": node.validation_checks,
                "recommended_skill_ids": node.recommended_skill_ids,
                "source_context": {
                    "source_path": context.get("source_path") or context.get("bundle_path") or context.get("path"),
                    "source_dir": context.get("source_dir"),
                    "work_type_id": context.get("work_type_id"),
                    "role_reflection_context": node.role_reflection_context,
                },
                "next_actions": node.next_actions,
            })
        return tasks

    def _unique_list(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in items:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    def _work_type_summary(self, context: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(context, dict):
            return {}
        required_inputs = context.get("work_type_required_inputs", [])
        optional_inputs = context.get("work_type_optional_inputs", [])
        deliverables = context.get("work_type_deliverables", [])
        knowledge_policy = context.get("work_type_knowledge_policy", {})
        return {
            "work_type_id": context.get("work_type_id"),
            "title": context.get("work_type_title"),
            "required_inputs": required_inputs if isinstance(required_inputs, list) else [],
            "optional_inputs": optional_inputs if isinstance(optional_inputs, list) else [],
            "deliverables": deliverables if isinstance(deliverables, list) else [],
            "knowledge_policy": knowledge_policy if isinstance(knowledge_policy, dict) else {},
            "enabled_packages": context.get("enabled_packages", []) if isinstance(context.get("enabled_packages"), list) else [],
        }


__all__ = ["MissionPlanner", "MISSION_KIND_TEMPLATES"]
