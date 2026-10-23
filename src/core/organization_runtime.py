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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
_TERMINAL_WORKER_STATES = {"retired"}


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
        workers = self._read(self.workers_path)
        if worker_id in workers:
            raise ValueError(f"Worker already exists: {worker_id}")
        if not isinstance(profile, dict):
            raise ValueError("Worker profile must be an object")
        worker = {
            "worker_id": worker_id,
            "role_id": role_id,
            "profile": dict(profile),
            "status": "available",
            "created_from_worker_id": created_from_worker_id,
            "active_task_ids": [],
            "knowledge_asset_ids": [],
            "created_at": _now(),
            "updated_at": _now(),
        }
        workers[worker_id] = worker
        self._write(self.workers_path, workers)
        return worker

    def clone_worker(self, *, source_worker_id: str, new_worker_id: str) -> dict[str, Any]:
        source_worker_id = _validate_id(source_worker_id, "source_worker_id")
        source = self.get_worker(source_worker_id)
        if source is None:
            raise KeyError(f"Worker not found: {source_worker_id}")
        if source.get("status") in _TERMINAL_WORKER_STATES:
            raise ValueError("Cannot clone a retired worker")
        return self.create_worker(
            worker_id=new_worker_id,
            role_id=source["role_id"],
            profile=self._clone_safe_profile(source["profile"]),
            created_from_worker_id=source_worker_id,
        )

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
        workers = self._read(self.workers_path)
        worker = workers.get(worker_id)
        if worker is None:
            raise KeyError(f"Worker not found: {worker_id}")
        if worker.get("status") == "retired" and status != "retired":
            raise ValueError("Retired worker cannot be reactivated")
        task_ids = self._clean_strings(active_task_ids or [])
        if status == "retired" and task_ids:
            raise ValueError("Worker with active tasks cannot be retired")
        worker["status"] = status
        worker["active_task_ids"] = task_ids
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

        workers = self._read(self.workers_path)
        worker = workers.get(worker_id)
        if worker is None:
            raise KeyError(f"Worker not found: {worker_id}")
        if worker.get("active_task_ids"):
            raise ValueError("Cannot retire a worker with active tasks")
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
        if status not in {"candidate", "validated", "standard", "rejected", "deprecated"}:
            raise ValueError(f"Unsupported knowledge asset status: {status}")
        if not str(title or "").strip() or not str(content_ref or "").strip():
            raise ValueError("Knowledge asset title and content_ref are required")
        assets = self._read(self.assets_path)
        if asset_id in assets:
            raise ValueError(f"Knowledge asset already exists: {asset_id}")
        evidence = self._clean_strings(evidence_refs)
        if status in {"validated", "standard"} and not evidence:
            raise ValueError("Validated knowledge assets require evidence_refs")

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

    @staticmethod
    def _clone_safe_profile(profile: dict[str, Any]) -> dict[str, Any]:
        """Copy reusable configuration while excluding credentials and live runtime state."""
        forbidden_fragments = (
            "secret", "token", "password", "credential", "api_key", "apikey",
            "access_key", "private_key", "authorization", "cookie", "session",
            "runtime", "active_task", "process_id", "pid",
        )

        def clean(value: Any) -> Any:
            if isinstance(value, dict):
                result: dict[str, Any] = {}
                for key, item in value.items():
                    normalized_key = str(key).strip().lower().replace("-", "_")
                    if any(fragment in normalized_key for fragment in forbidden_fragments):
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
]
