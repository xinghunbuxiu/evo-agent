"""Tenant-scoped Experience Reflection submission and review API."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import Request

from core.experience_reflection import ExperienceReflectionStore


def _actor_id(user: dict) -> str:
    user_id = str(user.get("id") or "").strip()
    provider = str(user.get("auth_provider") or "local").strip().lower()
    if not user_id:
        raise ValueError("authenticated user has no stable ID")
    return f"{provider}:{user_id}"


def _idempotency_key(request: Request) -> str | None:
    raw = str(request.headers.get("idempotency-key") or "").strip().lower()
    try:
        parsed = uuid.UUID(raw)
    except (ValueError, AttributeError):
        return None
    return raw if str(parsed) == raw else None


def register_experience_reflection_routes(
    app,
    *,
    workspace: Path,
    get_session_user,
    authorize_tenant,
    tenant_role,
    success_response,
    error_response,
) -> None:
    @app.get("/api/tenants/{tenant_id}/experience-reflections")
    async def list_experience_reflections(request: Request, tenant_id: str, source_experience_id: str | None = None):
        user = get_session_user(request)
        if not user:
            return error_response("未登录", 401)
        if not authorize_tenant(user, tenant_id):
            return error_response("无权访问该租户", 403)
        if tenant_role(user, tenant_id) not in {"tenant_admin", "member", "viewer"}:
            return error_response("当前用户没有读取 Reflection 的租户权限", 403)
        source_id = str(source_experience_id or "").strip() or None
        try:
            items = ExperienceReflectionStore(workspace, tenant_id).list_reviewed_for_source(source_id)
        except ValueError as exc:
            message = str(exc)
            return error_response(message, 404 if "does not exist" in message else 409)
        except (OSError, RuntimeError):
            return error_response("Reflection 读取失败", 503)
        return success_response({
            "tenant_id": tenant_id,
            "source_experience_id": source_id,
            "items": items,
        })

    @app.post("/api/tenants/{tenant_id}/experience-reflections")
    async def submit_experience_reflection(request: Request, tenant_id: str):
        user = get_session_user(request)
        if not user:
            return error_response("未登录", 401)
        if not authorize_tenant(user, tenant_id):
            return error_response("无权访问该租户", 403)
        if tenant_role(user, tenant_id) not in {"tenant_admin", "member"}:
            return error_response("当前用户没有提交 Reflection 的租户权限", 403)
        key = _idempotency_key(request)
        if not key:
            return error_response("必须通过 Idempotency-Key 请求头提供规范 UUID 幂等键", 400)
        try:
            data = await request.json()
        except Exception:
            return error_response("请求 JSON 无效", 400)
        if not isinstance(data, dict) or not {"source_experience_id", "findings"} <= set(data):
            return error_response("请求必须包含 source_experience_id 和 findings", 400)
        if set(data) - {"source_experience_id", "findings", "source_evidence_refs"}:
            return error_response("请求包含不允许的字段；tenant 和 author 从会话中解析", 400)
        source_id = str(data.get("source_experience_id") or "").strip()
        findings = data.get("findings")
        refs = data.get("source_evidence_refs", [])
        if not source_id:
            return error_response("source_experience_id 不能为空", 400)
        if not isinstance(findings, dict) or not findings:
            return error_response("findings 必须是非空对象", 400)
        if not isinstance(refs, list) or any(not isinstance(item, str) for item in refs):
            return error_response("source_evidence_refs 必须是字符串数组", 400)
        try:
            actor = _actor_id(user)
            reflection = ExperienceReflectionStore(workspace, tenant_id).append(
                source_id,
                author=actor,
                findings=findings,
                source_evidence_refs=refs,
                idempotency_key=key,
            )
        except ValueError as exc:
            message = str(exc)
            status = 404 if "does not exist" in message else 409 if "already used" in message or "changed" in message else 400
            return error_response(message, status)
        except (OSError, RuntimeError):
            return error_response("Reflection 提交未能完成；请使用同一幂等键安全重试", 503)
        return success_response({"tenant_id": tenant_id, "reflection": reflection.to_dict()}, "Reflection 已追加")

    @app.post("/api/tenants/{tenant_id}/experience-reflections/{reflection_id}/decision")
    async def decide_experience_reflection(request: Request, tenant_id: str, reflection_id: str):
        user = get_session_user(request)
        if not user:
            return error_response("未登录", 401)
        if not authorize_tenant(user, tenant_id):
            return error_response("无权访问该租户", 403)
        if tenant_role(user, tenant_id) != "tenant_admin":
            return error_response("Reflection 复核仅允许 tenant_admin", 403)
        key = _idempotency_key(request)
        if not key:
            return error_response("必须通过 Idempotency-Key 请求头提供规范 UUID 幂等键", 400)
        try:
            data = await request.json()
        except Exception:
            return error_response("请求 JSON 无效", 400)
        if not isinstance(data, dict) or "decision" not in data or set(data) - {"decision", "reason"}:
            return error_response("请求只允许 decision 和 reason", 400)
        outcome = str(data.get("decision") or "").strip().lower()
        reason = data.get("reason")
        if outcome not in {"accepted", "rejected"}:
            return error_response("decision 只能是 accepted 或 rejected", 400)
        if reason is not None and not isinstance(reason, str):
            return error_response("reason 必须是字符串", 400)
        try:
            actor = _actor_id(user)
            record = ExperienceReflectionStore(workspace, tenant_id).decide(
                reflection_id,
                reviewer=actor,
                decision=outcome,
                reason=reason,
                idempotency_key=key,
            )
        except ValueError as exc:
            message = str(exc)
            if "does not exist" in message:
                status = 404
            elif "cannot review their own" in message:
                status = 403
            elif "already" in message or "idempotency_key" in message:
                status = 409
            else:
                status = 400
            return error_response(message, status)
        except (OSError, RuntimeError):
            return error_response("Reflection 决策未能完成；请使用同一幂等键安全重试", 503)
        return success_response({"tenant_id": tenant_id, "decision": record.to_dict()}, "Reflection 复核决定已追加")
