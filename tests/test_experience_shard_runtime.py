"""End-to-end unit tests for verified experience shard writes."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.experience_shard_runtime import (
    archive_verified_experience_files,
    rebuild_experience_artifact_catalog,
)  # noqa: E402
from core.knowledge_shards import KnowledgeShardRegistry
import hashlib


class FakeProvider:
    provider_name = "gitee"

    def __init__(self):
        self.repos = {}
        self.files = {}
        self.created = []

    async def ensure_repo(self, *, token, name, description, private, auto_init, namespace):
        self.created.append(name)
        full_name = f"{namespace}/{name}" if namespace else name
        repo = SimpleNamespace(
            full_name=full_name,
            html_url=f"https://gitee.com/{full_name}",
            branch="master",
        )
        self.repos[full_name] = repo
        return repo

    async def upsert_text_file(self, *, token, repo_full_name, file_path, content, message, branch):
        self.files[(repo_full_name, branch, file_path)] = content

    async def read_text_file(self, *, token, repo_full_name, file_path, branch):
        return self.files.get((repo_full_name, branch, file_path))

    async def list_directory(self, *, token, repo_full_name, path, branch):
        prefix = path.rstrip("/") + "/"
        result = []
        for (repo, file_branch, file_path), _content in self.files.items():
            if repo != repo_full_name or file_branch != branch or not file_path.startswith(prefix):
                continue
            remainder = file_path[len(prefix):]
            if "/" not in remainder:
                result.append({"type": "file", "path": file_path})
            else:
                directory = prefix + remainder.split("/", 1)[0]
                if not any(item.get("path") == directory for item in result):
                    result.append({"type": "dir", "path": directory})
        return result


class ExperienceShardArchiveTests(unittest.TestCase):
    def run_archive(self, workspace, provider, **overrides):
        args = {
            "workspace": workspace,
            "tenant_id": "tenant-a",
            "provider": provider,
            "token": "test-token",
            "namespace": "owner",
            "repository_name_prefix": "evo-tenant-a-experience",
            "artifact_prefix": "tenants/tenant-a/nodes/task-1",
            "files": {"manifest.json": '{"ok":true}', "phases/review.json": '{"score":1}'},
            "message": "archive node",
        }
        args.update(overrides)
        return asyncio.run(archive_verified_experience_files(**args))

    def test_experience_archive_writes_reads_back_and_catalogs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = FakeProvider()
            result = self.run_archive(Path(temp_dir), provider)
            self.assertEqual(result["repository_id"], "D-01")
            self.assertEqual(result["target_repo"], "owner/evo-tenant-a-experience-d-01")
            self.assertTrue(result["integrity_verified"])
            self.assertEqual(len(result["verified_files"]), 2)
            self.assertEqual(len(result["artifacts"]), 2)
            self.assertEqual(len(result["remote_catalog_manifests"]), 2)
            self.assertEqual(len(provider.created), 1)

    def test_experience_archive_retry_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = FakeProvider()
            first = self.run_archive(Path(temp_dir), provider)
            second = self.run_archive(Path(temp_dir), provider)
            self.assertEqual(first["artifacts"], second["artifacts"])
            self.assertEqual(provider.created, ["evo-tenant-a-experience-d-01"])

    def test_experience_archive_does_not_catalog_unverified_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = FakeProvider()
            original_read = provider.read_text_file

            async def corrupt_read(**kwargs):
                value = await original_read(**kwargs)
                return "tampered" if value is not None else None

            provider.read_text_file = corrupt_read
            with self.assertRaisesRegex(RuntimeError, "verification failed"):
                self.run_archive(
                    Path(temp_dir),
                    provider,
                    files={"manifest.json": '{"ok":true}'},
                )
            catalog = Path(temp_dir) / ".tenants" / "tenant-a" / "knowledge_shards" / "artifact_catalog.jsonl"
            self.assertFalse(catalog.exists())

    def test_invalid_archive_path_is_rejected_before_provisioning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = FakeProvider()
            with self.assertRaisesRegex(ValueError, "invalid experience archive path"):
                self.run_archive(
                    Path(temp_dir),
                    provider,
                    files={"../outside.json": "no"},
                )
            self.assertEqual(provider.created, [])

    def test_rebuild_catalog_from_remote_manifest_after_local_catalog_loss(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            provider = FakeProvider()
            self.run_archive(workspace, provider)
            registry_root = workspace / ".tenants" / "tenant-a" / "knowledge_shards"
            registry = KnowledgeShardRegistry(registry_root)
            (registry_root / "artifact_catalog.jsonl").unlink()

            result = asyncio.run(rebuild_experience_artifact_catalog(
                registry=registry, provider=provider, token="test-token", tenant_id="tenant-a"
            ))

            self.assertEqual(result["inspected_manifests"], 2)
            self.assertEqual(result["restored_artifacts"], 2)
            self.assertTrue(result["integrity_verified"])
            artifact_id = "tenant-a:tenants/tenant-a/nodes/task-1/manifest.json:" + hashlib.sha256(b'{"ok":true}').hexdigest()
            self.assertIsNotNone(registry.find_artifact(artifact_id))

    def test_rebuild_skips_tampered_remote_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            provider = FakeProvider()
            self.run_archive(workspace, provider)
            registry = KnowledgeShardRegistry(workspace / ".tenants" / "tenant-a" / "knowledge_shards")
            original_read = provider.read_text_file

            async def tampered_read(**kwargs):
                value = await original_read(**kwargs)
                if kwargs["file_path"].endswith("manifest.json"):
                    return "tampered"
                return value

            provider.read_text_file = tampered_read
            result = asyncio.run(rebuild_experience_artifact_catalog(
                registry=registry, provider=provider, token="test-token", tenant_id="tenant-a"
            ))
            self.assertEqual(result["restored_artifacts"], 1)
            self.assertTrue(any(item["reason"] == "artifact_digest_mismatch" for item in result["skipped"]))


if __name__ == "__main__":
    unittest.main()
