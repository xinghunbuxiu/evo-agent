"""Tests for tenant-scoped Worker mission plan generation."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_plan_ai_runtime import create_worker_mission_plan_proposer  # noqa: E402


class MissionPlanAiRuntimeTests(unittest.TestCase):
    def test_proposer_returns_structured_plan_and_does_not_send_provider_secrets(self):
        model_plan = {
            "title": "Python plan",
            "tasks": [{
                "id": "inspect",
                "title": "Inspect",
                "objective": "Inspect requirements",
                "task_type": "analyze",
                "capability_type": "python",
                "acceptance": "Requirements are explicit",
            }],
        }
        tenant_manager = object()
        with (
            mock.patch(
                "admin.mission_plan_ai_runtime.resolve_model_provider",
                return_value={
                    "enabled": True, "base_url": "https://model.example/v1",
                    "api_key": "private-secret", "model": "test-model",
                },
            ),
            mock.patch("admin.mission_plan_ai_runtime.model_provider_ready", return_value=True),
            mock.patch(
                "admin.mission_plan_ai_runtime.complete_chat",
                return_value={
                    "status": "completed",
                    "content": json.dumps(model_plan),
                    "provider_label": "test-provider",
                    "model": "test-model",
                },
            ) as complete,
        ):
            proposer = create_worker_mission_plan_proposer(tenant_manager)
            result = proposer(
                tenant_id="tenant-a",
                goal="Build a Python utility",
                context={
                    "work_type_id": "python-work",
                    "source_path": "src/input.py",
                    "api_key": "must-not-be-sent",
                    "access_token": "must-not-be-sent",
                    "dependency_replan": {
                        "schema_version": "untrusted-version",
                        "source_mission_run_id": "run-previous",
                        "required": True,
                        "decision_owner": "attacker",
                        "node_ids": ["node-a", " node-b ", ""],
                        "automatic_dispatch": True,
                        "api_key": "must-not-be-sent",
                    },
                },
                worker_manifest={
                    "worker_id": "python-worker",
                    "title": "Python Worker",
                    "capability_type": "python",
                    "task_types": ["analyze", "execute"],
                },
            )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["plan"], model_plan)
        sent = complete.call_args.kwargs["messages"][1]["content"]
        self.assertNotIn("must-not-be-sent", sent)
        self.assertNotIn("private-secret", sent)
        self.assertIn("python-worker", sent)
        sent_payload = json.loads(sent)
        self.assertEqual(sent_payload["task_context"]["dependency_replan"], {
            "schema_version": "mission.dependency.replan.request.v1",
            "source_mission_run_id": "run-previous",
            "required": True,
            "decision_owner": "mission",
            "node_ids": ["node-a", "node-b"],
            "automatic_dispatch": False,
        })
        self.assertNotIn("must-not-be-sent", sent)
        self.assertIn("不是派发授权", complete.call_args.kwargs["messages"][0]["content"])

    def test_proposer_rejects_non_json_model_output(self):
        with (
            mock.patch(
                "admin.mission_plan_ai_runtime.resolve_model_provider",
                return_value={"enabled": True, "base_url": "https://model.example/v1",
                              "api_key": "key", "model": "test-model"},
            ),
            mock.patch("admin.mission_plan_ai_runtime.model_provider_ready", return_value=True),
            mock.patch(
                "admin.mission_plan_ai_runtime.complete_chat",
                return_value={"status": "completed", "content": "not-json"},
            ),
        ):
            result = create_worker_mission_plan_proposer(object())(
                tenant_id="tenant-a",
                goal="Do work",
                context={},
                worker_manifest={"worker_id": "worker-a", "capability_type": "python"},
            )
        self.assertEqual(result["status"], "invalid_response")
        self.assertIsNone(result.get("plan"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
