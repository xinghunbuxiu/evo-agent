"""Signed independent verification requirements for Worker Growth Learning Tasks."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.learning_task_verification_runtime import (  # noqa: E402
    attach_learning_task_attestation,
    require_passed_learning_task_attestation,
)
from core.verification import sign_verification_evidence


class LearningTaskVerificationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.tenant_id = "tenant-a"
        self.task = {
            "task_id": "learning:growth:member-a:run-a:node-a",
            "member_id": "member-a",
            "status": "submitted",
            "metadata": {
                "source": "talent_center_worker_growth_adoption",
                "executing_worker_id": "worker-a",
                "execution_event_id": "learning-submit:attempt-1",
            },
        }

    def tearDown(self):
        self.temp.cleanup()

    def _attestation(self, **overrides):
        payload = {
            "source": "learning_task_independent_verifier",
            "tenant_id": self.tenant_id,
            "learning_task_id": self.task["task_id"],
            "member_id": "member-a",
            "worker_id": "worker-a",
            "execution_event_id": "learning-submit:attempt-1",
            "verifier_id": "isolated-learning-verifier",
            "verifier_version": "1",
            "status": "passed",
            "checks": [{"check_id": "deliverables", "passed": True}],
            "verified_at": "2026-11-18T12:00:00+08:00",
            **overrides,
        }
        return sign_verification_evidence(self.workspace, self.tenant_id, payload)

    def test_signed_exactly_bound_pass_attestation_can_be_attached_and_revalidated(self):
        attestation = self._attestation()
        attached = attach_learning_task_attestation(
            self.workspace, self.tenant_id, self.task, attestation,
        )
        self.assertEqual(attached["status"], "passed")
        self.assertEqual(
            require_passed_learning_task_attestation(
                self.workspace, self.tenant_id, self.task,
            )["sha256"],
            attached["sha256"],
        )

    def test_unsigned_or_cross_task_attestation_is_rejected(self):
        unsigned = self._attestation()
        unsigned.pop("signature")
        with self.assertRaisesRegex(ValueError, "signature is invalid"):
            attach_learning_task_attestation(
                self.workspace, self.tenant_id, self.task, unsigned,
            )
        foreign = self._attestation(learning_task_id="learning:other")
        with self.assertRaisesRegex(ValueError, "learning_task_id binding mismatch"):
            attach_learning_task_attestation(
                self.workspace, self.tenant_id, self.task, foreign,
            )

    def test_worker_and_submission_event_must_match_exact_task_execution(self):
        wrong_worker = self._attestation(worker_id="worker-b")
        with self.assertRaisesRegex(ValueError, "worker_id binding mismatch"):
            attach_learning_task_attestation(
                self.workspace, self.tenant_id, self.task, wrong_worker,
            )
        wrong_event = self._attestation(execution_event_id="another-attempt")
        with self.assertRaisesRegex(ValueError, "execution_event_id binding mismatch"):
            attach_learning_task_attestation(
                self.workspace, self.tenant_id, self.task, wrong_event,
            )

    def test_failed_or_inconsistent_verdict_cannot_be_approved(self):
        failed = self._attestation(
            status="failed",
            checks=[{"check_id": "deliverables", "passed": False}],
        )
        attach_learning_task_attestation(
            self.workspace, self.tenant_id, self.task, failed,
        )
        with self.assertRaisesRegex(ValueError, "did not pass"):
            require_passed_learning_task_attestation(
                self.workspace, self.tenant_id, self.task,
            )
        inconsistent = self._attestation(
            status="passed",
            checks=[{"check_id": "deliverables", "passed": False}],
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            attach_learning_task_attestation(
                self.workspace, self.tenant_id, self.task, inconsistent,
            )

    def test_verification_requires_submitted_worker_growth_task(self):
        self.task["status"] = "in_progress"
        with self.assertRaisesRegex(ValueError, "must be submitted"):
            attach_learning_task_attestation(
                self.workspace, self.tenant_id, self.task, self._attestation(),
            )


if __name__ == "__main__":
    unittest.main()
