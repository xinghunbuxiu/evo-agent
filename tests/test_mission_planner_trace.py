"""Regression tests for auditable mission-planner decisions.

The trace intentionally records rules and observable evidence, not private chain-of-thought.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.mission_planner import MissionPlanner  # noqa: E402


class FakeRegistry:
    def __init__(self, descriptors=()):
        self.descriptors = list(descriptors)

    def list_descriptors(self):
        return self.descriptors


class MissionPlannerTraceTests(unittest.TestCase):
    def _planner(self, descriptors=()):
        planner = MissionPlanner(Path(tempfile.gettempdir()), registry=FakeRegistry(descriptors))
        planner._knowledge_signals = mock.Mock(return_value={
            "experience_count": 0,
            "verified_skill_count": 0,
            "top_experience_ids": [],
            "top_verified_skill_ids": [],
        })
        planner._role_reflection_context = mock.Mock(return_value={})
        planner._match_verified_skills = mock.Mock(return_value=[])
        return planner

    def test_missing_source_input_is_traceable_to_blocker_rule(self):
        planner = self._planner()
        custom_templates = {
            "floorplan_review": {
                "title": "Floorplan review",
                "description": "Review an uploaded floorplan",
                "primary_capability_type": "design",
                "tasks": [{
                    "id": "inspect_plan",
                    "title": "Inspect plan",
                    "objective": "Inspect room and wall layout",
                    "task_type": "analyze",
                    "capability_type": "design",
                    "acceptance": "List structural findings",
                }],
            }
        }
        with mock.patch("core.mission_planner.load_worker_mission_kind_templates", return_value=custom_templates):
            result = planner.plan(
                tenant_id="test-tenant",
                goal="检查户型图结构并指出问题",
                mission_kind="floorplan_review",
                context={},
            )

        node = result["nodes"][0]
        self.assertEqual(node["status"], "needs_input")
        self.assertIn("source_path_or_source_dir", node["blockers"])
        trace = {item["step"]: item for item in node["decision_trace"]}
        self.assertEqual(trace["input_validation"]["rule_id"], "mission.required_inputs.v1")
        self.assertEqual(trace["input_validation"]["result"], "blocked")
        self.assertIn("source_path_or_source_dir", trace["input_validation"]["evidence"]["blocker_codes"])
        self.assertEqual(trace["status_decision"]["rule_id"], "mission.status.input_gap.v1")
        self.assertEqual(trace["status_decision"]["result"], "needs_input")

    def test_missing_capability_is_traceable_to_capability_gap_rule(self):
        planner = self._planner()
        result = planner.plan(
            tenant_id="test-tenant",
            goal="automation task",
            context={"channel": "test-channel", "deliverable_goal": "test output"},
        )

        node = next(item for item in result["nodes"] if item["id"] == "understand_goal")
        trace = {item["step"]: item for item in node["decision_trace"]}
        self.assertEqual(node["status"], "needs_learning")
        self.assertEqual(node["gap_type"], "capability_gap")
        self.assertEqual(trace["capability_match"]["result"], "missing")
        self.assertEqual(trace["capability_match"]["evidence"]["capability_ids"], [])
        self.assertEqual(trace["status_decision"]["rule_id"], "mission.status.capability_gap.v1")
        self.assertEqual(trace["status_decision"]["evidence"]["gap_type"], "capability_gap")

    def test_trace_has_stable_steps_and_machine_readable_evidence(self):
        planner = self._planner()
        result = planner.plan(
            tenant_id="test-tenant",
            goal="automation task",
            context={"channel": "test-channel", "deliverable_goal": "test output"},
        )
        node = result["nodes"][0]
        self.assertEqual(
            [item["step"] for item in node["decision_trace"]],
            ["input_validation", "capability_match", "knowledge_check", "status_decision"],
        )
        for item in node["decision_trace"]:
            self.assertTrue(item["rule_id"])
            self.assertIn("result", item)
            self.assertIsInstance(item["evidence"], dict)


if __name__ == "__main__":
    unittest.main()
