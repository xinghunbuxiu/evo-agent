"""Regression tests for work-node archive snapshot primitives.

Run from the repository root with:
    python -m unittest discover -s tests -p 'test_work_nodes_archive.py'
"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.work_nodes_runtime import (  # noqa: E402
    _write_local_node_archive,
    attach_archive_to_task,
    work_node_storage_prefix,
)


class LocalArchiveSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.workspace = Path(self.temp_dir.name)
        self.prefix = work_node_storage_prefix("tenant-a", "design", "member-1", "task-1")

    def test_storage_prefix_sanitizes_each_path_segment(self):
        prefix = work_node_storage_prefix("tenant/a", "design role", "member:1", "task/1")
        self.assertEqual(
            prefix,
            "tenants/tenant_a/work_types/design_role/members/member_1/nodes/task_1",
        )

    def test_snapshot_round_trips_utf8_and_reports_verified_files(self):
        files = {
            "manifest.json": json.dumps({"title": "户型设计"}, ensure_ascii=False),
            "phases/approved.json": '{"status":"done"}',
        }
        result = _write_local_node_archive(self.workspace, self.prefix, files)
        base = Path(result["local_root"])

        self.assertEqual(result["status"], "local_only")
        self.assertTrue(result["integrity_verified"])
        self.assertEqual(set(result["verified_files"]), set(files))
        for rel_path, expected in files.items():
            self.assertEqual((base / rel_path).read_text(encoding="utf-8"), expected)

    def test_snapshot_removes_stale_files_from_previous_version(self):
        _write_local_node_archive(
            self.workspace, self.prefix,
            {"manifest.json": "v1", "phases/obsolete.json": "old"},
        )
        result = _write_local_node_archive(
            self.workspace, self.prefix, {"manifest.json": "v2"},
        )
        base = Path(result["local_root"])
        self.assertEqual((base / "manifest.json").read_text(encoding="utf-8"), "v2")
        self.assertFalse((base / "phases/obsolete.json").exists())
        self.assertEqual(result["files"], [f"{self.prefix}/manifest.json"])

    def test_attach_archive_updates_only_matching_task(self):
        runtime = {"task_center": {"items": [
            {"task_id": "task-1", "status": "approved"},
            {"task_id": "task-2", "status": "approved"},
        ]}}
        metadata = {"status": "local_only", "integrity_verified": True}
        self.assertTrue(attach_archive_to_task(runtime, "task-1", metadata))
        self.assertEqual(runtime["task_center"]["items"][0]["work_node_archive"], metadata)
        self.assertNotIn("work_node_archive", runtime["task_center"]["items"][1])


    def _write_retry_snapshot(self, files):
        base = self.workspace / ".admin" / "local_git_exports" / self.prefix
        base.mkdir(parents=True, exist_ok=True)
        hashes = {}
        for rel_path, content in files.items():
            target = base / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            hashes[rel_path] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        (base / "archive.integrity.json").write_text(
            json.dumps({"algorithm": "sha256", "files": hashes}),
            encoding="utf-8",
        )
        return base

    def _retry(self):
        import asyncio
        import os
        from unittest.mock import patch
        from admin import work_nodes_runtime as archive_module

        runtime = {"task_center": {"items": [{"task_id": "task-1", "status": "approved"}]}}
        node = {"task_id": "task-1", "node_id": "node:task-1", "work_type_id": "design", "member_id": "member-1"}
        with patch.object(archive_module, "build_work_nodes_from_runtime", return_value=[node]), patch.dict(os.environ, {"GITEE_TOKEN": ""}):
            return asyncio.run(archive_module.retry_local_work_node_archive(
                workspace=self.workspace,
                tenant_id="tenant-a",
                runtime=runtime,
                task_id="task-1",
                get_user_gitee_token=lambda request: None,
                tenant_manager=None,
                config=None,
                get_git_provider_instance=lambda *args: None,
                get_tenant_git_repo=lambda *args: (None, None),
                request=object(),
            ))

    def test_retry_rejects_missing_integrity_manifest_before_remote_access(self):
        result = self._retry()
        self.assertEqual(result["status"], "failed")
        self.assertIn("archive.integrity.json missing", result["reason"])
        self.assertFalse(result["integrity_verified"])

    def test_retry_rejects_empty_integrity_manifest_before_remote_access(self):
        self._write_retry_snapshot({})
        result = self._retry()
        self.assertEqual(result["status"], "failed")
        self.assertIn("integrity manifest contains no files", result["reason"])
        self.assertFalse(result["integrity_verified"])

    def test_retry_rejects_malformed_sha256_digest_before_remote_access(self):
        base = self.workspace / ".admin" / "local_git_exports" / self.prefix
        base.mkdir(parents=True, exist_ok=True)
        (base / "manifest.json").write_text("{}", encoding="utf-8")
        (base / "archive.integrity.json").write_text(
            json.dumps({"algorithm": "sha256", "files": {"manifest.json": "not-a-sha256"}}),
            encoding="utf-8",
        )
        result = self._retry()
        self.assertEqual(result["status"], "failed")
        self.assertIn("invalid SHA-256 digest", result["reason"])
        self.assertFalse(result["integrity_verified"])

    def test_retry_rejects_hash_mismatch_before_remote_access(self):
        base = self.workspace / ".admin" / "local_git_exports" / self.prefix
        base.mkdir(parents=True, exist_ok=True)
        (base / "manifest.json").write_text("tampered", encoding="utf-8")
        (base / "archive.integrity.json").write_text(
            json.dumps({"algorithm": "sha256", "files": {"manifest.json": "0" * 64}}),
            encoding="utf-8",
        )
        result = self._retry()
        self.assertEqual(result["status"], "failed")
        self.assertIn("archive hash mismatch", result["reason"])
        self.assertFalse(result["integrity_verified"])

    def test_retry_keeps_valid_snapshot_when_gitee_token_is_missing(self):
        self._write_retry_snapshot({"manifest.json": "{}", "skills.json": "[]"})
        result = self._retry()
        self.assertEqual(result["status"], "local_only")
        self.assertEqual(result["reason"], "missing_gitee_token")
        self.assertTrue(result["integrity_verified"])


    def _retry_with_remote(self, *, upload_error=None, corrupt_readback=False):
        import asyncio
        import os
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from admin import work_nodes_runtime as archive_module

        files = {"manifest.json": "{}", "skills.json": "[]"}
        base = self._write_retry_snapshot(files)
        remote_files = dict(files)
        remote_files["archive.integrity.json"] = (base / "archive.integrity.json").read_text(encoding="utf-8")
        provider = SimpleNamespace()
        if upload_error:
            provider.upsert_text_file = AsyncMock(side_effect=RuntimeError("simulated upload failure"))
        else:
            provider.upsert_text_file = AsyncMock()
        async def read_back(*, file_path, **kwargs):
            rel_path = file_path[len(self.prefix) + 1:]
            if corrupt_readback and rel_path == "manifest.json":
                return "different content"
            return remote_files.get(rel_path)
        provider.read_text_file = AsyncMock(side_effect=read_back)
        config = SimpleNamespace(experiences=SimpleNamespace(full_name="owner/repo", url="https://gitee.com/owner/repo"))
        runtime = {"task_center": {"items": [{"task_id": "task-1", "status": "approved"}]}}
        node = {"task_id": "task-1", "node_id": "node:task-1", "work_type_id": "design", "member_id": "member-1"}
        with patch.object(archive_module, "build_work_nodes_from_runtime", return_value=[node]), patch.dict(os.environ, {"GITEE_TOKEN": "test-token"}):
            return asyncio.run(archive_module.retry_local_work_node_archive(
                workspace=self.workspace,
                tenant_id="tenant-a",
                runtime=runtime,
                task_id="task-1",
                get_user_gitee_token=lambda request: None,
                tenant_manager=SimpleNamespace(get_git_knowledge_config=lambda tenant_id: {}),
                config=config,
                get_git_provider_instance=lambda *args: provider,
                get_tenant_git_repo=lambda *args: ("owner/repo", "https://gitee.com/owner/repo"),
                request=object(),
            )), provider

    def test_retry_preserves_local_snapshot_when_remote_upload_fails(self):
        result, provider = self._retry_with_remote(upload_error=True)
        self.assertEqual(result["status"], "local_only")
        self.assertIn("simulated upload failure", result["reason"])
        self.assertTrue(result["integrity_verified"])
        self.assertEqual(provider.upsert_text_file.await_count, 1)

    def test_retry_rejects_remote_readback_mismatch(self):
        result, provider = self._retry_with_remote(corrupt_readback=True)
        self.assertEqual(result["status"], "local_only")
        self.assertIn("remote archive verification failed", result["reason"])
        self.assertTrue(result["integrity_verified"])
        self.assertEqual(provider.read_text_file.await_count, 1)

    def test_retry_reports_archived_only_after_all_files_read_back(self):
        result, provider = self._retry_with_remote()
        self.assertEqual(result["status"], "archived")
        self.assertTrue(result["integrity_verified"])
        self.assertEqual(set(result["verified_files"]), set(result["files"]))
        self.assertEqual(provider.upsert_text_file.await_count, 3)
        self.assertEqual(provider.read_text_file.await_count, 3)

    def test_integrity_manifest_uses_sha256_utf8_bytes(self):
        payload = "中文内容"
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.assertEqual(len(expected), 64)
        self.assertEqual(expected, hashlib.sha256(payload.encode()).hexdigest())


if __name__ == "__main__":
    unittest.main()
