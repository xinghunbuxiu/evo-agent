"""
任务队列、指纹与本地技能草稿接口。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import HTTPException, Request


def register_task_tool_routes(
    app,
    *,
    workspace: Path,
    task_queue,
    task_priority_cls,
    build_task_comparison: Callable,
    record_replay_validation: Callable[[Path, str, dict], dict | None],
    success_response: Callable[[dict | None, str], dict],
    error_response: Callable[[str, int], object],
) -> None:
    @app.get("/api/tasks")
    async def list_tasks(limit: int = 100):
        tasks = task_queue.list_tasks(limit=limit)
        return [t.to_dict() for t in tasks]

    @app.post("/api/tasks")
    async def create_task(request: dict):
        task = task_queue.submit(
            task_type=request.get("type", "analyze"),
            payload=request.get("payload", {}),
            priority=task_priority_cls(request.get("priority", 2)),
            tenant_id=request.get("tenant_id", "default"),
        )
        return {"success": True, "task_id": task.id}

    @app.get("/api/tasks/{task_id}")
    async def get_task(task_id: str):
        task = task_queue.get_task(task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        return task.to_dict()

    @app.delete("/api/tasks/{task_id}")
    async def cancel_task(task_id: str):
        success = task_queue.cancel_task(task_id)
        return {"success": success}

    @app.post("/api/tasks/{task_id}/replay")
    async def replay_task(task_id: str):
        original = task_queue.get_task(task_id)
        if not original:
            raise HTTPException(404, "Task not found")

        replay_payload = dict(original.payload or {})
        replay_payload["_replay_of"] = original.id

        replay_task = task_queue.submit(
            task_type=original.type,
            payload=replay_payload,
            priority=original.priority,
            tenant_id=original.tenant_id,
        )
        return success_response({
            "task_id": replay_task.id,
            "replay_of": original.id,
            "tenant_id": replay_task.tenant_id,
        }, "任务已重新提交")

    @app.get("/api/tasks/{task_id}/compare")
    async def compare_task(task_id: str):
        current = task_queue.get_task(task_id)
        if not current:
            raise HTTPException(404, "Task not found")

        all_tasks = task_queue.list_tasks(tenant_id=current.tenant_id, limit=300)
        replay_of = (current.payload or {}).get("_replay_of")
        if replay_of:
            original = task_queue.get_task(replay_of)
            replay = current
        else:
            original = current
            replay_candidates = [
                task for task in all_tasks
                if (task.payload or {}).get("_replay_of") == current.id
            ]
            replay_candidates.sort(key=lambda item: item.created_at, reverse=True)
            replay = replay_candidates[0] if replay_candidates else None

        if not original or not replay:
            return error_response("暂无可对比的重放任务", 404)

        comparison = build_task_comparison(original, replay)
        validation = record_replay_validation(workspace, original.tenant_id, comparison)
        if validation:
            comparison["validation_record"] = validation
        return success_response(comparison)

    @app.post("/api/fingerprint/generate")
    async def generate_fingerprint(request: Request):
        data = await request.json()
        analysis_result = data.get("analysis_result")
        tenant_id = data.get("tenant_id", "default")

        if not analysis_result:
            raise HTTPException(400, "缺少 analysis_result")

        from domains.javascript.fingerprint import generate_fingerprint as gen_fp

        fingerprint = gen_fp(analysis_result)

        fp_dir = workspace / ".cache" / "fingerprints" / tenant_id
        fp_dir.mkdir(parents=True, exist_ok=True)
        fp_file = fp_dir / f"fp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(fp_file, "w", encoding="utf-8") as f:
            json.dump(fingerprint, f, indent=2, ensure_ascii=False)

        return {
            "success": True,
            "fingerprint": fingerprint,
            "saved_to": str(fp_file),
        }

    @app.get("/api/fingerprint/list")
    async def list_fingerprints(tenant_id: str = "default"):
        fp_dir = workspace / ".cache" / "fingerprints" / tenant_id
        if not fp_dir.exists():
            return {"fingerprints": []}

        fingerprints = []
        for fp_file in fp_dir.glob("*.json"):
            try:
                with open(fp_file, encoding="utf-8") as f:
                    data = json.load(f)
                fingerprints.append({
                    "name": fp_file.stem,
                    "file": str(fp_file),
                    "frameworks": list(data.get("framework_signatures", {}).keys())[:3],
                })
            except Exception:
                pass

        return {"fingerprints": fingerprints}

    @app.get("/api/skills/local")
    async def list_local_skills(tenant_id: str = "default"):
        skills_dir = workspace / ".tenants" / tenant_id / "skills" / "draft"
        if not skills_dir.exists():
            return {"skills": []}

        skills = []
        for skill_file in skills_dir.glob("*.json"):
            try:
                with open(skill_file, encoding="utf-8") as f:
                    data = json.load(f)
                skills.append({
                    "name": data.get("name", skill_file.stem),
                    "domain": data.get("domain", "unknown"),
                    "trust_level": "draft",
                    "created_at": data.get("created_at"),
                })
            except Exception:
                pass

        return {"skills": skills}
