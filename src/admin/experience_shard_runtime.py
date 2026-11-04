"""Verified artifact writes into numbered experience knowledge shards."""
from __future__ import annotations

import hashlib
import json
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

    # Persist a rebuildable artifact manifest in the same Gitee shard before
    # updating the local catalog. This keeps the remote repository self-describing
    # if the local registry/catalog is lost.
    artifact_descriptors: list[dict[str, Any]] = []
    remote_manifests: list[str] = []
    for relative, content in files.items():
        content_bytes = content.encode("utf-8")
        digest = hashlib.sha256(content_bytes).hexdigest()
        artifact_id = f"{normalized_tenant}:{remote_paths[relative]}:{digest}"
        descriptor = {
            "schema_version": 1,
            "artifact_id": artifact_id,
            "tenant_id": normalized_tenant,
            "domain": "experience",
            "repository_id": shard["repository_id"],
            "provider": shard["provider"],
            "full_name": repo_full_name,
            "branch": branch,
            "path": remote_paths[relative],
            "artifact_type": "work_node_archive",
            "version": 1,
            "sha256": digest,
        }
        manifest_path = f".evo/catalog/experience/{hashlib.sha256(artifact_id.encode('utf-8')).hexdigest()}.json"
        manifest_content = json.dumps(
            descriptor, ensure_ascii=False, sort_keys=True, indent=2
        )
        await provider.upsert_text_file(
            token=token,
            repo_full_name=repo_full_name,
            file_path=manifest_path,
            content=manifest_content,
            message=f"{message} (artifact catalog)",
            branch=branch,
        )
        actual_manifest = await read_text_file(
            token=token,
            repo_full_name=repo_full_name,
            file_path=manifest_path,
            branch=branch,
        )
        if actual_manifest != manifest_content:
            raise RuntimeError(f"remote artifact manifest verification failed: {manifest_path}")
        remote_manifests.append(manifest_path)
        artifact_descriptors.append((descriptor, content_bytes))

    artifacts: list[dict[str, Any]] = []
    for descriptor, content_bytes in artifact_descriptors:
        artifacts.append(registry.record_artifact(
            artifact_id=descriptor["artifact_id"],
            tenant_id=normalized_tenant,
            domain="experience",
            repository_id=str(shard["repository_id"]),
            path=descriptor["path"],
            artifact_type=descriptor["artifact_type"],
            version=descriptor["version"],
            content=content_bytes,
        ))

    return {
        "repository_id": shard["repository_id"],
        "target_repo": repo_full_name,
        "target_url": shard.get("url"),
        "branch": branch,
        "files": list(remote_paths.values()),
        "verified_files": verified,
        "remote_catalog_manifests": remote_manifests,
        "artifacts": artifacts,
        "integrity_verified": len(verified) == len(files) and len(remote_manifests) == len(files) and len(artifacts) == len(files),
    }



async def rebuild_experience_artifact_catalog(
    *,
    registry: KnowledgeShardRegistry,
    provider: Any,
    token: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Rebuild missing local experience entries from verified remote manifests."""
    normalized_tenant = str(tenant_id or "").strip()
    if not normalized_tenant or normalized_tenant in {".", ".."} or "/" in normalized_tenant or "\\" in normalized_tenant:
        raise ValueError("invalid tenant_id")
    list_directory = getattr(provider, "list_directory", None)
    read_text_file = getattr(provider, "read_text_file", None)
    if not callable(list_directory) or not callable(read_text_file):
        raise RuntimeError("Git provider must support list_directory and read_text_file")

    restored: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    inspected = 0
    for shard in registry.list_shards("experience"):
        if shard.get("status") not in {"active", "sealed"}:
            continue
        full_name = str(shard.get("full_name") or "")
        branch = str(shard.get("branch") or "master")
        if not full_name:
            skipped.append({"repository_id": str(shard.get("repository_id")), "reason": "missing_full_name"})
            continue

        pending = [".evo/catalog/experience"]
        manifest_paths: list[str] = []
        while pending:
            directory = pending.pop()
            entries = await list_directory(
                token=token, repo_full_name=full_name, path=directory, branch=branch
            )
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                path = str(entry.get("path") or "")
                kind = str(entry.get("type") or entry.get("type_name") or "").lower()
                if not path.startswith(".evo/catalog/experience/"):
                    continue
                if kind in {"dir", "tree"}:
                    pending.append(path)
                elif kind in {"file", "blob"} and path.endswith(".json"):
                    manifest_paths.append(path)

        for manifest_path in sorted(manifest_paths):
            inspected += 1
            raw = await read_text_file(
                token=token, repo_full_name=full_name, file_path=manifest_path, branch=branch
            )
            if raw is None:
                skipped.append({"path": manifest_path, "reason": "manifest_missing"})
                continue
            try:
                descriptor = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                skipped.append({"path": manifest_path, "reason": "manifest_invalid_json"})
                continue

            if (
                descriptor.get("schema_version") != 1
                or descriptor.get("tenant_id") != normalized_tenant
                or descriptor.get("domain") != "experience"
                or descriptor.get("repository_id") != shard.get("repository_id")
                or descriptor.get("provider") != shard.get("provider")
                or descriptor.get("full_name") != full_name
                or descriptor.get("branch") != branch
            ):
                skipped.append({"path": manifest_path, "reason": "manifest_identity_mismatch"})
                continue

            artifact_path = str(descriptor.get("path") or "")
            if not artifact_path or artifact_path.startswith("/") or ".." in Path(artifact_path).parts:
                skipped.append({"path": manifest_path, "reason": "artifact_path_invalid"})
                continue
            artifact_content = await read_text_file(
                token=token, repo_full_name=full_name, file_path=artifact_path, branch=branch
            )
            if artifact_content is None:
                skipped.append({"path": manifest_path, "reason": "artifact_missing"})
                continue
            content_bytes = artifact_content.encode("utf-8")
            actual_digest = hashlib.sha256(content_bytes).hexdigest()
            if actual_digest != descriptor.get("sha256"):
                skipped.append({"path": manifest_path, "reason": "artifact_digest_mismatch"})
                continue
            artifact_id = str(descriptor.get("artifact_id") or "")
            if artifact_id != f"{normalized_tenant}:{artifact_path}:{actual_digest}":
                skipped.append({"path": manifest_path, "reason": "artifact_id_mismatch"})
                continue

            restored.append(registry.record_artifact(
                artifact_id=artifact_id,
                tenant_id=normalized_tenant,
                domain="experience",
                repository_id=str(shard["repository_id"]),
                path=artifact_path,
                artifact_type=str(descriptor.get("artifact_type") or "work_node_archive"),
                version=int(descriptor.get("version") or 1),
                content=content_bytes,
            ))

    return {
        "tenant_id": normalized_tenant,
        "inspected_manifests": inspected,
        "restored_artifacts": len(restored),
        "artifacts": restored,
        "skipped": skipped,
        "integrity_verified": inspected > 0 and not skipped and len(restored) == inspected and all(item.get("sha256") for item in restored),
    }


__all__ = ["archive_verified_experience_files", "rebuild_experience_artifact_catalog"]
