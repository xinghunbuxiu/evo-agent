"""
租户级通用模型提供方（OpenAI-compatible）。

用于供给环自主学习：DeepSeek / 通义 / 本地网关等，只要兼容 chat/completions。
不绑定任何平台品牌业务逻辑。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_MODEL_PROVIDER: dict[str, Any] = {
    "enabled": False,
    "label": "openai_compatible",
    "base_url": "",
    "api_key": "",
    "model": "",
}


def normalize_model_provider(payload: dict | None) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    base_url = str(raw.get("base_url") or "").strip().rstrip("/")
    return {
        "enabled": bool(raw.get("enabled")),
        "label": str(raw.get("label") or "openai_compatible").strip() or "openai_compatible",
        "base_url": base_url,
        "api_key": str(raw.get("api_key") or "").strip(),
        "model": str(raw.get("model") or "").strip(),
    }


def mask_model_provider(provider: dict | None) -> dict[str, Any]:
    normalized = normalize_model_provider(provider)
    key = normalized.get("api_key") or ""
    if key:
        normalized["api_key"] = ("*" * min(8, len(key))) + key[-4:] if len(key) > 4 else "****"
        normalized["api_key_configured"] = True
    else:
        normalized["api_key"] = ""
        normalized["api_key_configured"] = False
    return normalized


def merge_model_provider_update(existing: dict | None, patch: dict | None) -> dict[str, Any]:
    current = normalize_model_provider(existing)
    incoming = patch if isinstance(patch, dict) else {}
    next_provider = {
        **current,
        **{
            key: incoming[key]
            for key in ("enabled", "label", "base_url", "model")
            if key in incoming
        },
    }
    if "api_key" in incoming:
        raw_key = str(incoming.get("api_key") or "").strip()
        # Keep previous key when UI sends masked / empty placeholder
        if raw_key and "*" not in raw_key:
            next_provider["api_key"] = raw_key
        elif not raw_key:
            next_provider["api_key"] = current.get("api_key") or ""
    return normalize_model_provider(next_provider)


def resolve_model_provider(tenant_manager, tenant_id: str) -> dict[str, Any]:
    policy = {}
    try:
        policy = tenant_manager.get_external_learning_policy(tenant_id) if tenant_manager else {}
    except Exception:
        policy = {}
    provider = normalize_model_provider(
        policy.get("model_provider") if isinstance(policy, dict) else None
    )
    # Env fallback for desktop: EVO_MODEL_BASE_URL / EVO_MODEL_API_KEY / EVO_MODEL_NAME
    if not provider.get("base_url"):
        provider["base_url"] = str(os.getenv("EVO_MODEL_BASE_URL") or "").strip().rstrip("/")
    if not provider.get("api_key"):
        provider["api_key"] = str(os.getenv("EVO_MODEL_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not provider.get("model"):
        provider["model"] = str(os.getenv("EVO_MODEL_NAME") or os.getenv("DEEPSEEK_MODEL") or "").strip()
    if provider.get("base_url") and provider.get("api_key") and provider.get("model"):
        if not provider.get("enabled") and (
            os.getenv("EVO_MODEL_BASE_URL") or os.getenv("DEEPSEEK_API_KEY")
        ):
            provider["enabled"] = True
    return provider


def model_provider_ready(provider: dict | None) -> bool:
    normalized = normalize_model_provider(provider)
    return bool(
        normalized.get("enabled")
        and normalized.get("base_url")
        and normalized.get("api_key")
        and normalized.get("model")
    )


def _chat_completions_url(base_url: str) -> str:
    root = str(base_url or "").strip().rstrip("/")
    if root.endswith("/chat/completions"):
        return root
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


def complete_chat(
    provider: dict | None,
    *,
    messages: list[dict[str, str]],
    temperature: float = 0.3,
    timeout_sec: float = 45.0,
) -> dict[str, Any]:
    """Call OpenAI-compatible chat completions. Returns {status, content, detail, provider_label}."""
    if str(os.getenv("EVO_MODEL_PROVIDER_MOCK") or "").strip().lower() in {"1", "true", "yes"}:
        user_text = ""
        for item in messages:
            if str(item.get("role") or "") == "user":
                user_text = str(item.get("content") or "")
                break
        return {
            "status": "completed",
            "content": (
                "【模拟模型学习结论】\n"
                f"围绕目标整理可执行步骤：{user_text[:240]}\n"
                "1. 澄清缺口与验收标准\n"
                "2. 做一次最小可验证动作\n"
                "3. 记录结果并沉淀为岗位经验"
            ),
            "detail": "mock",
            "provider_label": "mock",
            "model": "mock-model",
        }

    normalized = normalize_model_provider(provider)
    if not model_provider_ready(normalized):
        return {
            "status": "unavailable",
            "content": "",
            "detail": "model_provider_not_configured",
            "provider_label": normalized.get("label"),
            "model": normalized.get("model"),
        }

    url = _chat_completions_url(str(normalized["base_url"]))
    body = {
        "model": normalized["model"],
        "messages": messages,
        "temperature": temperature,
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {normalized['api_key']}",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw) if raw else {}
        choices = data.get("choices") if isinstance(data, dict) else None
        content = ""
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else {}
            content = str((message or {}).get("content") or "").strip()
        if not content:
            return {
                "status": "error",
                "content": "",
                "detail": "empty_model_response",
                "provider_label": normalized.get("label"),
                "model": normalized.get("model"),
            }
        return {
            "status": "completed",
            "content": content,
            "detail": None,
            "provider_label": normalized.get("label"),
            "model": normalized.get("model"),
        }
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else str(exc)
        return {
            "status": "error",
            "content": "",
            "detail": f"http_{exc.code}:{detail[:240]}",
            "provider_label": normalized.get("label"),
            "model": normalized.get("model"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "content": "",
            "detail": str(exc)[:240],
            "provider_label": normalized.get("label"),
            "model": normalized.get("model"),
        }


def build_knowledge_learning_messages(*, goal: str, queries: list[str], role_hint: str = "") -> list[dict[str, str]]:
    query_block = "\n".join(f"- {q}" for q in queries[:8] if str(q).strip()) or "- （无额外检索词）"
    role = str(role_hint or "岗位员工").strip() or "岗位员工"
    return [
        {
            "role": "system",
            "content": (
                "你是个人公司里的岗位教练。根据缺口给出可执行补知识方案，"
                "输出简洁中文：结论摘要、3-5 条下一步、需要验证的点。不要编造具体外部链接。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"角色：{role}\n"
                f"学习目标：{goal or '补齐当前岗位缺口'}\n"
                f"检索线索：\n{query_block}\n"
                "请给出可落地的补知识方案。"
            ),
        },
    ]


def run_configured_ai_assist(
    *,
    tenant_manager,
    tenant_id: str,
    goal: str,
    queries: list[str],
    role_hint: str = "",
) -> dict[str, Any]:
    provider = resolve_model_provider(tenant_manager, tenant_id)
    result = complete_chat(
        provider,
        messages=build_knowledge_learning_messages(goal=goal, queries=queries, role_hint=role_hint),
    )
    if result.get("status") != "completed":
        return {
            "source": "ai_assist",
            "status": result.get("status") or "unavailable",
            "candidate": None,
            "detail": result.get("detail"),
        }
    content = str(result.get("content") or "").strip()
    return {
        "source": "ai_assist",
        "status": "completed",
        "candidate": {
            "source": "ai_assist",
            "title": "模型补知识方案",
            "summary": content[:500],
            "confidence": 0.72,
            "evidence": [
                f"provider={result.get('provider_label')}",
                f"model={result.get('model')}",
                *[str(q) for q in queries[:3] if str(q).strip()],
            ],
            "next_steps": [
                "带着方案回到正式任务做最小验证",
                "记录结果差异并更新岗位经验",
                "稳定后再考虑扩权或接更大单",
            ],
            "metadata": {
                "provider_label": result.get("provider_label"),
                "model": result.get("model"),
                "full_content": content[:4000],
            },
        },
        "detail": None,
    }


def append_learning_experience_card(member: dict, *, learning_task: dict, summary: str) -> dict:
    """Append a learning card into member experience_journal (dedupe by signature)."""
    member_id = str(member.get("member_id") or "").strip() or "member"
    task_id = str(learning_task.get("task_id") or learning_task.get("id") or "").strip() or "learning"
    signature = f"knowledge_learning:{task_id}"
    journal = member.get("experience_journal") if isinstance(member.get("experience_journal"), dict) else {}
    cards = journal.get("cards") if isinstance(journal.get("cards"), list) else []
    if any(isinstance(card, dict) and str(card.get("signature") or "") == signature for card in cards):
        return member
    from datetime import datetime

    now_iso = datetime.now().isoformat()
    needed_caps = [
        str(x).strip()
        for x in (
            learning_task.get("needed_capabilities")
            if isinstance(learning_task.get("needed_capabilities"), list)
            else learning_task.get("queries") if isinstance(learning_task.get("queries"), list) else []
        )
        if str(x).strip()
    ]
    card = {
        "card_id": f"exp:learning:{task_id}:{int(datetime.now().timestamp() * 1000)}",
        "signature": signature,
        "title": f"补知识学习 · {str(learning_task.get('title') or task_id)[:80]}",
        "summary": str(summary or learning_task.get("goal") or "")[:400],
        "current_pattern": str(summary or "")[:280],
        "source": "knowledge_learning",
        "learning_task_id": task_id,
        "status": str(learning_task.get("status") or ""),
        "created_at": now_iso,
        "member_id": member_id,
        "metadata": {
            "needed_capabilities": needed_caps[:12],
            "goal": str(learning_task.get("goal") or "")[:200] or None,
        },
    }
    next_cards = [card, *[c for c in cards if isinstance(c, dict)]][:40]
    member["experience_journal"] = {
        **journal,
        "cards": next_cards,
        "last_compiled_at": now_iso,
        "card_count": len(next_cards),
    }
    growth = member.get("growth_state") if isinstance(member.get("growth_state"), dict) else {}
    member["growth_state"] = {
        **growth,
        "current_focus": f"消化补知识：{str(learning_task.get('title') or '学习任务')[:60]}",
        "last_reflection_at": now_iso,
    }
    return member


__all__ = [
    "DEFAULT_MODEL_PROVIDER",
    "normalize_model_provider",
    "mask_model_provider",
    "merge_model_provider_update",
    "resolve_model_provider",
    "model_provider_ready",
    "complete_chat",
    "run_configured_ai_assist",
    "append_learning_experience_card",
    "build_knowledge_learning_messages",
]
