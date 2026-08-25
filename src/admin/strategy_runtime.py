"""
策略复盘与平台共享的持久化辅助。
"""

from __future__ import annotations

import json
from pathlib import Path


def get_platform_shared_root(workspace: Path) -> Path:
    root = workspace / ".platform_shared"
    root.mkdir(parents=True, exist_ok=True)
    return root


def list_platform_strategy_promotions(workspace: Path, limit: int = 20) -> list[dict]:
    root = get_platform_shared_root(workspace) / "strategy_promotions"
    if not root.is_dir():
        return []

    items: list[dict] = []
    for file_path in sorted(root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        review_entry = payload.get("review_entry") if isinstance(payload, dict) else None
        candidate = review_entry.get("upgrade_candidate") if isinstance(review_entry, dict) else None
        items.append({
            "id": file_path.stem,
            "tenant_id": payload.get("tenant_id"),
            "strategy_id": payload.get("strategy_id"),
            "promoted_at": payload.get("promoted_at"),
            "path": str(file_path),
            "share_mode": (
                payload.get("knowledge_policy", {}).get("share_mode")
                if isinstance(payload.get("knowledge_policy"), dict)
                else None
            ),
            "decision": candidate.get("decision") if isinstance(candidate, dict) else None,
            "summary": candidate.get("summary") if isinstance(candidate, dict) else None,
            "title": candidate.get("title") if isinstance(candidate, dict) else None,
        })
        if len(items) >= limit:
            break
    return items


def review_queue_file(workspace: Path, tenant_id: str) -> Path:
    queue_dir = workspace / ".tenants" / tenant_id / "data"
    queue_dir.mkdir(parents=True, exist_ok=True)
    return queue_dir / "strategy_review_queue.json"


def load_review_queue(workspace: Path, tenant_id: str) -> list[dict]:
    queue_file = review_queue_file(workspace, tenant_id)
    if not queue_file.is_file():
        return []
    try:
        with open(queue_file, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_review_queue(workspace: Path, tenant_id: str, items: list[dict]) -> None:
    queue_file = review_queue_file(workspace, tenant_id)
    with open(queue_file, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
