import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.organization_runtime import OrganizationRegistry
import admin.mission_runtime as mission_runtime
from admin.mission_runtime import (
    load_mission_runs,
    release_worker_claim_for_review,
    reconcile_worker_claims_on_startup,
    save_mission_runs,
)


class Queue:
    def __init__(self, statuses=None):
        self.statuses = statuses or {}

    def get_task(self, task_id):
        status = self.statuses.get(task_id, "success")
        if status is None:
            return None
        return SimpleNamespace(status=SimpleNamespace(value=status))


class MissionWorkerClaimManualReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.registry = OrganizationRegistry(self.workspace)
        self.registry.create_role(
            role_id="android",
            title="Android",
            responsibilities=["execute"],
            required_capabilities=["android"],
        )
        self.registry.create_worker(
            worker_id="worker-a",
            role_id="android",
            profile={"handler_id": "android"},
        )
        self.claim_id = "claim-manual-1"
        self.registry.claim_worker_task(worker_id="worker-a", task_id=self.claim_id)
        save_mission_runs(self.workspace, {"items": [{
            "mission_run_id": "run-a",
            "tenant_id": "tenant-a",
            "actions": [{
                "task_id": "task-a",
                "worker_claim": {
                    "claim_id": self.claim_id,
                    "worker_id": "worker-a",
                    "state": "claimed",
                    "recovery_status": "needs_review",
                    "recovery_reason": "queue_task_missing",
                },
            }],
        }]})
        self.actor = {"id": 7, "auth_provider": "password"}

    def release(self, *, queue=None, registry=None, tenant_id="tenant-a"):
        return release_worker_claim_for_review(
            workspace=self.workspace,
            mission_run_id="run-a",
            tenant_id=tenant_id,
            claim_id=self.claim_id,
            actor=self.actor,
            reason="Verified task is terminal and reviewed by tenant admin",
            task_queue=queue or Queue(),
            organization_registry=registry or self.registry,
        )

    def test_admin_release_updates_both_stores_and_writes_two_phase_audit(self):
        result = self.release()
        claim = load_mission_runs(self.workspace)["items"][0]["actions"][0]["worker_claim"]
        worker = self.registry.get_worker("worker-a")
        audit_path = self.workspace / ".admin" / "worker_claim_recovery_audit.jsonl"
        lines = audit_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(result["state"], "released")
        self.assertEqual(claim["state"], "released")
        self.assertEqual(claim["release_operation"]["status"], "applied")
        self.assertEqual(worker["status"], "available")
        self.assertEqual(worker["active_task_ids"], [])
        self.assertEqual([__import__("json").loads(line)["event"] for line in lines], [
            "release_requested", "release_applied",
        ])
        self.assertEqual(audit_path.stat().st_mode & 0o777, 0o600)
        repeated = self.release()
        self.assertTrue(repeated["already_released"])

    def test_startup_recovery_finishes_a_persisted_manual_release_intent(self):
        state = load_mission_runs(self.workspace)
        claim = state["items"][0]["actions"][0]["worker_claim"]
        claim["release_operation"] = {
            "status": "requested",
            "requested_at": "2026-10-30T10:00:00+00:00",
            "actor_provider": "password",
            "actor_id": "7",
        }
        save_mission_runs(self.workspace, state)
        result = reconcile_worker_claims_on_startup(
            workspace=self.workspace,
            task_queue=Queue(),
            organization_registry=self.registry,
        )
        persisted = load_mission_runs(self.workspace)["items"][0]["actions"][0]["worker_claim"]
        self.assertEqual(result["claims_released"], 1)
        self.assertEqual(persisted["state"], "released")
        self.assertEqual(persisted["release_operation"]["status"], "applied")
        self.assertEqual(self.registry.get_worker("worker-a")["status"], "available")

    def test_retry_repairs_missing_applied_audit_after_state_was_released(self):
        original = mission_runtime._append_worker_claim_recovery_audit

        def fail_applied(workspace, event):
            if event.get("event") == "release_applied":
                raise OSError("simulated audit disk failure")
            return original(workspace, event)

        mission_runtime._append_worker_claim_recovery_audit = fail_applied
        try:
            with self.assertRaises(OSError):
                self.release()
        finally:
            mission_runtime._append_worker_claim_recovery_audit = original

        audit_path = self.workspace / ".admin" / "worker_claim_recovery_audit.jsonl"
        before = [__import__("json").loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([item["event"] for item in before], ["release_requested"])
        self.assertEqual(
            load_mission_runs(self.workspace)["items"][0]["actions"][0]["worker_claim"]["state"],
            "released",
        )

        retried = self.release()
        after = [__import__("json").loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(retried["already_released"])
        self.assertEqual([item["event"] for item in after], ["release_requested", "release_applied"])

    def test_nonterminal_task_keeps_worker_claim_and_writes_no_audit(self):
        with self.assertRaisesRegex(ValueError, "task_not_terminal"):
            self.release(queue=Queue({"task-a": "running"}))
        claim = load_mission_runs(self.workspace)["items"][0]["actions"][0]["worker_claim"]
        self.assertEqual(claim["state"], "claimed")
        self.assertEqual(self.registry.get_worker("worker-a")["status"], "busy")
        self.assertFalse((self.workspace / ".admin" / "worker_claim_recovery_audit.jsonl").exists())

    def test_missing_task_keeps_worker_claim(self):
        with self.assertRaisesRegex(ValueError, "task_missing"):
            self.release(queue=Queue({"task-a": None}))
        self.assertEqual(self.registry.get_worker("worker-a")["active_task_ids"], [self.claim_id])

    def test_worker_registry_mismatch_fails_closed(self):
        self.registry.release_worker_task(worker_id="worker-a", task_id=self.claim_id)
        with self.assertRaisesRegex(ValueError, "registry_claim_mismatch"):
            self.release()
        claim = load_mission_runs(self.workspace)["items"][0]["actions"][0]["worker_claim"]
        self.assertEqual(claim["state"], "claimed")

    def test_cross_tenant_request_is_rejected(self):
        with self.assertRaises(PermissionError):
            self.release(tenant_id="tenant-b")
        self.assertEqual(self.registry.get_worker("worker-a")["status"], "busy")

    def test_claim_referenced_by_another_tenant_is_rejected(self):
        state = load_mission_runs(self.workspace)
        state["items"].append({
            "mission_run_id": "run-b",
            "tenant_id": "tenant-b",
            "actions": [{
                "task_id": "task-b",
                "worker_claim": {
                    "claim_id": self.claim_id,
                    "worker_id": "worker-a",
                    "state": "claimed",
                    "recovery_status": "needs_review",
                },
            }],
        })
        save_mission_runs(self.workspace, state)
        with self.assertRaises(PermissionError):
            self.release()
        self.assertEqual(self.registry.get_worker("worker-a")["status"], "busy")


if __name__ == "__main__":
    unittest.main()
