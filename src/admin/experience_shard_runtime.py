"""Verified artifact writes into numbered experience knowledge shards."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from admin.knowledge_shard_runtime import ensure_writable_knowledge_shard
from core.knowledge_shards import KnowledgeShardRegistry


async def archive_verified_experience_files(
    *,
    workspace: Path,
    tenant_id: str,
    provider: Any,
    token: str,
    namespace: str | None,
    repository_name_prefix: str,
    artifact_prefix: str,
    files: dict[str, str],
    message: str,
) -> dict[str, Any]:
    """Write an immutable archive batch, read every file back, then catalog it.

    The artifact catalog is updated only after the entire batch has passed
    remote content verification. Artifact IDs include the content digest so a
    changed snapshot creates a new immutable catalog entry rather than
    conflicting with an earlier version.
    """
    normalized_tenant = str(tenant_id or "default").strip()
    if not normalized_tenant or normalized_tenant in {".", ".."} or "/" in normalized_tenant or "\\" in normalized_tenant:
        raise ValueError("invalid tenant_id")
    tenant_root = (Path(workspace) / ".tenants" / normalized_tenant).resolve()
    tenants_root = (Path(workspace) / ".tenants").resolve()
    if tenant_root.parent != tenants_root:
        raise ValueError("invalid tenant_id")

    if not files:
        raise ValueError("experience archive must contain at least one file")
    for relative in files:
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts or not relative_path.parts or relative_path.as_posix() != relative:
            raise ValueError(f"invalid experience archive path: {relative}")

    registry = KnowledgeShardRegistry(tenant_root / "knowledge_shards")
    shard = await ensure_writable_knowledge_shard(
        registry,
        provider,
        token=token,
        namespace=str(namespace or "").strip(),
        repository_name_prefix=repository_name_prefix,
        domain="experience",
        private=True,
    )
    repo_full_name = str(shard["full_name"])
    branch = str(shard.get("branch") or "master")
    remote_paths = {relative: f"{artifact_prefix.rstrip('/')}/{relative}" for relative in files}

    for relative, content in files.items():
        await provider.upsert_text_file(
            token=token,
            repo_full_name=repo_full_name,
            file_path=remote_paths[relative],
            content=content,
            message=message,
            branch=branch,
        )

    read_text_file = getattr(provider, "read_text_file", None)
    if not callable(read_text_file):
        raise RuntimeError("Git provider does not support remote archive verification")

    verified: list[str] = []
    for relative, expected in files.items():
        path = remote_paths[relative]
        actual = await read_text_file(
            token=token,
            repo_full_name=repo_full_name,
            file_path=path,
            branch=branch,
        )
        if actual is None or actual != expected:
            raise RuntimeError(f"remote archive verification failed: {path}")
        verified.append(path)

    artifacts: list[dict[str, Any]] = []
    for relative, content in files.items():
        content_bytes = content.encode("utf-8")
        digest = hashlib.sha256(content_bytes).hexdigest()
        artifact_id = f"{normalized_tenant}:{remote_paths[relative]}:{digest}"
        artifacts.append(registry.record_artifact(
            artifact_id=artifact_id,
            tenant_id=normalized_tenant,
            domain="experience",
            repository_id=str(shard["repository_id"]),
            path=remote_paths[relative],
            artifact_type="work_node_archive",
            version=1,
            content=content_bytes,
        ))

    return {
        "repository_id": shard["repository_id"],
        "target_repo": repo_full_name,
        "target_url": shard.get("url"),
        "branch": branch,
        "files": list(remote_paths.values()),
        "verified_files": verified,
        "artifacts": artifacts,
        "integrity_verified": len(verified) == len(files) and len(artifacts) == len(files),
    }


__all__ = ["archive_verified_experience_files"]
