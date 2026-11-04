"""Capacity-aware, scenario-partitioned Git knowledge repository registry.

This module is provider-neutral metadata/control-plane logic. Gitee is the
initial provider, while each numbered shard remains an ordinary Git repo.
Remote provisioning and artifact upload are deliberately performed by the
caller after a shard reservation has been durably recorded.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


DOMAIN_CODES = {
    "mission": "A",
    "worker": "B",
    "skill": "C",
    "experience": "D",
    "strategy": "E",
    "project": "F",
}
_REPO_ID = re.compile(r"^[A-Z]-[0-9]{2,}$")


@dataclass(frozen=True)
class ShardPolicy:
    warning_ratio: float = 0.70
    stop_writes_ratio: float = 0.80
    hard_limit_ratio: float = 0.90

    def __post_init__(self) -> None:
        values = (self.warning_ratio, self.stop_writes_ratio, self.hard_limit_ratio)
        if any(not 0 < value < 1 for value in values):
            raise ValueError("capacity ratios must be between 0 and 1")
        if not self.warning_ratio < self.stop_writes_ratio < self.hard_limit_ratio:
            raise ValueError("capacity thresholds must be strictly increasing")


class KnowledgeShardRegistry:
    """Durable local registry and append-only artifact-location catalog."""

    def __init__(self, root: Path, *, policy: ShardPolicy | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "repository_registry.json"
        self.catalog_path = self.root / "artifact_catalog.jsonl"
        self.lock_path = self.root / ".knowledge_shards.lock"
        self.policy = policy or ShardPolicy()
        if not self.registry_path.exists():
            self._write_registry({"schema_version": 1, "domains": {}})

    @contextmanager
    def _locked(self) -> Iterator[None]:
        # fcntl locks coordinate independent processes on Linux/macOS runners.
        import fcntl

        with self.lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_registry(self) -> dict[str, Any]:
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"knowledge repository registry is unreadable: {exc}") from exc
        if data.get("schema_version") != 1 or not isinstance(data.get("domains"), dict):
            raise RuntimeError("unsupported or malformed knowledge repository registry")
        return data

    def _write_registry(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".repository_registry.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.registry_path)
            dir_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _domain_code(domain: str) -> str:
        if domain not in DOMAIN_CODES:
            raise ValueError(f"unsupported knowledge domain: {domain}")
        return DOMAIN_CODES[domain]

    def list_shards(self, domain: str | None = None) -> list[dict[str, Any]]:
        data = self._read_registry()
        if domain is not None:
            self._domain_code(domain)
            groups = [data["domains"].get(domain, {})]
        else:
            groups = list(data["domains"].values())
        shards = [dict(item) for group in groups for item in group.get("shards", [])]
        return sorted(shards, key=lambda item: item.get("repository_id", ""))

    def reserve_next_shard(self, domain: str, *, provider: str = "gitee") -> dict[str, Any]:
        """Reserve a monotonically numbered shard before remote repo creation."""
        code = self._domain_code(domain)
        with self._locked():
            data = self._read_registry()
            group = data["domains"].setdefault(domain, {"code": code, "shards": []})
            if group.get("code") != code:
                raise RuntimeError(f"domain code mismatch for {domain}")
            numbers = [
                int(match.group(1))
                for item in group["shards"]
                if (match := re.fullmatch(rf"{code}-([0-9]+)", str(item.get("repository_id", ""))))
            ]
            next_number = max(numbers, default=0) + 1
            shard = {
                "repository_id": f"{code}-{next_number:02d}",
                "domain": domain,
                "provider": provider,
                "status": "provisioning",
                "writable": False,
                "created_at": int(time.time()),
                "capacity_policy": {
                    "warning_ratio": self.policy.warning_ratio,
                    "stop_writes_ratio": self.policy.stop_writes_ratio,
                    "hard_limit_ratio": self.policy.hard_limit_ratio,
                },
            }
            group["shards"].append(shard)
            self._write_registry(data)
            return dict(shard)

    def activate_shard(
        self,
        repository_id: str,
        *,
        full_name: str,
        url: str,
        branch: str,
        capacity_limit_bytes: int | None = None,
        max_files: int | None = None,
    ) -> dict[str, Any]:
        if not _REPO_ID.fullmatch(repository_id):
            raise ValueError("invalid repository shard ID")
        if not full_name.strip() or not url.strip() or not branch.strip():
            raise ValueError("full_name, url and branch are required")
        if capacity_limit_bytes is not None and capacity_limit_bytes <= 0:
            raise ValueError("capacity_limit_bytes must be positive")
        if max_files is not None and max_files <= 0:
            raise ValueError("max_files must be positive")
        with self._locked():
            data = self._read_registry()
            for group in data["domains"].values():
                for shard in group.get("shards", []):
                    if shard.get("repository_id") == repository_id:
                        if shard.get("status") not in {"provisioning", "active"}:
                            raise RuntimeError(f"cannot activate shard in state {shard.get('status')}")
                        shard.update({
                            "full_name": full_name,
                            "url": url,
                            "branch": branch,
                            "capacity_limit_bytes": capacity_limit_bytes,
                            "max_files": max_files,
                            "status": "active",
                            "writable": True,
                            "activated_at": int(time.time()),
                        })
                        self._write_registry(data)
                        return dict(shard)
            raise KeyError(f"unknown repository shard: {repository_id}")

    def update_usage(
        self,
        repository_id: str,
        *,
        used_bytes: int,
        file_count: int,
        largest_file_bytes: int = 0,
    ) -> dict[str, Any]:
        if min(used_bytes, file_count, largest_file_bytes) < 0:
            raise ValueError("usage metrics cannot be negative")
        with self._locked():
            data = self._read_registry()
            for group in data["domains"].values():
                for shard in group.get("shards", []):
                    if shard.get("repository_id") != repository_id:
                        continue
                    shard["usage"] = {
                        "used_bytes": used_bytes,
                        "file_count": file_count,
                        "largest_file_bytes": largest_file_bytes,
                        "measured_at": int(time.time()),
                    }
                    limits = []
                    if shard.get("capacity_limit_bytes"):
                        limits.append(used_bytes / shard["capacity_limit_bytes"])
                    if shard.get("max_files"):
                        limits.append(file_count / shard["max_files"])
                    ratio = max(limits, default=0.0)
                    shard["capacity_ratio"] = round(ratio, 6)
                    if ratio >= self.policy.stop_writes_ratio:
                        shard["status"] = "sealed"
                        shard["writable"] = False
                    elif shard.get("status") == "active":
                        shard["writable"] = True
                    shard["capacity_warning"] = ratio >= self.policy.warning_ratio
                    self._write_registry(data)
                    return dict(shard)
            raise KeyError(f"unknown repository shard: {repository_id}")

    def select_writable_shard(self, domain: str) -> dict[str, Any] | None:
        self._domain_code(domain)
        shards = self.list_shards(domain)
        active = [
            item for item in shards
            if item.get("status") == "active" and item.get("writable") is True
        ]
        return active[-1] if active else None

    def record_artifact(
        self,
        *,
        artifact_id: str,
        tenant_id: str,
        domain: str,
        repository_id: str,
        path: str,
        artifact_type: str,
        version: int,
        content: bytes,
    ) -> dict[str, Any]:
        """Record a verified artifact location; retries are idempotent."""
        self._domain_code(domain)
        if not artifact_id.strip() or not tenant_id.strip() or not path.strip():
            raise ValueError("artifact_id, tenant_id and path are required")
        if version < 1:
            raise ValueError("version must be >= 1")
        shard = next(
            (item for item in self.list_shards(domain) if item.get("repository_id") == repository_id),
            None,
        )
        if shard is None or shard.get("status") not in {"active", "sealed"}:
            raise ValueError("artifact target must be a registered active or sealed shard")
        record = {
            "artifact_id": artifact_id,
            "tenant_id": tenant_id,
            "domain": domain,
            "repository_id": repository_id,
            "provider": shard["provider"],
            "full_name": shard.get("full_name"),
            "branch": shard.get("branch"),
            "path": path,
            "artifact_type": artifact_type,
            "version": version,
            "sha256": hashlib.sha256(content).hexdigest(),
            "recorded_at": int(time.time()),
        }
        with self._locked():
            existing = self._find_artifact_unlocked(artifact_id)
            if existing:
                comparable = {key: existing.get(key) for key in record if key != "recorded_at"}
                expected = {key: value for key, value in record.items() if key != "recorded_at"}
                if comparable != expected:
                    raise RuntimeError(f"artifact_id already points to different content: {artifact_id}")
                return existing
            with self.catalog_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        return record

    def _find_artifact_unlocked(self, artifact_id: str) -> dict[str, Any] | None:
        if not self.catalog_path.is_file():
            return None
        with self.catalog_path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError("artifact catalog contains a corrupt record") from exc
                if item.get("artifact_id") == artifact_id:
                    return item
        return None

    def find_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        with self._locked():
            return self._find_artifact_unlocked(artifact_id)


__all__ = ["DOMAIN_CODES", "ShardPolicy", "KnowledgeShardRegistry"]
