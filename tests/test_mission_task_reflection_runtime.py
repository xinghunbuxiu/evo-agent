"""Mission terminal task observations automatically create pending Reflections."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_task_reflection_runtime import record_mission_task_reflection
from core.experience_reflection import ExperienceReflectionStore
from core.learning import ExperienceStore
from core.verification import sign_verification_evidence, verify_verification_evidence


class MissionTaskReflectionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.tenant_id = "tenant-a"
        self.mission_run_id = "mission-1"
        self.node_id = "node-1"
        self.task = self._task()
        self.mission_run = {
            "tenant_id": self.tenant_id,
            "mission_run_id": self.mission_run_id,
        }
        self.action = self._action()

    def tearDown(self):
        self.temp.cleanup()

    def _task(self, *, status="success", tenant_id="tenant-a", task_id="queue-task-1"):
        return SimpleNamespace(
            id=task_id,
            tenant_id=tenant_id,
            status=SimpleNamespace(value=status),
            completed_at="2026-11-17T08:00:00+08:00",
            updated_at="2026-11-17T08:00:00+08:00",
            created_at="2026-11-17T07:59:00+08:00",
            result={"summary": "Implemented and tested the parser."},
            error=None,
        )

    def _action(self, *, task_id="queue-task-1"):
        return {
            "tenant_id": self.tenant_id,
            "mission_run_id": self.mission_run_id,
            "node_id": self.node_id,
            "task_id": task_id,
            "title": "Implement parser",
            "task_type": "execute",
            "worker_id": "worker-1",
        }

    def _signed_verification(self, *, task=None, status="passed", checks=None):
        current = task or self.task
        payload = {
            "source": "mission_independent_verifier",
            "task_id": current.id,
            "tenant_id": self.tenant_id,
            "mission_run_id": self.mission_run_id,
            "mission_node_id": self.node_id,
            "execution_event_id": f"task-completion:{current.id}:{current.completed_at}",
            "verifier_id": "workspace-verifier",
            "verifier_version": "1",
            "status": status,
            "checks": checks or [{"check_id": "parser-tests", "passed": status == "passed"}],
        }
        return sign_verification_evidence(self.workspace, self.tenant_id, payload)

    def _record(self, *, task=None, mission_run=None, action=None):
        return record_mission_task_reflection(
            workspace=self.workspace,
            tenant_id=self.tenant_id,
            mission_run=mission_run or self.mission_run,
            action=action or self.action,
            task=task or self.task,
        )

    def test_signed_verification_is_retained_and_bound_to_pending_reflection(self):
        self.action["independent_verification"] = self._signed_verification()
        first = self._record()
        second = self._record()
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "created")
        self.assertEqual(first["review_state"], "pending")
        self.assertEqual(first["independent_verification"], "passed")

        source = next(
            item for item in ExperienceStore(self.workspace, self.tenant_id).load_by_domain("mission_task")
            if item.id == first["source_experience_id"]
        )
        self.assertEqual(source.metadata["task_id"], self.task.id)
        self.assertNotIn("verification", source.metadata)
        self.assertIn(self.task.id, source.metadata["evidence_refs"])

        reflections = ExperienceReflectionStore(self.workspace, self.tenant_id).list_for_source(source.id)
        self.assertEqual(len(reflections), 1)
        payload = reflections[0].metadata["experience_reflection"]
        self.assertEqual(payload["state"], "pending")
        self.assertEqual(payload["author"], "mission-system")
        self.assertEqual(payload["source_experience_digest"], first["source_experience_digest"])
        self.assertIn(self.task.id, payload["source_evidence_refs"])

        execution = payload["findings"]["execution_evidence"]
        self.assertEqual(execution["signature_verification"], "valid")
        self.assertEqual(execution["verdict"], "passed")
        self.assertEqual(
            execution["sha256"],
            hashlib.sha256(json.dumps(
                execution["attestation"], sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")).hexdigest(),
        )
        self.assertTrue(
            verify_verification_evidence(self.workspace, self.tenant_id, execution["attestation"])
        )

    def test_late_verifier_evidence_appends_revision_without_mutating_source(self):
        first = self._record()
        self.assertEqual(first["independent_verification"], "unavailable")
        self.assertEqual(first["reflection_revision"], 1)

        self.action["independent_verification"] = self._signed_verification()
        second = self._record()
        self.assertEqual(second["independent_verification"], "passed")
        self.assertEqual(second["reflection_revision"], 2)
        self.assertEqual(first["source_experience_id"], second["source_experience_id"])
        self.assertEqual(first["source_experience_digest"], second["source_experience_digest"])

        reflections = ExperienceReflectionStore(self.workspace, self.tenant_id).list_for_source(
            first["source_experience_id"]
        )
        self.assertEqual(len(reflections), 2)
        self.assertEqual(
            reflections[0].metadata["experience_reflection"]["findings"]["execution_evidence"]["signature_verification"],
            "unavailable",
        )
        self.assertEqual(
            reflections[1].metadata["experience_reflection"]["findings"]["execution_evidence"]["signature_verification"],
            "valid",
        )

        repeated = self._record()
        self.assertEqual(repeated["reflection_revision"], 2)
        self.assertEqual(len(ExperienceReflectionStore(self.workspace, self.tenant_id).list_for_source(
            first["source_experience_id"]
        )), 2)

        self.action.pop("independent_verification")
        reused = self._record()
        self.assertEqual(reused["reflection_revision"], 2)
        self.assertTrue(reused["reused"])
        self.assertEqual(reused["independent_verification"], "passed")

    def test_unsigned_worker_supplied_verifier_marker_is_not_trusted(self):
        self.action["independent_verification"] = {
            "source": "mission_independent_verifier",
            "task_id": self.task.id,
            "tenant_id": self.tenant_id,
            "mission_run_id": self.mission_run_id,
            "mission_node_id": self.node_id,
            "execution_event_id": f"task-completion:{self.task.id}:{self.task.completed_at}",
            "verifier_id": "forged",
            "verifier_version": "1",
            "status": "passed",
            "checks": [{"check_id": "fake", "passed": True}],
        }
        result = self._record()
        self.assertEqual(result["independent_verification"], "unavailable")
        source = next(
            item for item in ExperienceStore(self.workspace, self.tenant_id).load_by_domain("mission_task")
            if item.id == result["source_experience_id"]
        )
        self.assertNotIn("verification", source.metadata)
        reflection = ExperienceReflectionStore(self.workspace, self.tenant_id).list_for_source(source.id)[0]
        execution = reflection.metadata["experience_reflection"]["findings"]["execution_evidence"]
        self.assertEqual(execution["signature_verification"], "unavailable")
        self.assertEqual(execution["reason"], "signature_invalid")

    def test_cross_tenant_task_is_rejected_before_experience_persistence(self):
        foreign_task = self._task(tenant_id="tenant-b")
        with self.assertRaisesRegex(ValueError, "tenant binding"):
            self._record(task=foreign_task)
        self.assertEqual(ExperienceStore(self.workspace, self.tenant_id).load_by_domain("mission_task"), [])

    def test_missing_task_tenant_is_rejected(self):
        task = self._task(tenant_id="")
        with self.assertRaisesRegex(ValueError, "tenant binding"):
            self._record(task=task)

    def test_action_task_id_must_match_queue_task(self):
        action = self._action(task_id="different-task")
        with self.assertRaisesRegex(ValueError, "task binding"):
            self._record(action=action)

    def test_mission_tenant_must_match_requested_tenant(self):
        mission_run = {**self.mission_run, "tenant_id": "tenant-b"}
        with self.assertRaisesRegex(ValueError, "tenant binding"):
            self._record(mission_run=mission_run)

    def test_failed_signed_checks_are_recorded_as_failure_causes(self):
        self.task = self._task(status="failed")
        self.action["independent_verification"] = self._signed_verification(
            task=self.task,
            status="failed",
            checks=[{"check_id": "parser-tests", "passed": False}],
        )
        result = self._record()
        self.assertEqual(result["independent_verification"], "failed")
        reflection = ExperienceReflectionStore(self.workspace, self.tenant_id).list_for_source(
            result["source_experience_id"]
        )[0]
        findings = reflection.metadata["experience_reflection"]["findings"]
        self.assertIn("independent check failed: parser-tests", findings["failure_causes"])
        self.assertTrue(findings["open_questions"])


if __name__ == "__main__":
    unittest.main()
