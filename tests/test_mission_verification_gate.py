"""Mission completion must respect explicit independent-verification contracts."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_execution_runtime import create_mission_execution_bindings


class MissionVerificationGateTests(unittest.TestCase):
    def _bindings(self, *, verifier=None, saved=None):
        saved = saved if saved is not None else {}

        def save_learning_tasks(workspace, payload):
            saved.update(payload)

        return create_mission_execution_bindings(
            load_learning_tasks=lambda workspace: {"tasks": saved.get("tasks", {})},
            save_learning_tasks=save_learning_tasks,
            collect_task_verified_skills=lambda *args, **kwargs: [],
            skill_ids_from_items=lambda items: [],
            infer_framework_hint_from_delivery=lambda *args, **kwargs: "",
            create_mission_delivery_skill_candidate=lambda *args, **kwargs: {},
            safe_float=lambda value, default=0.0: default,
            trim_candidate_text=lambda value, limit=280: str(value or "")[:limit],
            record_growth_event=lambda *args, **kwargs: None,
            build_snapshot_signature=lambda *args, **kwargs: {},
            normalize_string_list=lambda value: value if isinstance(value, list) else [],
            build_external_learning_plan=lambda **kwargs: {"preferred_sources": []},
            execute_learning_task=lambda **kwargs: {"task_id": "learning-verification-1", "status": "needs_learning"},
            make_learning_task_id=lambda tenant_id, sample: "learning-verification-generated",
            extract_task_snapshot=lambda *args, **kwargs: {},
            resolve_effective_growth_policy=lambda **kwargs: {},
            growth_policy_decision_label=lambda *args, **kwargs: "",
            effective_platform_promotion_status=lambda *args, **kwargs: "",
            independent_verifier=verifier,
        )

    def _refresh(self, *, verifier=None, contract=True):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            task = SimpleNamespace(
                id="task-verify-gate",
                type="execute",
                status=SimpleNamespace(value="success"),
                tenant_id="tenant-a",
                completed_at="2026-11-07T10:00:00",
                payload={"path": "deliverable.txt"},
                result={"summary": "worker execution finished"},
                error="",
            )

            class Queue:
                def get_task(self, task_id):
                    return task if task_id == task.id else None

            class TenantManager:
                def get_knowledge_policy(self, tenant_id):
                    return {}

            action = {
                "node_id": "node-verify",
                "title": "Verify deliverable",
                "action_type": "task_submitted",
                "task_type": "execute",
                "task_id": task.id,
                "status": "submitted",
                "decision_trace": [{"step": "plan", "result": "ready"}],
                "mission_runtime_authorization": {
                    "schema_version": "mission.dispatch.authorization.v1",
                    "authorized": True,
                },
            }
            if contract:
                action["verification_contract"] = {
                    "schema_version": "mission.verification.v1",
                    "checks": [{"check_id": "deliverable_exists", "type": "file_exists", "path": "deliverable.txt"}],
                }
            mission_run = {
                "mission_run_id": "mission-verification-gate",
                "tenant_id": "tenant-a",
                "goal": "deliver a verified artifact",
                "context": {"source_path": "deliverable.txt"},
                "actions": [action],
                "submitted_task_ids": [task.id],
            }
            bindings = self._bindings(verifier=verifier)
            refreshed = bindings["refresh_mission_run"](
                workspace=workspace,
                task_queue=Queue(),
                tenant_manager=TenantManager(),
                mission_run=mission_run,
                build_mission_next_cycle_plan=lambda run, actions: {"status": "pending", "next_steps": [], "focus_points": []},
                build_mission_growth_timeline=lambda actions: [],
            )
            return refreshed

    def test_required_contract_passes_only_with_independent_verifier_pass(self):
        def verifier(**kwargs):
            return {
                "verifier_id": "test-verifier",
                "verifier_version": "1",
                "checks": [{"check_id": "deliverable_exists", "passed": True}],
            }

        refreshed = self._refresh(verifier=verifier)
        action = next(item for item in refreshed["actions"] if item.get("action_type") == "task_submitted")
        self.assertEqual(action["execution_status"], "completed")
        self.assertEqual(action["verification_verdict"], "pass")
        self.assertEqual(action["status"], "completed")
        self.assertEqual(refreshed["status"], "completed")

    def test_required_contract_failure_does_not_complete_and_creates_learning_ticket(self):
        def verifier(**kwargs):
            return {
                "verifier_id": "test-verifier",
                "verifier_version": "1",
                "checks": [{"check_id": "deliverable_exists", "passed": False}],
            }

        refreshed = self._refresh(verifier=verifier)
        action = next(item for item in refreshed["actions"] if item.get("action_type") == "task_submitted")
        ticket = next(item for item in refreshed["actions"] if item.get("action_type") == "failure_learning_ticket")
        self.assertEqual(action["execution_status"], "completed")
        self.assertEqual(action["verification_verdict"], "fail")
        self.assertEqual(action["status"], "verification_failed")
        self.assertEqual(ticket["failure_kind"], "verification_failure")
        self.assertEqual(refreshed["status"], "needs_learning")

    def test_required_contract_without_verifier_remains_awaiting_verification(self):
        refreshed = self._refresh(verifier=None)
        action = next(item for item in refreshed["actions"] if item.get("action_type") == "task_submitted")
        self.assertEqual(action["execution_status"], "completed")
        self.assertEqual(action["verification_verdict"], "inconclusive")
        self.assertEqual(action["status"], "awaiting_verification")
        self.assertEqual(refreshed["status"], "awaiting_verification")

    def test_task_without_explicit_independent_contract_keeps_execution_completion_semantics(self):
        refreshed = self._refresh(verifier=None, contract=False)
        action = next(item for item in refreshed["actions"] if item.get("action_type") == "task_submitted")
        self.assertEqual(action["execution_status"], "completed")
        self.assertEqual(action["verification_verdict"], "not_required")
        self.assertEqual(action["status"], "completed")
        self.assertEqual(refreshed["status"], "completed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
