"""Mission terminal task observations automatically create pending Reflections."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_task_reflection_runtime import record_mission_task_reflection
from core.experience_reflection import ExperienceReflectionStore
from core.learning import ExperienceStore


class MissionTaskReflectionRuntimeTests(unittest.TestCase):
    def test_terminal_task_creates_idempotent_pending_reflection_with_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = SimpleNamespace(
                id="queue-task-1",
                status=SimpleNamespace(value="success"),
                completed_at="2026-11-17T08:00:00+08:00",
                updated_at="2026-11-17T08:00:00+08:00",
                created_at="2026-11-17T07:59:00+08:00",
                result={"summary": "Implemented and tested the parser."},
                error=None,
            )
            mission_run = {"mission_run_id": "mission-1"}
            action = {
                "tenant_id": "tenant-a",
                "mission_run_id": "mission-1",
                "node_id": "node-1",
                "title": "Implement parser",
                "task_type": "execute",
                "worker_id": "worker-1",
                "independent_verification": {
                    "source": "mission_independent_verifier",
                    "task_id": "queue-task-1",
                    "execution_event_id": "task-completion:queue-task-1:2026-11-17T08:00:00+08:00",
                    "verifier_id": "workspace-verifier",
                    "verifier_version": "1",
                    "status": "passed",
                    "checks": [{"check_id": "parser-tests", "passed": True}],
                },
            }
            first = record_mission_task_reflection(
                workspace=Path(tmp), tenant_id="tenant-a",
                mission_run=mission_run, action=action, task=task,
            )
            second = record_mission_task_reflection(
                workspace=Path(tmp), tenant_id="tenant-a",
                mission_run=mission_run, action=action, task=task,
            )
            self.assertEqual(first, second)
            self.assertEqual(first["status"], "created")
            self.assertEqual(first["review_state"], "pending")
            self.assertEqual(first["independent_verification"], "passed")

            source = next(
                item for item in ExperienceStore(Path(tmp), "tenant-a").load_by_domain("mission_task")
                if item.id == first["source_experience_id"]
            )
            self.assertEqual(source.metadata["task_id"], "queue-task-1")
            reflections = ExperienceReflectionStore(Path(tmp), "tenant-a").list_for_source(source.id)
            self.assertEqual(len(reflections), 1)
            payload = reflections[0].metadata["experience_reflection"]
            self.assertEqual(payload["state"], "pending")
            self.assertEqual(payload["author"], "mission-system")
            self.assertEqual(payload["source_experience_digest"], first["source_experience_digest"])
            self.assertIn("queue-task-1", payload["source_evidence_refs"])

    def test_cross_tenant_action_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = SimpleNamespace(
                id="queue-task-2",
                status=SimpleNamespace(value="failed"),
                completed_at="2026-11-17T08:00:00+08:00",
                result={},
                error="failed",
            )
            with self.assertRaisesRegex(ValueError, "tenant or run binding"):
                record_mission_task_reflection(
                    workspace=Path(tmp), tenant_id="tenant-a",
                    mission_run={"mission_run_id": "mission-2"},
                    action={
                        "tenant_id": "tenant-b",
                        "mission_run_id": "mission-2",
                        "node_id": "node-2",
                    },
                    task=task,
                )

    def test_non_terminal_task_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = SimpleNamespace(
                id="queue-task-3",
                status=SimpleNamespace(value="running"),
                completed_at=None,
                result={},
                error=None,
            )
            with self.assertRaisesRegex(ValueError, "terminal queue task"):
                record_mission_task_reflection(
                    workspace=Path(tmp), tenant_id="tenant-a",
                    mission_run={"mission_run_id": "mission-3"},
                    action={
                        "tenant_id": "tenant-a",
                        "mission_run_id": "mission-3",
                        "node_id": "node-3",
                    },
                    task=task,
                )


if __name__ == "__main__":
    unittest.main()
