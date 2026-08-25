"""
JavaScript 内置能力 Provider

当前仍复用 commands.py 中已经存在的实现，
但从内核视角它已经是一个可注册、可替换的能力插件。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from core.capabilities import CapabilityDescriptor, CapabilityProvider, TaskContext, TaskResult

from .commands import init_workspace, analyze_bundle, reconstruct_project


class JavaScriptCapabilityProvider(CapabilityProvider):
    """内置 JavaScript 能力。"""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            id="builtin.javascript",
            name="JavaScript Reverse Capability",
            version="2.0.0",
            provider_kind="builtin",
            capability_type="javascript_reverse",
            description="内置 JS 逆向、分析、重构能力",
            supported_tasks=["init", "analyze", "reconstruct"],
            tags=["javascript", "reverse", "builtin"],
            customizable=True,
        )

    def init_workspace(self, workspace: Path, tenant_id: str = "default") -> Dict[str, Any]:
        result = init_workspace(workspace, tenant_id)
        result["capability_id"] = self.descriptor.id
        return result

    def execute(self, context: TaskContext) -> TaskResult:
        decision = context.parameters.get("_decision")
        matched_verified_skills = context.parameters.get("_matched_verified_skills", [])
        skill_execution_template = context.parameters.get("_skill_execution_template", {})
        if not isinstance(matched_verified_skills, list):
            matched_verified_skills = []
        if not isinstance(skill_execution_template, dict):
            skill_execution_template = {}

        if context.task_type == "init":
            data = self.init_workspace(context.workspace, context.tenant_id)
            return TaskResult(
                success=True,
                capability_id=self.descriptor.id,
                task_type=context.task_type,
                summary="JavaScript workspace initialized",
                confidence=1.0,
                data=data,
            )

        if context.task_type == "analyze":
            if not context.input_path:
                raise ValueError("JavaScript analyze task requires input_path")
            data = analyze_bundle(
                workspace=context.workspace,
                bundle_path=context.input_path,
                tenant_id=context.tenant_id,
                save_experience=context.parameters.get("save_experience", True),
                capability_id=self.descriptor.id,
                decision=decision,
                skill_template=skill_execution_template,
            )
            return TaskResult(
                success=bool(data.get("success")),
                capability_id=self.descriptor.id,
                task_type=context.task_type,
                summary=f"Analyzed bundle: {context.input_path.name}",
                confidence=float(data.get("confidence", 0.0)),
                data={
                    **data,
                    "matched_verified_skills": matched_verified_skills,
                    "skill_execution_template": skill_execution_template,
                },
                feedback={
                    "frameworks": data.get("frameworks", []),
                    "patterns": data.get("patterns", []),
                    "matched_verified_skills": matched_verified_skills,
                    "skill_execution_template": skill_execution_template,
                },
            )

        if context.task_type == "reconstruct":
            analysis_result = context.parameters.get("analysis_result", {})
            auto_analyzed = False
            if not analysis_result and context.input_path:
                analysis_result = analyze_bundle(
                    workspace=context.workspace,
                    bundle_path=context.input_path,
                    tenant_id=context.tenant_id,
                    save_experience=False,
                    capability_id=self.descriptor.id,
                    decision=decision,
                    skill_template=skill_execution_template,
                )
                auto_analyzed = True
            source_dir = context.source_dir or context.input_path
            if not source_dir:
                raise ValueError("JavaScript reconstruct task requires source_dir or input_path")
            if source_dir.is_file():
                source_dir = source_dir.parent
            data = reconstruct_project(
                workspace=context.workspace,
                analysis_result=analysis_result,
                source_dir=source_dir,
                tenant_id=context.tenant_id,
                capability_id=self.descriptor.id,
                decision=decision,
                skill_template=skill_execution_template,
            )
            return TaskResult(
                success=bool(data.get("success")),
                capability_id=self.descriptor.id,
                task_type=context.task_type,
                summary=f"Reconstructed project for {analysis_result.get('frameworks', ['unknown'])[0] if analysis_result.get('frameworks') else 'unknown'}",
                confidence=0.8 if data.get("success") else 0.0,
                data={
                    **data,
                    "matched_verified_skills": matched_verified_skills,
                    "skill_execution_template": skill_execution_template,
                },
                feedback={
                    "auto_analyzed": auto_analyzed,
                    "matched_verified_skills": matched_verified_skills,
                    "skill_execution_template": skill_execution_template,
                },
            )

        raise ValueError(f"Unsupported JavaScript task: {context.task_type}")


__all__ = ["JavaScriptCapabilityProvider"]
