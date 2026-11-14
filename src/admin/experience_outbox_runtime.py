"""Retryable synchronization of the ExperienceStore durable outbox to Gitee shards."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from admin.experience_shard_runtime import archive_verified_experience_files


async def sync_experience_outbox(
    *,
    workspace: Path,
    tenant_id: str,
    provider: Any,
    token: str,
    namespace: str | None,
    repository_name_prefix: str,
    limit: int = 100,
) -> dict[str, Any]:
    """Archive pending experience events, verify remote readback, then mark delivered.

    Pending records are immutable and content-addressed. If the process stops
    after the remote commit but before the local move to delivered, the next run
    safely retries the same remote paths and manifests.
    """
    tenant = str(tenant_id or "").strip()
    if not tenant or tenant in {".", ".."} or "/" in tenant or chr(92) in tenant:
        raise ValueError("invalid tenant_id")
    if limit < 1:
        raise ValueError("limit must be positive")

    tenant_root = (Path(workspace) / ".tenants" / tenant).resolve()
    tenants_root = (Path(workspace) / ".tenants").resolve()
    if tenant_root.parent != tenants_root:
        raise ValueError("invalid tenant_id")

    pending_dir = tenant_root / "experience_outbox" / "pending"
    delivered_dir = tenant_root / "experience_outbox" / "delivered"
    pending_dir.mkdir(parents=True, exist_ok=True)
    delivered_dir.mkdir(parents=True, exist_ok=True)
    lock_path = tenant_root / "experience_outbox" / ".sync.lock"

    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            records: list[tuple[Path, dict[str, Any]]] = []
            skipped: list[dict[str, str]] = []
            for record_path in sorted(pending_dir.glob("*.json"))[:limit]:
                try:
                    record = json.loads(record_path.read_text(encoding="utf-8"))
                    if (
                        record.get("schema_version") != 1
                        or record.get("tenant_id") != tenant
                        or not isinstance(record.get("content"), str)
                    ):
                        raise ValueError("outbox_record_invalid")
                    content = record["content"]
                    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    if digest != record.get("sha256"):
                        raise ValueError("outbox_digest_mismatch")
                    domain = str(record.get("domain") or "")
                    experience_id = str(record.get("experience_id") or "")
                    expected_id = f"{tenant}:{domain}/{experience_id}:{digest}"
                    if record.get("artifact_id") != expected_id:
                        raise ValueError("outbox_artifact_id_mismatch")
                    relative_path = str(record.get("relative_path") or "")
                    relative = Path(relative_path)
                    if (
                        not relative_path
                        or relative.is_absolute()
                        or ".." in relative.parts
                        or relative.as_posix() != relative_path
                        or chr(92) in relative_path
                    ):
                        raise ValueError("outbox_path_invalid")
                    records.append((record_path, record))
                except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    skipped.append({"file": record_path.name, "reason": str(exc)})
            if not records:
                return {
                    "tenant_id": tenant,
                    "pending": len(list(pending_dir.glob("*.json"))),
                    "synced": 0,
                    "skipped": skipped,
                    "integrity_verified": not skipped,
                }

            files = {record["relative_path"]: record["content"] for _, record in records}
            if len(files) != len(records):
                raise RuntimeError("duplicate experience outbox artifact paths")
            result = await archive_verified_experience_files(
                workspace=Path(workspace),
                tenant_id=tenant,
                provider=provider,
                token=token,
                namespace=namespace,
                repository_name_prefix=repository_name_prefix,
                artifact_prefix=f"tenants/{tenant}/experiences",
                files=files,
                message=f"Sync {len(files)} experience outbox records for tenant {tenant}",
            )
            if not result.get("integrity_verified"):
                raise RuntimeError("remote experience archive did not pass integrity verification")

            moved = 0
            for record_path, _record in records:
                os.replace(record_path, delivered_dir / record_path.name)
                moved += 1
            return {
                "tenant_id": tenant,
                "repository_id": result["repository_id"],
                "target_repo": result["target_repo"],
                "synced": moved,
                "pending": len(list(pending_dir.glob("*.json"))),
                "skipped": skipped,
                "integrity_verified": not skipped and moved == len(records) and result.get("integrity_verified") is True,
            }
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


__all__ = ["sync_experience_outbox"]
