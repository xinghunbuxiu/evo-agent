"""Regression tests for integrity manifests produced by the real archive path."""
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin import work_nodes_runtime as archive_module  # noqa: E402
from admin.work_nodes_runtime import work_node_storage_prefix  # noqa: E402


class GeneratedArchiveIntegrityTests(unittest.TestCase):
    def test_generated_manifest_hashes_exact_utf8_payloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            node = {
                "task_id": "task-1",
                "node_id": "node:task-1",
                "work_type_id": "design",
                "member_id": "member-1",
                "title": "户型设计",
                "phases": [{"key": "approved", "summary": "确认完成"}],
            }
            runtime = {
                "task_center": {
                    "items": [{"task_id": "task-1", "status": "approved"}]
                }
            }
            with (
                patch.object(archive_module, "build_work_nodes_from_runtime", return_value=[node]),
                patch.object(archive_module, "list_skills_for_scope", return_value=[]),
                patch.dict(os.environ, {"GITEE_TOKEN": ""}),
            ):
                result = asyncio.run(archive_module.archive_work_node_to_storage(
                    workspace=workspace,
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

            self.assertEqual(result["status"], "local_only")
            base = Path(result["local_root"])
            integrity = json.loads(
                (base / "archive.integrity.json").read_text(encoding="utf-8")
            )
            self.assertEqual(integrity["algorithm"], "sha256")
            self.assertIn("manifest.json", integrity["files"])
            self.assertIn("phases/approved.json", integrity["files"])
            for relative_path, expected_digest in integrity["files"].items():
                payload = (base / relative_path).read_bytes()
                self.assertEqual(
                    hashlib.sha256(payload).hexdigest(),
                    expected_digest,
                    f"wrong digest for {relative_path}",
                )
            manifest_text = (base / "manifest.json").read_text(encoding="utf-8")
            self.assertIn("户型设计", manifest_text)


    def test_retry_rejects_unlisted_extra_file_before_remote_access(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            prefix = work_node_storage_prefix("tenant-a", "design", "member-1", "task-1")
            base = workspace / ".admin" / "local_git_exports" / prefix
            base.mkdir(parents=True)
            payloads = {"manifest.json": "{}", "skills.json": "[]"}
            hashes = {}
            for relative_path, content in payloads.items():
                (base / relative_path).write_text(content, encoding="utf-8")
                hashes[relative_path] = hashlib.sha256(content.encode("utf-8")).hexdigest()
            (base / "archive.integrity.json").write_text(
                json.dumps({"algorithm": "sha256", "files": hashes}),
                encoding="utf-8",
            )
            (base / "unexpected.json").write_text("not in manifest", encoding="utf-8")
            runtime = {
                "task_center": {
                    "items": [{"task_id": "task-1", "status": "approved"}]
                }
            }
            node = {
                "task_id": "task-1",
                "node_id": "node:task-1",
                "work_type_id": "design",
                "member_id": "member-1",
            }

            with (
                patch.object(archive_module, "build_work_nodes_from_runtime", return_value=[node]),
                patch.dict(os.environ, {"GITEE_TOKEN": ""}),
            ):
                result = asyncio.run(archive_module.retry_local_work_node_archive(
                    workspace=workspace,
                    tenant_id="tenant-a",
                    runtime=runtime,
                    task_id="task-1",
                    get_user_gitee_token=lambda request: None,
                    tenant_manager=None,
                    config=None,
                    get_git_provider_instance=lambda *args: self.fail("remote provider must not be initialized"),
                    get_tenant_git_repo=lambda *args: self.fail("remote repo must not be resolved"),
                    request=object(),
                ))

            self.assertEqual(result["status"], "failed")
            self.assertIn("archive file set does not match integrity manifest", result["reason"])
            self.assertFalse(result["integrity_verified"])


if __name__ == "__main__":
    unittest.main()
