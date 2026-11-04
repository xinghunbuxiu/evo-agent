"""Runtime integration for provisioning numbered knowledge shards via Gitee."""
from __future__ import annotations

import re
from typing import Any

from core.knowledge_shards import KnowledgeShardRegistry


async def ensure_writable_knowledge_shard(
    registry: KnowledgeShardRegistry,
    provider: Any,
    *,
    token: str,
    namespace: str,
    repository_name_prefix: str,
    domain: str,
    private: bool = True,
    capacity_limit_bytes: int | None = None,
    max_files: int | None = None,
) -> dict[str, Any]:
    """Find the current writable shard or provision the next numbered repo.

    Provisioning reservations are persisted before calling the remote provider.
    If the process stops during repo creation, the next attempt reuses the same
    reservation and deterministic repository name instead of skipping a shard.
    """
    active = registry.select_writable_shard(domain)
    if active:
        return active

    reservation = registry.find_provisioning_shard(domain)
    if reservation is None:
        reservation = registry.reserve_next_shard(domain, provider=provider.provider_name)

    prefix = re.sub(r"[^a-zA-Z0-9_-]+", "-", repository_name_prefix.strip()).strip("-")
    if not prefix:
        raise ValueError("repository_name_prefix must contain letters or digits")

    repository_id = reservation["repository_id"]
    managed = await provider.ensure_repo(
        token=token,
        name=f"{prefix}-{repository_id.lower()}",
        description=f"Evo {domain} knowledge shard {repository_id}",
        private=private,
        auto_init=True,
        namespace=namespace or None,
    )
    return registry.activate_shard(
        repository_id,
        full_name=managed.full_name,
        url=managed.html_url,
        branch=managed.branch,
        capacity_limit_bytes=capacity_limit_bytes,
        max_files=max_files,
    )


__all__ = ["ensure_writable_knowledge_shard"]
