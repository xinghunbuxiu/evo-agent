"""
自媒体产物本地降级导出：远端 Git 不可用时写入 workspace，满足 M1「仅本地 workspace」验收。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def export_self_media_artifacts_locally(
    workspace: Path,
    *,
    tenant_id: str,
    task_id: str,
    task_type: str,
    exports: list[dict[str, Any]],
    index_entries: list[dict[str, Any]] | None = None,
    remote_reason: str = "",
) -> dict:
    root = workspace / ".admin" / "local_git_exports" / tenant_id
    root.mkdir(parents=True, exist_ok=True)
    saved_files: list[str] = []
    for item in exports:
        file_path = str(item.get("file_path") or "").strip()
        if not file_path:
            continue
        target = root / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(item.get("content") or ""), encoding="utf-8")
        saved_files.append(file_path)

    index_payload = {
        "schema_version": "1.0",
        "tenant_id": tenant_id,
        "generated_at": datetime.now().isoformat(),
        "description": "Local fallback for self media exports when remote Git is unavailable.",
        "remote_reason": remote_reason,
        "entries": index_entries or [],
    }
    index_path = root / "evo" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    saved_files.append("evo/index.json")

    manifest = {
        "task_id": task_id,
        "task_type": task_type,
        "exported_at": datetime.now().isoformat(),
        "status": "local_only",
        "files": saved_files,
        "local_root": str(root),
    }
    manifest_path = root / "manifests" / f"{task_id}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "status": "local_only",
        "reason": remote_reason or "remote_git_unavailable",
        "local_root": str(root),
        "files": saved_files,
        "next_action": "远端仓库就绪后可重新 export；当前产物已落盘本地 workspace",
    }


def export_commercial_intake_experience_locally(
    workspace: Path,
    *,
    tenant_id: str | None,
    member: dict,
    intake: dict,
    settled_amount: float | None = None,
) -> dict:
    """消费环结算后把员工商业经验落到本地 Git 降级目录（远端未就绪时也可验收）。"""
    normalized_tenant = str(tenant_id or "default").strip() or "default"
    member_id = str((member or {}).get("member_id") or "member").strip() or "member"
    intake_id = str((intake or {}).get("intake_id") or "intake").strip() or "intake"
    safe_intake = intake_id.replace(":", "_").replace("/", "_")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"exports/commercial/{stamp}_{member_id}_{safe_intake}.json"

    journal = member.get("experience_journal") if isinstance(member.get("experience_journal"), dict) else {}
    growth = member.get("growth_state") if isinstance(member.get("growth_state"), dict) else {}
    cards = journal.get("cards") if isinstance(journal.get("cards"), list) else []
    commercial_cards = [
        card
        for card in cards
        if isinstance(card, dict)
        and (
            str(card.get("signature") or "").startswith("commercial_intake:")
            or str(card.get("signature") or "") == f"commercial_intake:{intake_id}"
        )
    ]
    payload = {
        "schema_version": "1.0",
        "source": "commercial_intake_settle",
        "tenant_id": normalized_tenant,
        "exported_at": datetime.now().isoformat(),
        "member_id": member_id,
        "intake_id": intake_id,
        "settled_amount": settled_amount,
        "currency": str((intake or {}).get("currency") or "CNY").strip() or "CNY",
        "intake": {
            "title": (intake or {}).get("title"),
            "needed_capabilities": list((intake or {}).get("needed_capabilities") or []),
            "project_id": (intake or {}).get("project_id"),
            "client_label": (intake or {}).get("client_label"),
            "quoted_amount": (intake or {}).get("quoted_amount"),
            "settled_at": (intake or {}).get("settled_at"),
        },
        "growth_state": {
            "commercial_settled_count": growth.get("commercial_settled_count"),
            "commercial_settled_revenue": growth.get("commercial_settled_revenue"),
            "last_commercial_intake_id": growth.get("last_commercial_intake_id"),
            "current_focus": growth.get("current_focus"),
            "next_goal": growth.get("next_goal"),
        },
        "commercial_experience_cards": commercial_cards[-5:],
        "journal_summary": {
            "card_count": len(cards),
            "last_compiled_at": journal.get("last_compiled_at"),
        },
    }

    result = export_self_media_artifacts_locally(
        workspace,
        tenant_id=normalized_tenant,
        task_id=f"commercial_{safe_intake}",
        task_type="commercial_intake_settle",
        exports=[{
            "file_path": file_path,
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
        }],
        index_entries=[{
            "kind": "commercial_intake_experience",
            "member_id": member_id,
            "intake_id": intake_id,
            "file_path": file_path,
            "exported_at": payload["exported_at"],
        }],
        remote_reason="commercial_settle_local_first",
    )
    return {
        **result,
        "status": "local_exported",
        "file_path": file_path,
        "member_id": member_id,
        "intake_id": intake_id,
        "next_action": "远端 experiences 仓就绪后可同步；当前商业经验已落盘本地 workspace",
    }
