"""
工种 / Worker 动态路由：从成员 current_jobs 与 work_types 注册表解析，禁止写死业务工种 ID。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from project_caps import build_project_package_runtime_entries
from work_type_runtime import resolve_runtime_route
from work_types import load_work_types
from workers.registry import builtin_worker_manifests, load_worker_registry_config


def resolve_work_type_id(member: dict | None, *, job: dict | None = None) -> str | None:
    if isinstance(job, dict):
        job_id = str(job.get("job_id") or "").strip()
        if job_id:
            return job_id
    if not isinstance(member, dict):
        return None
    jobs = member.get("current_jobs") if isinstance(member.get("current_jobs"), list) else []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("job_id") or "").strip()
        if job_id:
            return job_id
    role = str(member.get("primary_role") or "").strip()
    if role and role != "talent_development":
        return role
    return None


def resolve_runtime_route_for_work_type(workspace: Path, work_type_id: str | None) -> dict[str, Any]:
    return resolve_runtime_route(
        workspace,
        work_type_id=work_type_id,
        mission_kind=None,
        capability_type=None,
        load_work_types=load_work_types,
        builtin_worker_manifests=builtin_worker_manifests,
        load_worker_registry_config=load_worker_registry_config,
        build_project_package_runtime_entries=build_project_package_runtime_entries,
    )


def resolve_primary_worker_id(workspace: Path, *, member: dict | None = None, work_type_id: str | None = None) -> str | None:
    target_work_type = work_type_id or resolve_work_type_id(member)
    if not target_work_type:
        return None
    route = resolve_runtime_route_for_work_type(workspace, target_work_type)
    worker_ids = route.get("worker_ids") if isinstance(route.get("worker_ids"), list) else []
    enabled_workers = [
        worker for worker in (route.get("workers") if isinstance(route.get("workers"), list) else [])
        if isinstance(worker, dict) and worker.get("enabled")
    ]
    if enabled_workers:
        return str(enabled_workers[0].get("worker_id") or "").strip() or None
    if worker_ids:
        return str(worker_ids[0]).strip() or None
    return None


def worker_manifest(workspace: Path, worker_id: str | None) -> dict[str, Any]:
    wid = str(worker_id or "").strip()
    if not wid:
        return {}
    payload = builtin_worker_manifests(workspace).get(wid)
    return payload if isinstance(payload, dict) else {}


def worker_has_operation_tasks(workspace: Path, worker_id: str | None) -> bool:
    manifest = worker_manifest(workspace, worker_id)
    task_types = manifest.get("task_types") if isinstance(manifest.get("task_types"), list) else []
    return any(str(item).startswith("operation_") for item in task_types)


def is_automation_work_type(workspace: Path, work_type_id: str | None) -> bool:
    if not work_type_id:
        return False
    route = resolve_runtime_route_for_work_type(workspace, work_type_id)
    if str(route.get("capability_type") or "").strip() == "automation":
        return True
    workers = route.get("workers") if isinstance(route.get("workers"), list) else []
    return any(isinstance(item, dict) and item.get("capability_type") == "automation" for item in workers)


def member_uses_operation_automation(workspace: Path, member: dict | None) -> bool:
    work_type_id = resolve_work_type_id(member)
    if not work_type_id:
        return False
    worker_id = resolve_primary_worker_id(workspace, member=member, work_type_id=work_type_id)
    return bool(worker_id and worker_has_operation_tasks(workspace, worker_id))


def resolve_experience_domain(
    workspace: Path | None,
    *,
    primary_role: str | None = None,
    work_type_id: str | None = None,
) -> str:
    role = str(primary_role or "").strip()
    if role in {"talent_development", "finance"}:
        return "evolution" if role == "talent_development" else "finance"
    target = work_type_id or role
    worker_id = resolve_primary_worker_id(workspace, work_type_id=target) if isinstance(workspace, Path) else None
    manifest = worker_manifest(workspace, worker_id) if isinstance(workspace, Path) else {}
    explicit = str(manifest.get("experience_domain") or "").strip()
    if explicit:
        return explicit
    capability_type = str(manifest.get("capability_type") or "").strip()
    if capability_type.endswith("_reverse"):
        return capability_type[: -len("_reverse")]
    if worker_id:
        if worker_id.endswith("_operations"):
            return worker_id[: -len("_operations")]
        if worker_id.endswith("_reverse"):
            return worker_id[: -len("_reverse")]
        return worker_id
    if target:
        if str(target).endswith("_reverse"):
            return str(target)[: -len("_reverse")]
        return str(target)
    return "general"


def worker_autonomy_state_key(worker_id: str | None) -> str | None:
    """operation 类 worker 在 autonomy runtime 中使用的租户态 bucket（按 worker 区分）。"""
    wid = str(worker_id or "").strip()
    if not wid:
        return None
    if wid.endswith("_operations"):
        return wid[: -len("_operations")]
    return wid


def build_generic_automation_job_runtime(job: dict, *, member: dict | None = None) -> dict:
    job_id = str(job.get("job_id") or "").strip() or None
    status = str(job.get("status") or "planned").strip() or "planned"
    return {
        "job_id": job_id,
        "account_id": str(job.get("account_id") or "default").strip() or "default",
        "status": status,
        "blocked_reason": None,
        "next_action": str(job.get("target_outcome") or "等待育成师分配正式任务后启动工种执行。").strip(),
        "signals": [f"job:{job_id or 'unknown'}"],
        "tenant_state": {},
    }


def worker_supports_mission_follow_up(runtime_route: dict | None, primary_worker_id: str | None) -> bool:
    route = runtime_route if isinstance(runtime_route, dict) else {}
    wid = str(primary_worker_id or "").strip()
    workers = route.get("workers") if isinstance(route.get("workers"), list) else []
    for worker in workers:
        if not isinstance(worker, dict):
            continue
        if wid and str(worker.get("worker_id") or "").strip() != wid:
            continue
        task_types = worker.get("task_types") if isinstance(worker.get("task_types"), list) else []
        if any(str(item).startswith("operation_") for item in task_types):
            return True
    task_types = route.get("task_types") if isinstance(route.get("task_types"), list) else []
    return any(str(item).startswith("operation_") for item in task_types)


def worker_uses_self_media_tenant_bucket(worker_id: str | None) -> bool:
    """该 worker 是否使用 autonomy.runtime['self_media'].tenants 状态桶。"""
    return worker_autonomy_state_key(worker_id) == "self_media"


def resolve_autonomy_job_tag(
    workspace: Path,
    *,
    member: dict | None = None,
    work_type_id: str | None = None,
    worker_id: str | None = None,
) -> str:
    """任务 payload 中 `_autonomy_job` 标签（优先 worker_id，其次 work_type）。"""
    wid = str(worker_id or "").strip()
    if not wid:
        wid = str(resolve_primary_worker_id(workspace, member=member, work_type_id=work_type_id) or "").strip()
    if wid:
        return wid
    return str(work_type_id or resolve_work_type_id(member) or "").strip()


def build_operation_job_runtime(
    workspace: Path,
    job: dict,
    autonomy: dict,
    *,
    member: dict | None = None,
    build_self_media_job_runtime: Callable[..., dict] | None = None,
) -> dict | None:
    """按 worker 能力选择工种 job runtime 构建器。"""
    job_id = str(job.get("job_id") or "").strip()
    worker_id = resolve_primary_worker_id(workspace, member=member, work_type_id=job_id or None)
    if not worker_id or not worker_has_operation_tasks(workspace, worker_id):
        return None
    if worker_uses_self_media_tenant_bucket(worker_id) and callable(build_self_media_job_runtime):
        return build_self_media_job_runtime(job, autonomy, member=member)
    return build_generic_automation_job_runtime(job, member=member)


__all__ = [
    "build_generic_automation_job_runtime",
    "build_operation_job_runtime",
    "is_automation_work_type",
    "member_uses_operation_automation",
    "resolve_autonomy_job_tag",
    "resolve_experience_domain",
    "resolve_primary_worker_id",
    "resolve_runtime_route_for_work_type",
    "resolve_work_type_id",
    "worker_autonomy_state_key",
    "worker_has_operation_tasks",
    "worker_manifest",
    "worker_supports_mission_follow_up",
    "worker_uses_self_media_tenant_bucket",
]
