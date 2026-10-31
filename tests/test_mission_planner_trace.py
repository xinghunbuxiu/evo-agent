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


    def test_matching_verified_strategy_is_recommended_and_traced_per_tenant(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            strategy_dir = workspace / ".tenants" / "test-tenant"
            strategy_dir.mkdir(parents=True)
            (strategy_dir / "strategies.json").write_text(
                __import__("json").dumps([{
                    "id": "floorplan-lines-first",
                    "name": "先识别墙线再推断房间",
                    "domain": "design",
                    "description": "先确认墙线、门窗，再归纳房间边界",
                    "applicable_when": ["户型图"],
                    "steps": [{"action": "识别墙线"}, {"action": "关联门窗"}],
                    "success_rate": 0.8,
                    "usage_count": 5,
                }], ensure_ascii=False),
                encoding="utf-8",
            )
            planner = MissionPlanner(workspace, registry=FakeRegistry())
            planner._knowledge_signals = mock.Mock(return_value={
                "experience_count": 0, "verified_skill_count": 0,
                "top_experience_ids": [], "top_verified_skill_ids": [],
            })
            planner._role_reflection_context = mock.Mock(return_value={})
            planner._match_verified_skills = mock.Mock(return_value=[])
            custom_templates = {
                "floorplan_review": {
                    "title": "Floorplan review",
                    "description": "Review a floorplan",
                    "primary_capability_type": "design",
                    "tasks": [{
                        "id": "inspect", "title": "Inspect floorplan",
                        "objective": "检查户型图墙线与门窗",
                        "task_type": "analyze", "capability_type": "design",
                        "acceptance": "结构结果可验证",
                    }],
                }
            }
            with mock.patch("core.mission_planner.load_worker_mission_kind_templates", return_value=custom_templates):
                result = planner.plan(
                    tenant_id="test-tenant",
                    goal="检查户型图并总结墙线识别方法",
                    mission_kind="floorplan_review",
                    context={"source_path": "plan.png"},
                )
            node = result["nodes"][0]
            self.assertEqual(node["recommended_strategies"][0]["id"], "floorplan-lines-first")
            self.assertIn("floorplan-lines-first", " ".join(node["next_actions"]))
            trace = {item["step"]: item for item in node["decision_trace"]}
            self.assertEqual(trace["strategy_retrieval"]["result"], "matched")
            self.assertEqual(trace["strategy_retrieval"]["evidence"]["tenant_id"], "test-tenant")

    def test_context_verification_contract_is_bound_to_matching_node(self):
        planner = self._planner()
        custom_templates = {
            "artifact_demo": {
                "title": "Artifact demo",
                "description": "Verify a declared artifact",
                "primary_capability_type": "automation",
                "tasks": [{
                    "id": "write_readme",
                    "title": "Write README",
                    "objective": "Create a README",
                    "task_type": "execute",
                    "capability_type": "automation",
                    "acceptance": "README exists",
                }, {
                    "id": "other_node",
                    "title": "Other",
                    "objective": "No artifact contract",
                    "task_type": "plan",
                    "capability_type": "automation",
                    "acceptance": "Plan",
                }],
            }
        }
        declared_contract = {
            "schema_version": "mission.verification.v1",
            "checks": [{
                "check_id": "readme_exists",
                "type": "file_exists",
                "path": "README.md",
            }],
        }
        with mock.patch("core.mission_planner.load_worker_mission_kind_templates", return_value=custom_templates):
            result = planner.plan(
                tenant_id="tenant-a",
                goal="Create and verify README",
                mission_kind="artifact_demo",
                context={"verification_contracts": {"write_readme": declared_contract}},
            )

        by_id = {node["id"]: node for node in result["nodes"]}
        self.assertEqual(by_id["write_readme"]["verification_contract"], declared_contract)
        self.assertEqual(by_id["other_node"]["verification_contract"], {})
        decisions = {item["node_id"]: item for item in result["orchestration"]["node_decisions"]}
        self.assertEqual(decisions["write_readme"]["verification_contract"], declared_contract)
        self.assertIsNone(decisions["other_node"]["verification_contract"])

    def test_invalid_template_contract_is_not_silently_replaced_by_context_contract(self):
        planner = self._planner()
        custom_templates = {
            "invalid_contract": {
                "title": "Invalid contract",
                "description": "Reject malformed declaration",
                "primary_capability_type": "automation",
                "tasks": [{
                    "id": "write_readme",
                    "title": "Write README",
                    "objective": "Create README",
                    "task_type": "execute",
                    "capability_type": "automation",
                    "acceptance": "README exists",
                    "verification_contract": "not-a-contract",
                }],
            }
        }
        valid_fallback = {
            "schema_version": "mission.verification.v1",
            "checks": [{"check_id": "exists", "type": "file_exists", "path": "README.md"}],
        }
        with mock.patch("core.mission_planner.load_worker_mission_kind_templates", return_value=custom_templates):
            with self.assertRaisesRegex(ValueError, "verification contract"):
                planner.plan(
                    tenant_id="tenant-a",
                    goal="Create README",
                    mission_kind="invalid_contract",
                    context={"verification_contracts": {"write_readme": valid_fallback}},
                )

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
        trace = {item["step"]: item for item in result["decision_trace"]}
        self.assertEqual(trace["dependency_graph_validation"]["rule_id"], "mission.dependency_graph.validated.v1")
        self.assertEqual(trace["dependency_graph_validation"]["evidence"]["dependency_edge_count"], 1)
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
            ["input_validation", "capability_match", "knowledge_check", "strategy_retrieval", "status_decision", "workforce_catalog_match"],
        )
        for item in node["decision_trace"]:
            self.assertTrue(item["rule_id"])
            self.assertIn("result", item)
            self.assertIsInstance(item["evidence"], dict)


if __name__ == "__main__":
    unittest.main()
