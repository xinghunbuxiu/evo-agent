"""Tenant-scoped AI planning adapter for routed Mission Workers."""

from __future__ import annotations

import json
from typing import Any

from admin.model_provider_runtime import complete_chat, model_provider_ready, resolve_model_provider


def _safe_worker_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        key: manifest.get(key)
        for key in ("worker_id", "title", "capability_type", "task_types", "owned_modules", "capabilities")
        if key in manifest
    }


def _safe_task_context(context: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "work_type_id", "work_type_title", "work_type_deliverables",
        "work_type_required_inputs", "work_type_optional_inputs",
        "source_path", "source_dir", "bundle_path", "channel",
        "deliverable_goal", "goal_hint", "acceptance", "required_capabilities",
    )
    return {key: context[key] for key in allowed if key in context}


def build_worker_mission_plan_messages(
    *,
    goal: str,
    context: dict[str, Any],
    worker_manifest: dict[str, Any],
    reference_template: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    payload = {
        "goal": str(goal or "").strip(),
        "worker_manifest": _safe_worker_manifest(worker_manifest),
        "task_context": _safe_task_context(context),
        "reference_template": (
            reference_template if isinstance(reference_template, dict) else {}
        ),
    }
    return [
        {
            "role": "system",
            "content": (
                "你是被指派的专业 Worker。请先理解目标，再根据自己的岗位能力、输入条件、"
                "可复用参考流程和验收要求，制定本次任务真正需要的步骤。不要机械照搬参考模板；"
                "步骤数量和依赖必须由目标决定。只返回 JSON 对象，不输出 Markdown 或思维链。"
                "JSON 格式：{title,description,primary_capability_type,delivery,tasks}。"
                "tasks 为 1-24 个对象，每项必须包含 id,title,objective,task_type,capability_type,acceptance；"
                "可选 depends_on（id 数组）、parallel_safe（布尔值）、verification_contract（对象）。"
                "不要提出超出 manifest 能力范围的任务，不要要求执行未授权命令、访问密钥或绕过权限。"
                "Mission 主脑会独立审核计划、依赖、权限和验收条件；你的输出不是执行授权。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
    ]


def _parse_plan_content(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("worker plan response must be a JSON object")
    return parsed


def create_worker_mission_plan_proposer(tenant_manager):
    """Return a provider-backed proposal function; no provider means safe fallback."""

    def propose_worker_plan(
        *,
        tenant_id: str,
        goal: str,
        context: dict[str, Any],
        worker_manifest: dict[str, Any],
        reference_template: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        provider = resolve_model_provider(tenant_manager, tenant_id)
        if not model_provider_ready(provider):
            return {
                "status": "unavailable",
                "detail": "mission_plan_model_provider_not_configured",
            }
        response = complete_chat(
            provider,
            messages=build_worker_mission_plan_messages(
                goal=goal,
                context=context if isinstance(context, dict) else {},
                worker_manifest=worker_manifest if isinstance(worker_manifest, dict) else {},
                reference_template=reference_template,
            ),
            temperature=0.2,
            timeout_sec=45.0,
        )
        if response.get("status") != "completed":
            return {
                "status": response.get("status") or "error",
                "detail": response.get("detail"),
                "provider": response.get("provider_label"),
                "model": response.get("model"),
            }
        try:
            plan = _parse_plan_content(str(response.get("content") or ""))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return {
                "status": "invalid_response",
                "detail": f"{type(exc).__name__}: {exc}"[:240],
                "provider": response.get("provider_label"),
                "model": response.get("model"),
            }
        return {
            "status": "completed",
            "plan": plan,
            "provider": response.get("provider_label"),
            "model": response.get("model"),
        }

    return propose_worker_plan


__all__ = [
    "build_worker_mission_plan_messages",
    "create_worker_mission_plan_proposer",
]
