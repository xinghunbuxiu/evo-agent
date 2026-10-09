#!/usr/bin/env python3
"""
清空 E2E 测试脏数据，保留内置育成师 + 平台配置 + 执行器注册表。

用法:
  cd evo-os
  PYTHONPATH=src python3 scripts/reset_workspace_for_e2e.py
  PYTHONPATH=src python3 scripts/reset_workspace_for_e2e.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from admin.finance_runtime import purge_preset_finance_data  # noqa: E402
from admin.runtime_state import (  # noqa: E402
    load_autonomy_runtime,
    normalize_autonomy_runtime,
    save_autonomy_runtime,
)
from project_caps import purge_preset_project_packages  # noqa: E402


def _rm_tree(path: Path, *, dry_run: bool) -> bool:
    if not path.exists():
        return False
    if dry_run:
        print(f"[dry-run] remove tree: {path}")
        return True
    if path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)
    return True


def _write_json(path: Path, payload: dict, *, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def reset_workspace(workspace: Path, *, dry_run: bool = False) -> dict:
    actions: list[str] = []

    # 1. 队列与任务残留
    queue_dir = workspace / ".queue"
    if queue_dir.is_dir():
        for item in queue_dir.glob("*.json"):
            item.unlink(missing_ok=not dry_run) if not dry_run else None
            if dry_run:
                print(f"[dry-run] remove {item}")
            actions.append(f"queue:{item.name}")
        if not dry_run:
            remaining = list(queue_dir.glob("*.json"))
            actions.append(f"queue_cleared:{len(actions)} files")

    for rel in (
        ".admin/mission_runs.json",
        ".admin/learning_tasks.json",
    ):
        path = workspace / rel
        if path.is_file():
            if dry_run:
                print(f"[dry-run] remove {path}")
            else:
                path.unlink()
            actions.append(f"removed:{rel}")

    # 2. 财务与预置包
    finance_removed = purge_preset_finance_data(workspace) if not dry_run else []
    if dry_run:
        finance_dir = workspace / ".admin" / "finance"
        if finance_dir.is_dir():
            for item in finance_dir.glob("*.json"):
                print(f"[dry-run] remove finance {item.name}")
                finance_removed.append(item.stem)
    package_removed = purge_preset_project_packages(workspace) if not dry_run else []
    actions.append(f"finance_purged:{finance_removed}")
    actions.append(f"packages_purged:{package_removed}")

    # 3. 工种回到空列表（第一步从「添加工种」开始）
    work_types_path = workspace / ".admin" / "work_types.json"
    _write_json(work_types_path, {"version": 1, "items": []}, dry_run=dry_run)
    actions.append("work_types_reset")

    worker_registry_path = workspace / ".admin" / "worker_registry.json"
    if worker_registry_path.is_file() and not dry_run:
        try:
            registry_payload = json.loads(worker_registry_path.read_text(encoding="utf-8"))
            workers = registry_payload.get("workers", {}) if isinstance(registry_payload.get("workers"), dict) else {}
            for worker_id, entry in workers.items():
                if isinstance(entry, dict):
                    entry["enabled"] = False
            registry_payload["workers"] = workers
            _write_json(worker_registry_path, registry_payload, dry_run=False)
            actions.append("worker_registry_disabled")
        except Exception:
            actions.append("worker_registry_reset_skipped")
    elif dry_run and worker_registry_path.is_file():
        print(f"[dry-run] disable all workers in {worker_registry_path}")
        actions.append("worker_registry_disabled")

    # 4. 租户经验 / 技能 / 成员工作区
    tenant_root = workspace / ".tenants" / "default"
    for sub in ("experiences", "skills", ".skill_cache", "members"):
        target = tenant_root / sub
        if _rm_tree(target, dry_run=dry_run):
            actions.append(f"tenant_cleared:{sub}")

    tenant_runtime = tenant_root / "autonomy_runtime.json"
    if tenant_runtime.is_file():
        if dry_run:
            print(f"[dry-run] remove {tenant_runtime}")
        else:
            tenant_runtime.unlink()
        actions.append("tenant_runtime_removed")

    # 5. 自治运行时：仅保留系统育成师，清空关系/任务/用户员工
    runtime = load_autonomy_runtime(workspace)
    trainer_items = [
        item for item in (runtime.get("child_members") or {}).get("items", [])
        if isinstance(item, dict) and item.get("system_managed") and str(item.get("primary_role") or "") == "talent_development"
    ]
    cleaned = normalize_autonomy_runtime({
        "tenant_id": "default",
        "enabled": runtime.get("enabled", True),
        "domain": "operations",
        "status": "idle",
        "parent_profile": runtime.get("parent_profile"),
        "child_members": {
            "selected_member_id": None,
            "items": trainer_items,
        },
        "relationship_center": {},
        "task_center": {},
        "collaboration_center": {},
        "training_review": {},
        "feedback_monitor": {"tenants": {}},
        "self_media": {"tenants": {}},
    })
    if dry_run:
        print("[dry-run] reset .admin/autonomy_runtime.json")
    else:
        save_autonomy_runtime(workspace, cleaned)
    actions.append(f"autonomy_reset:trainer_only({len(trainer_items)})")

    return {"actions": actions, "dry_run": dry_run}


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset workspace for E2E testing from step 1")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workspace", default=str(ROOT))
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    result = reset_workspace(workspace, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("\n完成 dry-run。去掉 --dry-run 执行真实清空。")
    else:
        print("\n已清空测试数据。请重启 Admin 后从「公司设置 → 添加工种」开始 E2E。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
