"""Tests for durable ExperienceStore outbox persistence and remote sync."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.experience_outbox_runtime import sync_experience_outbox
from core import Experience, ExperienceStore


class FakeProvider:
    provider_name = "gitee"

    def __init__(self):
        self.files = {}
        self.created = []

    async def ensure_repo(self, *, token, name, description, private, auto_init, namespace):
        self.created.append(name)
        full_name = f"{namespace}/{name}" if namespace else name
        return SimpleNamespace(
            full_name=full_name,
            html_url=f"https://gitee.com/{full_name}",
            branch="master",
        )

    async def upsert_text_file(self, *, token, repo_full_name, file_path, content, message, branch):
        self.files[(repo_full_name, branch, file_path)] = content

    async def read_text_file(self, *, token, repo_full_name, file_path, branch):
        return self.files.get((repo_full_name, branch, file_path))

    async def list_directory(self, *, token, repo_full_name, path, branch):
        prefix = path.rstrip("/") + "/"
        entries = []
        for (repo, file_branch, file_path), _content in self.files.items():
            if repo != repo_full_name or file_branch != branch or not file_path.startswith(prefix):
                continue
            remainder = file_path[len(prefix):]
            if "/" not in remainder:
                entries.append({"type": "file", "path": file_path})
            else:
                directory = prefix + remainder.split("/", 1)[0]
                if not any(item.get("path") == directory for item in entries):
                    entries.append({"type": "dir", "path": directory})
        return entries


class ExperienceOutboxTests(unittest.TestCase):
    def make_experience(self, experience_id="exp-1"):
        return Experience(
            id=experience_id,
            domain="android",
            task_type="analysis",
            input_summary="IMS registration failure",
            output_summary="Checked modem and VoLTE provisioning",
            quality_score=0.9,
        )

    def test_save_persists_local_record_and_durable_outbox(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ExperienceStore(Path(temp_dir), "tenant-a")
            store.save(self.make_experience())

            local_file = Path(temp_dir) / ".tenants/tenant-a/experiences/android/exp-1.json"
            pending = Path(temp_dir) / ".tenants/tenant-a/experience_outbox/pending"
            records = list(pending.glob("*.json"))
            self.assertTrue(local_file.is_file())
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_text(encoding="utf-8"))
            self.assertEqual(record["tenant_id"], "tenant-a")
            self.assertEqual(record["domain"], "android")
            self.assertEqual(record["relative_path"].split("/", 1)[0], "android")
            self.assertEqual(record["sha256"], __import__("hashlib").sha256(record["content"].encode()).hexdigest())

    def test_sync_verifies_remote_archive_then_marks_outbox_delivered(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            store = ExperienceStore(workspace, "tenant-a")
            store.save(self.make_experience())
            provider = FakeProvider()

            result = asyncio.run(sync_experience_outbox(
                workspace=workspace,
                tenant_id="tenant-a",
                provider=provider,
                token="test-token",
                namespace="owner",
                repository_name_prefix="evo-tenant-a-experience",
            ))

            self.assertTrue(result["integrity_verified"])
            self.assertEqual(result["synced"], 1)
            self.assertEqual(result["repository_id"], "D-01")
            pending = workspace / ".tenants/tenant-a/experience_outbox/pending"
            delivered = workspace / ".tenants/tenant-a/experience_outbox/delivered"
            self.assertEqual(list(pending.glob("*.json")), [])
            self.assertEqual(len(list(delivered.glob("*.json"))), 1)
            self.assertTrue(any(path.endswith(".json") for _, _, path in provider.files))

    def test_retry_after_remote_success_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            ExperienceStore(workspace, "tenant-a").save(self.make_experience())
            provider = FakeProvider()
            first = asyncio.run(sync_experience_outbox(
                workspace=workspace, tenant_id="tenant-a", provider=provider,
                token="test-token", namespace="owner",
                repository_name_prefix="evo-tenant-a-experience",
            ))
            second = asyncio.run(sync_experience_outbox(
                workspace=workspace, tenant_id="tenant-a", provider=provider,
                token="test-token", namespace="owner",
                repository_name_prefix="evo-tenant-a-experience",
            ))
            self.assertEqual(first["synced"], 1)
            self.assertEqual(second["synced"], 0)
            self.assertEqual(provider.created, ["evo-tenant-a-experience-d-01"])

    def test_corrupt_outbox_record_is_not_deleted_or_marked_delivered(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            store = ExperienceStore(workspace, "tenant-a")
            store.save(self.make_experience())
            pending = workspace / ".tenants/tenant-a/experience_outbox/pending"
            record_path = next(pending.glob("*.json"))
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["sha256"] = "0" * 64
            record_path.write_text(json.dumps(record), encoding="utf-8")
            result = asyncio.run(sync_experience_outbox(
                workspace=workspace, tenant_id="tenant-a", provider=FakeProvider(),
                token="test-token", namespace="owner",
                repository_name_prefix="evo-tenant-a-experience",
            ))
            self.assertFalse(result["integrity_verified"])
            self.assertEqual(result["synced"], 0)
            self.assertTrue(record_path.exists())


if __name__ == "__main__":
    unittest.main()
