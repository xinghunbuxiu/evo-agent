"""Tests for the Gitee-backed knowledge shard provisioning runtime."""
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.knowledge_shard_runtime import ensure_writable_knowledge_shard  # noqa: E402
from core.knowledge_shards import KnowledgeShardRegistry  # noqa: E402


class FakeProvider:
    provider_name = "gitee"

    def __init__(self):
        self.calls = []

    async def ensure_repo(self, **kwargs):
        self.calls.append(kwargs)
        name = kwargs["name"]
        return SimpleNamespace(
            full_name=f"{kwargs['namespace']}/{name}",
            html_url=f"https://gitee.com/{kwargs['namespace']}/{name}",
            branch="master",
        )


class KnowledgeShardProvisioningTests(unittest.TestCase):
    def test_provisions_deterministic_gitee_repo_and_registers_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = KnowledgeShardRegistry(Path(tmp))
            provider = FakeProvider()
            result = asyncio.run(ensure_writable_knowledge_shard(
                registry, provider,
                token="secret",
                namespace="team",
                repository_name_prefix="evo-knowledge",
                domain="mission",
                capacity_limit_bytes=100000,
                max_files=1000,
            ))

            self.assertEqual(result["repository_id"], "A-01")
            self.assertEqual(result["full_name"], "team/evo-knowledge-a-01")
            self.assertEqual(result["status"], "active")
            self.assertEqual(provider.calls[0]["private"], True)
            self.assertEqual(provider.calls[0]["namespace"], "team")

    def test_reuses_interrupted_provisioning_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = KnowledgeShardRegistry(Path(tmp))
            pending = registry.reserve_next_shard("experience")
            provider = FakeProvider()
            result = asyncio.run(ensure_writable_knowledge_shard(
                registry, provider,
                token="secret",
                namespace="team",
                repository_name_prefix="evo-memory",
                domain="experience",
            ))

            self.assertEqual(pending["repository_id"], "D-01")
            self.assertEqual(result["repository_id"], "D-01")
            self.assertEqual(len(provider.calls), 1)
            self.assertEqual(provider.calls[0]["name"], "evo-memory-d-01")
            self.assertEqual(len(registry.list_shards("experience")), 1)

    def test_existing_active_shard_is_reused_without_remote_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = KnowledgeShardRegistry(Path(tmp))
            pending = registry.reserve_next_shard("skill")
            registry.activate_shard(
                pending["repository_id"],
                full_name="team/skills-c-01",
                url="https://gitee.com/team/skills-c-01",
                branch="master",
            )
            provider = FakeProvider()
            result = asyncio.run(ensure_writable_knowledge_shard(
                registry, provider,
                token="secret",
                namespace="team",
                repository_name_prefix="evo",
                domain="skill",
            ))
            self.assertEqual(result["repository_id"], "C-01")
            self.assertEqual(provider.calls, [])

    def test_invalid_repository_prefix_does_not_create_remote_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = KnowledgeShardRegistry(Path(tmp))
            provider = FakeProvider()
            with self.assertRaisesRegex(ValueError, "repository_name_prefix"):
                asyncio.run(ensure_writable_knowledge_shard(
                    registry, provider,
                    token="secret",
                    namespace="team",
                    repository_name_prefix="---",
                    domain="project",
                ))
            self.assertEqual(provider.calls, [])
            self.assertEqual(registry.list_shards("project")[0]["status"], "provisioning")


if __name__ == "__main__":
    unittest.main()
