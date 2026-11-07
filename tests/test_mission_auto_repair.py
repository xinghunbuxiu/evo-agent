"""Tests for policy-gated, bounded Mission repair cycles."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_runtime import (
    derive_repair_context,
    refresh_mission_runs,
    save_mission_runs,
    should_auto_repair_mission,
)
from core.tenant import TenantManager


class MissionAutoRepairTests(unittest.TestCase):
    def _failed_run(self, context=None):
        return {
            "mission_run_id": "mission-root",
            "tenant_id": "tenant-a",
            "goal": "Build and verify a Python utility",
            "status": "needs_learning",
            "context": dict(context or {}),
            "runtime_route": {"primary_worker_id": "python-worker"},
            "work_type": {"work_type_id": "python-work"},
            "mission_kind": "python-worker",
            "actions": [{
                "node_id": "implement",
                "title": "Implement utility",
                "action_type": "task_submitted",
                "task_id": "task-failed-1",
                "status": "verification_failed",
                "execution_status": "completed",
                "verification_state": "failed",
                "detail": "Expected output file was missing",
                "acceptance": "Output file exists and passes assertions",
                "task_result": {"summary": "Worker wrote implementation but missed output"},
                "independent_verification": {
                    "status": "failed",
                    "checks": [
                        {"check_id": "output_exists", "passed": False},
                        {"check_id": "syntax_valid", "passed": True},
                    ],
                },
            }, {
                "node_id": "implement",
                "action_type": "failure_learning_ticket",
                "status": "needs_learning",
            }],
        }

    def test_auto_repair_is_disabled_by_default_and_requires_finite_budget(self):
        run = self._failed_run()
        self.assertFalse(should_auto_repair_mission(run, {
            "auto_repair_enabled": False,
            "max_repair_attempts": 3,
        }))
        self.assertTrue(should_auto_repair_mission(run, {
            "auto_repair_enabled": True,
            "max_repair_attempts": 2,
        }))
        exhausted = self._failed_run({"repair_attempt_count": 2})
        self.assertFalse(should_auto_repair_mission(exhausted, {
            "auto_repair_enabled": True,
            "max_repair_attempts": 2,
        }))

    def test_auto_repair_waits_for_all_tasks_and_does_not_duplicate(self):
        active = self._failed_run()
        active["actions"].append({
            "node_id": "other",
            "action_type": "task_submitted",
            "status": "running",
        })
        policy = {"auto_repair_enabled": True, "max_repair_attempts": 2}
        self.assertFalse(should_auto_repair_mission(active, policy))
        duplicate = self._failed_run()
        duplicate["auto_repair_triggered_run_id"] = "mission-repair-1"
        self.assertFalse(should_auto_repair_mission(duplicate, policy))

    def test_repair_context_preserves_failure_facts_and_attempt_lineage(self):
        run = self._failed_run({"autonomy_session_id": "session-1"})
        context = derive_repair_context(run)
        self.assertEqual(context["repair_mode"], "fix_test")
        self.assertEqual(context["repair_attempt_count"], 1)
        self.assertEqual(context["repair_of_mission_run_id"], "mission-root")
        self.assertEqual(context["repair_failure_evidence"][0]["failure_kind"], "verification_failure")
        self.assertEqual(context["repair_failure_evidence"][0]["verification_checks"][0], {
            "check_id": "output_exists", "passed": False,
        })
        self.assertEqual(context["root_mission_run_id"], "mission-root")
        self.assertEqual(context["previous_mission_run_id"], "mission-root")

    def test_refresh_starts_one_repair_child_and_marks_parent_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            parent = self._failed_run()
            save_mission_runs(workspace, {"items": [parent]})
            manager = TenantManager(workspace)
            manager.set_external_learning_policy(
                "tenant-a",
                allow_ai_assist=True,
                allow_web_research=True,
                allow_enterprise_sources=True,
                source_priority=["local_memory", "ai_assist"],
                validation_required=True,
                model_provider={
                    "enabled": True,
                    "base_url": "https://model.example/v1",
                    "api_key": "test-only-key",
                    "model": "test-model",
                },
                auto_repair_enabled=True,
                max_repair_attempts=2,
            )
            started = []

            def start_child(payload, refresh_runs=False):
                started.append(payload)
                return ({
                    "mission_run_id": "mission-repair-1",
                    "tenant_id": "tenant-a",
                    "status": "running",
                    "context": payload["context"],
                    "actions": [],
                }, None)

            result = refresh_mission_runs(
                workspace=workspace,
                task_queue=object(),
                tenant_manager=manager,
                refresh_runtime_learning_tasks=lambda **kwargs: {},
                refresh_mission_run=lambda **kwargs: kwargs["mission_run"],
                mission_starter=start_child,
            )
            self.assertEqual(len(started), 1)
            self.assertEqual(started[0]["context"]["repair_attempt_count"], 1)
            self.assertEqual(started[0]["context"]["repair_failure_evidence"][0]["failure_kind"], "verification_failure")
            items = result["items"]
            child = next(item for item in items if item["mission_run_id"] == "mission-repair-1")
            updated_parent = next(item for item in items if item["mission_run_id"] == "mission-root")
            self.assertEqual(child["auto_repair_source_mission_run_id"], "mission-root")
            self.assertEqual(child["repair_attempt_number"], 1)
            self.assertEqual(updated_parent["auto_repair_triggered_run_id"], "mission-repair-1")
            self.assertEqual(updated_parent["auto_repair_status"], "triggered")

    def test_refresh_does_not_auto_repair_without_ai_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            save_mission_runs(workspace, {"items": [self._failed_run()]})
            manager = TenantManager(workspace)
            manager.set_external_learning_policy(
                "tenant-a",
                allow_ai_assist=True,
                allow_web_research=True,
                allow_enterprise_sources=True,
                source_priority=["local_memory"],
                validation_required=True,
                auto_repair_enabled=True,
                max_repair_attempts=2,
            )
            started = []
            result = refresh_mission_runs(
                workspace=workspace,
                task_queue=object(),
                tenant_manager=manager,
                refresh_runtime_learning_tasks=lambda **kwargs: {},
                refresh_mission_run=lambda **kwargs: kwargs["mission_run"],
                mission_starter=lambda payload, refresh_runs=False: (started.append(payload) or {}, None),
            )
            self.assertEqual(started, [])
            parent = result["items"][0]
            self.assertEqual(parent["auto_repair_status"], "blocked")
            self.assertEqual(
                parent["auto_repair_block_reason"],
                "ai_planning_provider_unavailable_or_disabled",
            )

    def test_tenant_policy_persists_opt_in_and_attempt_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = TenantManager(Path(tmp))
            policy = manager.get_external_learning_policy("tenant-a")
            self.assertFalse(policy["auto_repair_enabled"])
            self.assertEqual(policy["max_repair_attempts"], 0)
            manager.set_external_learning_policy(
                "tenant-a",
                allow_ai_assist=True,
                allow_web_research=True,
                allow_enterprise_sources=True,
                source_priority=["local_memory"],
                validation_required=True,
                auto_repair_enabled=True,
                max_repair_attempts=3,
            )
            saved = manager.get_external_learning_policy("tenant-a")
            self.assertTrue(saved["auto_repair_enabled"])
            self.assertEqual(saved["max_repair_attempts"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
