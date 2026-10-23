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

    def test_plan_level_trace_explains_template_selection_and_version(self):
        planner = self._planner()
        result = planner.plan(
            tenant_id="test-tenant",
            goal="automation task",
            context={"channel": "test-channel", "deliverable_goal": "test output"},
        )

        self.assertEqual(result["plan_version"], "mission.plan.v1")
        trace = {item["step"]: item for item in result["decision_trace"]}
        self.assertEqual(trace["mission_kind_resolution"]["rule_id"], "mission.kind_resolution.v1")
        self.assertEqual(trace["mission_kind_resolution"]["result"], "automation_operation")
        self.assertEqual(trace["mission_kind_resolution"]["evidence"]["resolution_source"], "default_template")
        self.assertEqual(trace["plan_assembly"]["rule_id"], "mission.plan_assembly.v1")
        self.assertGreater(trace["plan_assembly"]["evidence"]["node_count"], 0)

    def test_template_dependency_graph_is_preserved_and_validated(self):
        planner = self._planner()
        custom_templates = {
            "dependency_demo": {
                "title": "Dependency demo",
                "description": "Validates dependency order",
                "primary_capability_type": "design",
                "tasks": [
                    {"id": "inspect", "title": "Inspect", "objective": "Inspect", "task_type": "analyze", "capability_type": "design", "acceptance": "Findings"},
                    {"id": "build", "title": "Build", "objective": "Build", "task_type": "execute", "capability_type": "design", "acceptance": "Output", "depends_on": ["inspect"]},
                ],
            }
        }
        with mock.patch("core.mission_planner.load_worker_mission_kind_templates", return_value=custom_templates):
            result = planner.plan(tenant_id="test-tenant", goal="dependency test", mission_kind="dependency_demo", context={})
        self.assertEqual(result["dependency_graph"], {"inspect": [], "build": ["inspect"]})
        self.assertEqual(next(item for item in result["nodes"] if item["id"] == "build")["depends_on"], ["inspect"])

    def test_template_dependency_cycle_fails_before_plan_is_built(self):
        planner = self._planner()
        custom_templates = {
            "dependency_cycle": {
                "title": "Dependency cycle",
                "description": "Invalid dependency cycle",
                "primary_capability_type": "design",
                "tasks": [
                    {"id": "a", "title": "A", "objective": "A", "task_type": "analyze", "capability_type": "design", "acceptance": "A", "depends_on": ["b"]},
                    {"id": "b", "title": "B", "objective": "B", "task_type": "execute", "capability_type": "design", "acceptance": "B", "depends_on": ["a"]},
                ],
            }
        }
        with mock.patch("core.mission_planner.load_worker_mission_kind_templates", return_value=custom_templates):
            with self.assertRaisesRegex(ValueError, "dependency cycle detected"):
                planner.plan(tenant_id="test-tenant", goal="dependency test", mission_kind="dependency_cycle", context={})

    def test_unknown_requested_kind_fails_explicitly_instead_of_falling_back(self):
        planner = self._planner()
        with self.assertRaisesRegex(ValueError, "Unsupported mission_kind: unregistered_kind"):
            planner.plan(
                tenant_id="test-tenant",
                goal="automation task",
                mission_kind="unregistered_kind",
                context={"channel": "test-channel", "deliverable_goal": "test output"},
            )

    def test_unknown_context_kind_fails_explicitly_instead_of_falling_back(self):
        planner = self._planner()
        with self.assertRaisesRegex(ValueError, "Unsupported context mission_kind: unregistered_kind"):
            planner.plan(
                tenant_id="test-tenant",
                goal="automation task",
                context={
                    "mission_kind": "unregistered_kind",
                    "channel": "test-channel",
                    "deliverable_goal": "test output",
                },
            )

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
            ["input_validation", "capability_match", "knowledge_check", "status_decision", "workforce_catalog_match"],
        )
        for item in node["decision_trace"]:
            self.assertTrue(item["rule_id"])
            self.assertIn("result", item)
            self.assertIsInstance(item["evidence"], dict)


if __name__ == "__main__":
    unittest.main()
