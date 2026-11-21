"""Tests for process-local worker lease heartbeat supervision."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.worker_lease_runtime import start_worker_task_lease_heartbeat


class _Registry:
    def __init__(self):
        self.renewals = []

    def renew_worker_task_lease(self, **kwargs):
        self.renewals.append(kwargs)


class _Queue:
    def __init__(self, states):
        self.states = list(states)
        self.calls = 0

    def get_task(self, task_id):
        state = self.states[min(self.calls, len(self.states) - 1)]
        self.calls += 1
        if state is None:
            return None
        return SimpleNamespace(status=SimpleNamespace(value=state))


class WorkerLeaseHeartbeatTests(unittest.TestCase):
    def test_renews_while_task_is_pending_then_exits_when_terminal(self):
        registry = _Registry()
        queue = _Queue(["pending", "running", "success"])
        thread = start_worker_task_lease_heartbeat(
            organization_registry=registry,
            task_queue=queue,
            worker_id="worker-a",
            claim_id="claim-a",
            lease_token="secret-token",
            task_ids=["task-a"],
            heartbeat_interval_seconds=0.001,
        )
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertGreaterEqual(len(registry.renewals), 2)
        self.assertTrue(all(item["lease_token"] == "secret-token" for item in registry.renewals))
        self.assertTrue(all(item["task_id"] == "claim-a" for item in registry.renewals))

    def test_missing_queue_record_keeps_lease_alive_until_state_is_known(self):
        registry = _Registry()
        queue = _Queue([None, "failed"])
        thread = start_worker_task_lease_heartbeat(
            organization_registry=registry,
            task_queue=queue,
            worker_id="worker-a",
            claim_id="claim-b",
            lease_token="secret-token",
            task_ids=["task-missing"],
            heartbeat_interval_seconds=0.001,
        )
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(registry.renewals), 1)

    def test_transient_queue_lookup_error_keeps_lease_alive_and_retries(self):
        registry = _Registry()

        class FlakyQueue:
            def __init__(self):
                self.calls = 0

            def get_task(self, task_id):
                self.calls += 1
                if self.calls == 1:
                    raise OSError("temporary queue read failure")
                return SimpleNamespace(status=SimpleNamespace(value="failed"))

        queue = FlakyQueue()
        thread = start_worker_task_lease_heartbeat(
            organization_registry=registry,
            task_queue=queue,
            worker_id="worker-a",
            claim_id="claim-transient",
            lease_token="secret-token",
            task_ids=["task-a"],
            heartbeat_interval_seconds=0.001,
        )
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(queue.calls, 2)
        self.assertEqual(len(registry.renewals), 1)
        self.assertEqual(registry.renewals[0]["task_id"], "claim-transient")

    def test_rejects_empty_task_set_and_token(self):
        registry = _Registry()
        queue = _Queue(["success"])
        with self.assertRaisesRegex(ValueError, "task_id"):
            start_worker_task_lease_heartbeat(
                organization_registry=registry,
                task_queue=queue,
                worker_id="worker-a",
                claim_id="claim-c",
                lease_token="secret-token",
                task_ids=[],
            )
        with self.assertRaisesRegex(ValueError, "lease_token"):
            start_worker_task_lease_heartbeat(
                organization_registry=registry,
                task_queue=queue,
                worker_id="worker-a",
                claim_id="claim-c",
                lease_token="",
                task_ids=["task-a"],
            )


if __name__ == "__main__":
    unittest.main()
