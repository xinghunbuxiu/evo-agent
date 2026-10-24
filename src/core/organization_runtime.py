"""Persistent role and worker lifecycle for Evo's organization model.

Roles are durable organizational positions. Workers are disposable execution instances.
Cloning copies an approved worker profile, never its live task state or credentials.
Retirement preserves the role and only links explicitly validated knowledge assets.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
_TERMINAL_WORKER_STATES = {"retired"}


@contextmanager
def _exclusive_worker_lock(lock_path: Path):
    """Cross-platform exclusive lock for worker claims in a shared workspace."""
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_id(value: str, label: str) -> str:
    result = str(value or "").strip()
    if not _ID_PATTERN.fullmatch(result):
        raise ValueError(f"Invalid {label}: {value!r}")
    return result


class OrganizationRegistry:
    """File-backed source of truth for durable roles and worker instances."""

    def __init__(self, workspace: Path):
        self.root = Path(workspace) / ".organization"
        self.root.mkdir(parents=True, exist_ok=True)
        self.roles_path = self.root / "roles.json"
        self.workers_path = self.root / "workers.json"
        self.assets_path = self.root / "knowledge_assets.json"
        for path in (self.roles_path, self.workers_path, self.assets_path):
            if not path.exists():
                self._write(path, {})

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError(f"Registry must contain a JSON object: {path.name}")
        return value

    @staticmethod
    def _write(path: Path, value: dict[str, Any]) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def list_roles(self) -> list[dict[str, Any]]:
        return list(self._read(self.roles_path).values())

    def get_role(self, role_id: str) -> dict[str, Any] | None:
        return self._read(self.roles_path).get(_validate_id(role_id, "role_id"))

    def create_role(
        self,
        *,
        role_id: str,
        title: str,
        responsibilities: list[str],
        required_capabilities: list[str],
        standards: list[str] | None = None,
    ) -> dict[str, Any]:
        role_id = _validate_id(role_id, "role_id")
        title = str(title or "").strip()
        if not title:
            raise ValueError("Role title is required")
        roles = self._read(self.roles_path)
        if role_id in roles:
            raise ValueError(f"Role already exists: {role_id}")
        role = {
            "role_id": role_id,
            "title": title,
            "responsibilities": self._clean_strings(responsibilities),
            "required_capabilities": self._clean_strings(required_capabilities),
            "standards": self._clean_strings(standards or []),
            "knowledge_asset_ids": [],
            "status": "active",
            "created_at": _now(),
            "updated_at": _now(),
        }
        roles[role_id] = role
        self._write(self.roles_path, roles)
        return role

    def create_worker(
        self,
        *,
        worker_id: str,
        role_id: str,
        profile: dict[str, Any],
        created_from_worker_id: str | None = None,
    ) -> dict[str, Any]:
        worker_id = _validate_id(worker_id, "worker_id")
        role_id = _validate_id(role_id, "role_id")
        roles = self._read(self.roles_path)
        if role_id not in roles or roles[role_id].get("status") != "active":
            raise ValueError(f"Active role required: {role_id}")
        if not isinstance(profile, dict):
            raise ValueError("Worker profile must be an object")
        with _exclusive_worker_lock(self.root / ".workers.lock"):
            roles = self._read(self.roles_path)
            if role_id not in roles or roles[role_id].get("status") != "active":
                raise ValueError(f"Active role required: {role_id}")
            workers = self._read(self.workers_path)
            if worker_id in workers:
                raise ValueError(f"Worker already exists: {worker_id}")
            worker = {
                "worker_id": worker_id,
                "role_id": role_id,
                "profile": self._clone_safe_profile(profile),
                "status": "available",
                "created_from_worker_id": created_from_worker_id,
                "active_task_ids": [],
                "released_task_ids": [],
                "knowledge_asset_ids": [],
                "created_at": _now(),
                "updated_at": _now(),
            }
            workers[worker_id] = worker
            self._write(self.workers_path, workers)
            return worker

    def clone_worker(self, *, source_worker_id: str, new_worker_id: str) -> dict[str, Any]:
        source_worker_id = _validate_id(source_worker_id, "source_worker_id")
        new_worker_id = _validate_id(new_worker_id, "new_worker_id")
        with _exclusive_worker_lock(self.root / ".workers.lock"):
            workers = self._read(self.workers_path)
            source = workers.get(source_worker_id)
            if source is None:
                raise KeyError(f"Worker not found: {source_worker_id}")
            if source.get("status") in _TERMINAL_WORKER_STATES:
                raise ValueError("Cannot clone a retired worker")
            roles = self._read(self.roles_path)
            role_id = str(source.get("role_id") or "")
            if role_id not in roles or roles[role_id].get("status") != "active":
                raise ValueError(f"Active role required: {role_id}")
            if new_worker_id in workers:
                raise ValueError(f"Worker already exists: {new_worker_id}")
            clone = {
                "worker_id": new_worker_id,
                "role_id": role_id,
                "profile": self._clone_safe_profile(source.get("profile", {})),
                "status": "available",
                "created_from_worker_id": source_worker_id,
                "active_task_ids": [],
                "released_task_ids": [],
                "knowledge_asset_ids": [],
                "created_at": _now(),
                "updated_at": _now(),
            }
            workers[new_worker_id] = clone
            self._write(self.workers_path, workers)
            return clone

    def get_worker(self, worker_id: str) -> dict[str, Any] | None:
        return self._read(self.workers_path).get(_validate_id(worker_id, "worker_id"))

    def list_workers(self, *, role_id: str | None = None, include_retired: bool = False) -> list[dict[str, Any]]:
        workers = list(self._read(self.workers_path).values())
        if role_id is not None:
            role_id = _validate_id(role_id, "role_id")
            workers = [worker for worker in workers if worker.get("role_id") == role_id]
        if not include_retired:
            workers = [worker for worker in workers if worker.get("status") not in _TERMINAL_WORKER_STATES]
        return workers

    def set_worker_status(self, *, worker_id: str, status: str, active_task_ids: list[str] | None = None) -> dict[str, Any]:
        worker_id = _validate_id(worker_id, "worker_id")
        allowed = {"available", "busy", "offline", "retired"}
        if status not in allowed:
            raise ValueError(f"Unsupported worker status: {status}")
        task_ids = self._clean_strings(active_task_ids or [])
        with _exclusive_worker_lock(self.root / ".workers.lock"):
            workers = self._read(self.workers_path)
            worker = workers.get(worker_id)
            if worker is None:
                raise KeyError(f"Worker not found: {worker_id}")
            if worker.get("status") == "retired" and status != "retired":
                raise ValueError("Retired worker cannot be reactivated")
            current_tasks = list(worker.get("active_task_ids", []))
            if current_tasks and task_ids != current_tasks:
                raise ValueError("Active tasks must be released individually before status changes")
            if status == "retired" and task_ids:
                raise ValueError("Worker with active tasks cannot be retired")
            if status == "available" and task_ids:
                raise ValueError("Available worker cannot retain active tasks")
            if status == "busy" and not task_ids:
                raise ValueError("Busy worker must have at least one active task")
            worker["status"] = status
            worker["active_task_ids"] = task_ids
            worker.setdefault("released_task_ids", [])
            worker["updated_at"] = _now()
            self._write(self.workers_path, workers)
            return worker

    def retire_worker(
        self,
        *,
        worker_id: str,
        validated_knowledge_asset_ids: list[str],
    ) -> dict[str, Any]:
        worker_id = _validate_id(worker_id, "worker_id")
        assets = self._read(self.assets_path)
        asset_ids = self._clean_strings(validated_knowledge_asset_ids)
        missing = [asset_id for asset_id in asset_ids if asset_id not in assets]
        if missing:
            raise ValueError(f"Knowledge assets must already exist and be validated: {missing}")
        invalid = [
            asset_id for asset_id in asset_ids
            if assets[asset_id].get("status") not in {"validated", "standard"}
        ]
        if invalid:
            raise ValueError(f"Knowledge assets are not validated: {invalid}")

        with _exclusive_worker_lock(self.root / ".workers.lock"):
            workers = self._read(self.workers_path)
            worker = workers.get(worker_id)
            if worker is None:
                raise KeyError(f"Worker not found: {worker_id}")
            if worker.get("active_task_ids"):
                raise ValueError("Cannot retire a worker with active tasks")
            if worker.get("status") == "retired":
                raise ValueError("Worker is already retired")
            worker["status"] = "retired"
            worker["knowledge_asset_ids"] = sorted(set(worker.get("knowledge_asset_ids", []) + asset_ids))
            worker["retired_at"] = _now()
            worker["updated_at"] = _now()
            workers[worker_id] = worker
            self._write(self.workers_path, workers)

            roles = self._read(self.roles_path)
            role = roles[worker["role_id"]]
            role["knowledge_asset_ids"] = sorted(set(role.get("knowledge_asset_ids", []) + asset_ids))
            role["updated_at"] = _now()
            self._write(self.roles_path, roles)
            return worker

    def register_knowledge_asset(
        self,
        *,
        asset_id: str,
        role_id: str,
        title: str,
        asset_type: str,
        status: str,
        evidence_refs: list[str],
        content_ref: str,
    ) -> dict[str, Any]:
        asset_id = _validate_id(asset_id, "asset_id")
        role_id = _validate_id(role_id, "role_id")
        if self.get_role(role_id) is None:
            raise KeyError(f"Role not found: {role_id}")
        if status not in {"candidate", "rejected", "deprecated"}:
            raise ValueError("New knowledge assets must be candidate/rejected/deprecated; use validation and promotion APIs")
        if not str(title or "").strip() or not str(content_ref or "").strip():
            raise ValueError("Knowledge asset title and content_ref are required")
        assets = self._read(self.assets_path)
        if asset_id in assets:
            raise ValueError(f"Knowledge asset already exists: {asset_id}")
        evidence = self._clean_strings(evidence_refs)

        asset = {
            "asset_id": asset_id,
            "role_id": role_id,
            "title": str(title).strip(),
            "asset_type": str(asset_type or "experience").strip(),
            "status": status,
            "evidence_refs": evidence,
            "content_ref": str(content_ref).strip(),
            "created_at": _now(),
            "updated_at": _now(),
        }
        assets[asset_id] = asset
        self._write(self.assets_path, assets)
        return asset

    def validate_knowledge_asset(
        self,
        *,
        asset_id: str,
        evidence_refs: list[str],
    ) -> dict[str, Any]:
        """Promote a candidate only when explicit, reviewable evidence references are supplied."""
        asset_id = _validate_id(asset_id, "asset_id")
        evidence = self._clean_strings(evidence_refs)
        if not evidence:
            raise ValueError("Knowledge asset validation requires evidence_refs")
        assets = self._read(self.assets_path)
        asset = assets.get(asset_id)
        if asset is None:
            raise KeyError(f"Knowledge asset not found: {asset_id}")
        if asset.get("status") != "candidate":
            raise ValueError("Only candidate knowledge assets can be validated")
        asset["status"] = "validated"
        asset["evidence_refs"] = list(dict.fromkeys(asset.get("evidence_refs", []) + evidence))
        asset["validated_at"] = _now()
        asset["updated_at"] = _now()
        assets[asset_id] = asset
        self._write(self.assets_path, assets)
        return asset

    def promote_knowledge_asset_to_standard(
        self,
        *,
        asset_id: str,
        approval_ref: str,
    ) -> dict[str, Any]:
        """Promote a validated asset to an organizational standard with an approval reference."""
        asset_id = _validate_id(asset_id, "asset_id")
        approval_ref = str(approval_ref or "").strip()
        if not approval_ref:
            raise ValueError("Standard promotion requires approval_ref")
        assets = self._read(self.assets_path)
        asset = assets.get(asset_id)
        if asset is None:
            raise KeyError(f"Knowledge asset not found: {asset_id}")
        if asset.get("status") != "validated":
            raise ValueError("Only validated knowledge assets can become standard")
        asset["status"] = "standard"
        asset["evidence_refs"] = list(dict.fromkeys(asset.get("evidence_refs", []) + [approval_ref]))
        asset["standard_approved_at"] = _now()
        asset["updated_at"] = _now()
        assets[asset_id] = asset
        self._write(self.assets_path, assets)
        return asset

    def claim_worker_task(self, *, worker_id: str, task_id: str) -> dict[str, Any]:
        """Atomically reserve an available worker for one task.

        The lock serializes claims across processes sharing this workspace. A claim
        fails closed if the worker is unavailable or already owns any active task.
        """
        worker_id = _validate_id(worker_id, "worker_id")
        task_id = _validate_id(task_id, "task_id")
        with _exclusive_worker_lock(self.root / ".workers.lock"):
            workers = self._read(self.workers_path)
            worker = workers.get(worker_id)
            if worker is None:
                raise KeyError(f"Worker not found: {worker_id}")
            if worker.get("status") == "retired":
                raise ValueError("Retired worker cannot claim tasks")
            active = list(worker.get("active_task_ids", []))
            if task_id in active:
                return worker
            if task_id in worker.get("released_task_ids", []):
                raise ValueError("A released task claim cannot be reopened")
            if worker.get("status") != "available" or active:
                raise ValueError(f"Worker is not available for a new task: {worker_id}")
            worker["status"] = "busy"
            worker["active_task_ids"] = [task_id]
            worker["updated_at"] = _now()
            workers[worker_id] = worker
            self._write(self.workers_path, workers)
            return worker

    def release_worker_task(self, *, worker_id: str, task_id: str) -> dict[str, Any]:
        """Release a claimed task; keep the worker busy until all its tasks are closed."""
        worker_id = _validate_id(worker_id, "worker_id")
        task_id = _validate_id(task_id, "task_id")
        with _exclusive_worker_lock(self.root / ".workers.lock"):
            workers = self._read(self.workers_path)
            worker = workers.get(worker_id)
            if worker is None:
                raise KeyError(f"Worker not found: {worker_id}")
            active = list(worker.get("active_task_ids", []))
            if task_id not in active:
                if task_id in worker.get("released_task_ids", []):
                    return worker
                raise ValueError(f"Task is not claimed by worker {worker_id}: {task_id}")
            worker["active_task_ids"] = [item for item in active if item != task_id]
            released = list(worker.get("released_task_ids", []))
            released.append(task_id)
            worker["released_task_ids"] = released[-100:]
            if worker.get("status") == "busy":
                worker["status"] = "busy" if worker["active_task_ids"] else "available"
            worker["updated_at"] = _now()
            workers[worker_id] = worker
            self._write(self.workers_path, workers)
            return worker

    @staticmethod
    def _clone_safe_profile(profile: dict[str, Any]) -> dict[str, Any]:
        """Copy reusable configuration while excluding credentials and live runtime state."""
        forbidden_exact = {
            "secret", "token", "access_token", "refresh_token", "api_token",
            "password", "credential", "credentials", "api_key", "apikey",
            "access_key", "private_key", "authorization", "cookie", "session",
            "session_id", "pid", "process_id", "runtime", "runtime_state",
        }
        forbidden_fragments = (
            "client_secret", "password", "credential", "api_key", "apikey",
            "access_key", "private_key", "authorization", "cookie",
            "active_task", "runtime_state",
        )

        def clean(value: Any) -> Any:
            if isinstance(value, dict):
                result: dict[str, Any] = {}
                for key, item in value.items():
                    normalized_key = str(key).strip().lower().replace("-", "_")
                    if normalized_key in forbidden_exact or any(
                        fragment in normalized_key for fragment in forbidden_fragments
                    ):
                        continue
                    result[str(key)] = clean(item)
                return result
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, tuple):
                return [clean(item) for item in value]
            return value

        return clean(profile)

    @staticmethod
    def _clean_strings(values: list[str]) -> list[str]:
        if not isinstance(values, list):
            raise ValueError("Expected a list of strings")
        result = []
        for value in values:
            item = str(value or "").strip()
            if item and item not in result:
                result.append(item)
        return result



def sync_worker_catalog(
    registry: OrganizationRegistry,
    manifests: dict[str, dict[str, Any]],
    enabled_worker_ids: set[str],
) -> dict[str, int]:
    """Seed durable role definitions and enabled built-in worker instances.

    Existing user-authored roles, workers, and knowledge links are never overwritten.
    A worker is only seeded when a concrete runtime handler is enabled.
    """
    roles_created = 0
    workers_created = 0
    for raw_worker_id, manifest in sorted(manifests.items()):
        worker_id = _validate_id(raw_worker_id, "worker_id")
        if not isinstance(manifest, dict):
            continue
        capability_type = str(manifest.get("capability_type") or "").strip()
        if not capability_type:
            continue
        role = registry.get_role(worker_id)
        if role is None:
            registry.create_role(
                role_id=worker_id,
                title=str(manifest.get("title") or worker_id),
                responsibilities=(
                    manifest.get("owned_modules")
                    if isinstance(manifest.get("owned_modules"), list)
                    else manifest.get("task_types", [])
                ),
                required_capabilities=[capability_type],
                standards=["runtime-handler-required", "validated-knowledge-only"],
            )
            roles_created += 1

        if worker_id not in enabled_worker_ids:
            continue
        existing = registry.get_worker(worker_id)
        if existing is not None:
            continue
        registry.create_worker(
            worker_id=worker_id,
            role_id=worker_id,
            profile={
                "handler_id": worker_id,
                "capability_type": capability_type,
                "task_types": manifest.get("task_types", []),
                "work_type_ids": manifest.get("work_type_ids", []),
                "enabled": True,
                "source": "worker_manifest",
            },
        )
        workers_created += 1
    return {"roles_created": roles_created, "workers_created": workers_created}


def recommend_workforce_for_node(
    node: dict[str, Any],
    registry: OrganizationRegistry | None,
    *,
    reserved_worker_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Return an auditable workforce recommendation; never creates or dispatches workers."""
    parallel_safe = node.get("parallel_safe") is True
    node_id = str(node.get("id") or "").strip() or None
    required = node.get("required_capabilities")
    if not isinstance(required, list) or not required:
        capability_type = str(node.get("capability_type") or "").strip()
        required = [capability_type] if capability_type else []
    required = list(dict.fromkeys(str(item).strip() for item in required if str(item).strip()))
    base = {
        "node_id": node_id,
        "required_capabilities": required,
        "parallel_safe": parallel_safe,
        "dispatch_authorized": False,
        "dispatch_state": "recommendation_only",
        "recommended_role_id": None,
        "recommended_worker_id": None,
        "recommended_source_worker_id": None,
    }

    if str(node.get("status") or "") == "needs_input":
        return {**base, "decision": "blocked_missing_input", "reason": "任务输入未齐，暂不推荐执行员工。"}
    if registry is None:
        return {
            **base,
            "decision": "catalog_unavailable",
            "reason": "岗位/员工目录尚未初始化，不能据此声称已匹配员工。",
        }
    if not required:
        return {**base, "decision": "insufficient_capability_requirements", "reason": "节点没有明确能力要求。"}

    normalized_required = {item.casefold() for item in required}
    matching_roles = []
    for role in registry.list_roles():
        if role.get("status") != "active":
            continue
        role_caps = {
            str(item).strip().casefold()
            for item in role.get("required_capabilities", [])
            if str(item).strip()
        }
        if normalized_required.issubset(role_caps):
            matching_roles.append((len(role_caps - normalized_required), str(role.get("role_id") or ""), role))
    matching_roles.sort(key=lambda item: (item[0], item[1]))

    if not matching_roles:
        return {
            **base,
            "decision": "create_role_and_worker_recommended",
            "reason": "现有活动岗位没有覆盖节点所需的全部能力；仅提出岗位/员工创建建议，不自动创建。",
        }

    reserved = reserved_worker_ids or set()
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    busy: list[dict[str, Any]] = []
    offline: list[dict[str, Any]] = []
    for _, _, role in matching_roles:
        for worker in registry.list_workers(role_id=role["role_id"]):
            status = worker.get("status")
            if status == "available" and worker.get("worker_id") not in reserved:
                candidates.append((len(worker.get("active_task_ids", [])), str(worker.get("worker_id") or ""), worker))
            elif status == "busy" or worker.get("worker_id") in reserved:
                busy.append(worker)
            elif status == "offline":
                offline.append(worker)

    if candidates:
        _, _, worker = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
        return {
            **base,
            "decision": "assign_existing_worker_recommended",
            "recommended_role_id": worker.get("role_id"),
            "recommended_worker_id": worker.get("worker_id"),
            "reason": "找到能力要求匹配且未被本计划其他节点预留的可用员工；实际派发仍需运行时执行。",
        }

    if busy and parallel_safe:
        source = sorted(
            busy,
            key=lambda worker: (len(worker.get("active_task_ids", [])), str(worker.get("worker_id") or "")),
        )[0]
        return {
            **base,
            "decision": "clone_worker_recommended",
            "recommended_role_id": source.get("role_id"),
            "recommended_source_worker_id": source.get("worker_id"),
            "reason": "匹配员工繁忙且节点明确标记可安全并行；仅建议复制配置，未实际创建克隆。",
        }

    if busy:
        return {
            **base,
            "decision": "wait_for_worker_recommended",
            "recommended_role_id": busy[0].get("role_id"),
            "reason": "匹配员工繁忙或已被本计划其他节点预留，但节点未明确允许安全并行。",
        }

    if offline:
        return {
            **base,
            "decision": "create_worker_recommended",
            "recommended_role_id": offline[0].get("role_id"),
            "reason": "匹配岗位存在，但当前没有在线可用员工；建议恢复节点或孵化新员工。",
        }

    return {
        **base,
        "decision": "create_worker_recommended",
        "recommended_role_id": matching_roles[0][2].get("role_id"),
        "reason": "岗位能力匹配，但岗位下没有可用员工实例；仅提出创建建议。",
    }


def recommend_workforce_for_nodes(
    nodes: list[dict[str, Any]],
    registry: OrganizationRegistry | None,
) -> list[dict[str, Any]]:
    """Plan conservative per-node recommendations without assigning one worker twice."""
    reserved: set[str] = set()
    decisions: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        decision = recommend_workforce_for_node(node, registry, reserved_worker_ids=reserved)
        decisions.append(decision)
        worker_id = decision.get("recommended_worker_id")
        if decision.get("decision") == "assign_existing_worker_recommended" and worker_id:
            reserved.add(str(worker_id))
    return decisions


__all__ = [
    "OrganizationRegistry",
    "recommend_workforce_for_node",
    "recommend_workforce_for_nodes",
    "sync_worker_catalog",
]
