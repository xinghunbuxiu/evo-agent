from pathlib import Path
from types import SimpleNamespace

import pytest

from admin.experience_shard_runtime import archive_verified_experience_files


class FakeProvider:
    provider_name = "gitee"

    def __init__(self):
        self.repos = {}
        self.files = {}
        self.created = []

    async def ensure_repo(self, *, token, name, description, private, auto_init, namespace):
        self.created.append(name)
        full_name = f"{namespace}/{name}" if namespace else name
        self.repos[full_name] = SimpleNamespace(
            full_name=full_name,
            html_url=f"https://gitee.com/{full_name}",
            branch="master",
        )
        return self.repos[full_name]

    async def upsert_text_file(self, *, token, repo_full_name, file_path, content, message, branch):
        self.files[(repo_full_name, branch, file_path)] = content

    async def read_text_file(self, *, token, repo_full_name, file_path, branch):
        return self.files.get((repo_full_name, branch, file_path))


@pytest.mark.asyncio
async def test_experience_archive_writes_reads_back_and_catalogs(tmp_path: Path):
    provider = FakeProvider()
    files = {"manifest.json": '{"ok":true}', "phases/review.json": '{"score":1}'}

    result = await archive_verified_experience_files(
        workspace=tmp_path,
        tenant_id="tenant-a",
        provider=provider,
        token="test-token",
        namespace="owner",
        repository_name_prefix="evo-tenant-a-experience",
        artifact_prefix="tenants/tenant-a/nodes/task-1",
        files=files,
        message="archive node",
    )

    assert result["repository_id"] == "D-01"
    assert result["target_repo"] == "owner/evo-tenant-a-experience-d-01"
    assert result["integrity_verified"] is True
    assert len(result["verified_files"]) == 2
    assert len(result["artifacts"]) == 2
    assert len(provider.created) == 1


@pytest.mark.asyncio
async def test_experience_archive_retry_is_idempotent(tmp_path: Path):
    provider = FakeProvider()
    kwargs = dict(
        workspace=tmp_path,
        tenant_id="tenant-a",
        provider=provider,
        token="test-token",
        namespace="owner",
        repository_name_prefix="evo-tenant-a-experience",
        artifact_prefix="nodes/task-1",
        files={"manifest.json": '{"ok":true}'},
        message="archive node",
    )

    first = await archive_verified_experience_files(**kwargs)
    second = await archive_verified_experience_files(**kwargs)

    assert first["artifacts"] == second["artifacts"]
    assert provider.created == ["evo-tenant-a-experience-d-01"]


@pytest.mark.asyncio
async def test_experience_archive_does_not_catalog_unverified_content(tmp_path: Path):
    provider = FakeProvider()
    original_read = provider.read_text_file

    async def corrupt_read(**kwargs):
        value = await original_read(**kwargs)
        return "tampered" if value is not None else None

    provider.read_text_file = corrupt_read
    with pytest.raises(RuntimeError, match="verification failed"):
        await archive_verified_experience_files(
            workspace=tmp_path,
            tenant_id="tenant-a",
            provider=provider,
            token="test-token",
            namespace="owner",
            repository_name_prefix="evo-tenant-a-experience",
            artifact_prefix="nodes/task-1",
            files={"manifest.json": '{"ok":true}'},
            message="archive node",
        )

    catalog = tmp_path / ".tenants" / "tenant-a" / "knowledge_shards" / "artifact_catalog.jsonl"
    assert not catalog.exists()
