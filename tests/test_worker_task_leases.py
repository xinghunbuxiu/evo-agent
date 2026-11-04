"""Focused tests for worker execution leases and conservative expiry handling."""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.organization_runtime import OrganizationRegistry


class WorkerLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.registry = OrganizationRegistry(Path(self.temp.name))
        self.registry.create_role(
            role_id="android-role",
            title="Android worker",
            responsibilities=["execute Android tasks"],
            required_capabilities=["android"],
        )
        self.registry.create_worker(
            worker_id="android-worker",
            role_id="android-role",
            profile={"handler_id": "android-worker", "capability_type": "android"},
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_claim_issues_stable_token_and_heartbeat_renews_lease(self):
        claimed = self.registry.claim_worker_task(
            worker_id="android-worker", task_id="task-1", lease_seconds=60
        )
        lease = claimed["task_leases"]["task-1"]
        retried = self.registry.claim_worker_task(
            worker_id="android-worker", task_id="task-1", lease_seconds=60
        )
        self.assertEqual(retried["task_leases"]["task-1"]["lease_token"], lease["lease_token"])

        renewed = self.registry.renew_worker_task_lease(
            worker_id="android-worker",
            task_id="task-1",
            lease_token=lease["lease_token"],
            lease_seconds=120,
        )
        renewed_lease = renewed["task_leases"]["task-1"]
        self.assertEqual(renewed_lease["lease_token"], lease["lease_token"])
        self.assertGreater(
            datetime.fromisoformat(renewed_lease["expires_at"]),
            datetime.fromisoformat(lease["expires_at"]),
        )

    def test_stale_token_cannot_renew_lease(self):
        claimed = self.registry.claim_worker_task(
            worker_id="android-worker", task_id="task-2"
        )
        with self.assertRaisesRegex(ValueError, "Lease token"):
            self.registry.renew_worker_task_lease(
                worker_id="android-worker",
                task_id="task-2",
                lease_token="not-the-owner-token",
            )
        self.assertEqual(claimed["status"], "busy")

    def test_expired_lease_is_reported_but_never_auto_released(self):
        claimed = self.registry.claim_worker_task(
            worker_id="android-worker", task_id="task-3"
        )
        lease = claimed["task_leases"]["task-3"]
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        expired = self.registry.list_expired_worker_task_leases(now=future)
        self.assertEqual(
            [(item["worker_id"], item["task_id"]) for item in expired],
            [("android-worker", "task-3")],
        )
        # Expiry is a signal for task-queue reconciliation, not proof the task stopped.
        current = self.registry.get_worker("android-worker")
        self.assertEqual(current["status"], "busy")
        self.assertIn("task-3", current["active_task_ids"])
        with self.assertRaisesRegex(ValueError, "Expired lease"):
            self.registry.renew_worker_task_lease(
                worker_id="android-worker",
                task_id="task-3",
                lease_token=lease["lease_token"],
            )

    def test_queue_reconciliation_can_recover_an_expired_active_lease(self):
        claimed = self.registry.claim_worker_task(
            worker_id="android-worker", task_id="task-recovery", lease_seconds=60
        )
        token = claimed["task_leases"]["task-recovery"]["lease_token"]
        workers = self.registry._read(self.registry.workers_path)
        workers["android-worker"]["task_leases"]["task-recovery"]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        ).isoformat()
        self.registry._write(self.registry.workers_path, workers)

        with self.assertRaisesRegex(ValueError, "Expired lease"):
            self.registry.renew_worker_task_lease(
                worker_id="android-worker",
                task_id="task-recovery",
                lease_token=token,
            )

        recovered = self.registry.recover_worker_task_lease(
            worker_id="android-worker", task_id="task-recovery", lease_seconds=120
        )
        lease = recovered["task_leases"]["task-recovery"]
        self.assertEqual(lease["lease_token"], token)
        self.assertGreater(
            datetime.fromisoformat(lease["expires_at"]),
            datetime.now(timezone.utc),
        )

    def test_release_removes_lease_and_clone_starts_without_runtime_lease(self):
        claimed = self.registry.claim_worker_task(
            worker_id="android-worker", task_id="task-4"
        )
        self.assertIn("task-4", claimed["task_leases"])
        released = self.registry.release_worker_task(
            worker_id="android-worker", task_id="task-4"
        )
        self.assertNotIn("task-4", released["task_leases"])
        clone = self.registry.clone_worker(
            source_worker_id="android-worker", new_worker_id="android-worker-copy"
        )
        self.assertEqual(clone["task_leases"], {})
        self.assertEqual(clone["active_task_ids"], [])


if __name__ == "__main__":
    unittest.main()
