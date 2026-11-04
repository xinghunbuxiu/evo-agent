"""Tests for numbered, capacity-aware knowledge repository shards."""
import hashlib
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.knowledge_shards import KnowledgeShardRegistry, ShardPolicy  # noqa: E402


class KnowledgeShardRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.registry = KnowledgeShardRegistry(
            Path(self.temp_dir.name),
            policy=ShardPolicy(warning_ratio=0.70, stop_writes_ratio=0.80, hard_limit_ratio=0.90),
        )

    def _activate(self, shard):
        return self.registry.activate_shard(
            shard["repository_id"],
            full_name=f"owner/{shard['repository_id'].lower()}",
            url=f"https://gitee.com/owner/{shard['repository_id'].lower()}",
            branch="master",
            capacity_limit_bytes=1000,
            max_files=100,
        )

    def test_reservations_are_numbered_and_domain_scoped(self):
        a1 = self.registry.reserve_next_shard("mission")
        a2 = self.registry.reserve_next_shard("mission")
        d1 = self.registry.reserve_next_shard("experience")
        self.assertEqual([a1["repository_id"], a2["repository_id"], d1["repository_id"]],
                         ["A-01", "A-02", "D-01"])
        self.assertEqual(len(self.registry.list_shards("mission")), 2)

    def test_concurrent_reservations_never_allocate_duplicate_ids(self):
        results = []
        errors = []

        def reserve():
            try:
                results.append(self.registry.reserve_next_shard("worker")["repository_id"])
            except Exception as exc:  # pragma: no cover - assertion reports unexpected failures
                errors.append(exc)

        threads = [threading.Thread(target=reserve) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 12)
        self.assertEqual(len(set(results)), 12)
        self.assertEqual(set(results), {f"B-{index:02d}" for index in range(1, 13)})

    def test_capacity_threshold_seals_shard_and_stops_new_writes(self):
        shard = self._activate(self.registry.reserve_next_shard("mission"))
        self.assertEqual(self.registry.select_writable_shard("mission")["repository_id"], "A-01")

        measured = self.registry.update_usage(
            shard["repository_id"], used_bytes=800, file_count=10, largest_file_bytes=200
        )
        self.assertEqual(measured["status"], "sealed")
        self.assertFalse(measured["writable"])
        self.assertTrue(measured["capacity_warning"])
        self.assertIsNone(self.registry.select_writable_shard("mission"))

        next_shard = self.registry.reserve_next_shard("mission")
        self.assertEqual(next_shard["repository_id"], "A-02")

    def test_file_count_can_trigger_capacity_seal(self):
        shard = self._activate(self.registry.reserve_next_shard("skill"))
        measured = self.registry.update_usage(
            shard["repository_id"], used_bytes=10, file_count=80
        )
        self.assertEqual(measured["capacity_ratio"], 0.8)
        self.assertEqual(measured["status"], "sealed")

    def test_catalog_records_verified_digest_and_is_idempotent(self):
        shard = self._activate(self.registry.reserve_next_shard("experience"))
        payload = "阳台不是普通房间".encode("utf-8")
        record = self.registry.record_artifact(
            artifact_id="lesson-001",
            tenant_id="tenant-a",
            domain="experience",
            repository_id=shard["repository_id"],
            path="2026/11/lesson-001.json",
            artifact_type="mistake_book",
            version=1,
            content=payload,
        )
        self.assertEqual(record["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(self.registry.find_artifact("lesson-001"), record)
        self.assertEqual(
            self.registry.record_artifact(
                artifact_id="lesson-001",
                tenant_id="tenant-a",
                domain="experience",
                repository_id=shard["repository_id"],
                path="2026/11/lesson-001.json",
                artifact_type="mistake_book",
                version=1,
                content=payload,
            ),
            record,
        )
        with self.assertRaisesRegex(RuntimeError, "different content"):
            self.registry.record_artifact(
                artifact_id="lesson-001",
                tenant_id="tenant-a",
                domain="experience",
                repository_id=shard["repository_id"],
                path="2026/11/lesson-001.json",
                artifact_type="mistake_book",
                version=1,
                content=b"different",
            )

    def test_catalog_rejects_unregistered_or_unavailable_shard(self):
        shard = self.registry.reserve_next_shard("mission")
        with self.assertRaisesRegex(ValueError, "active or sealed"):
            self.registry.record_artifact(
                artifact_id="task-1",
                tenant_id="tenant-a",
                domain="mission",
                repository_id=shard["repository_id"],
                path="task.json",
                artifact_type="execution_trace",
                version=1,
                content=b"{}",
            )

    def test_registry_is_valid_json_after_atomic_updates(self):
        shard = self._activate(self.registry.reserve_next_shard("project"))
        self.registry.update_usage(shard["repository_id"], used_bytes=100, file_count=2)
        data = json.loads(self.registry.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(data["domains"]["project"]["shards"][0]["repository_id"], "F-01")


if __name__ == "__main__":
    unittest.main()
