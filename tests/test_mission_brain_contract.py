"""Regression tests for Mission's central-brain coordination contract."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.mission_brain import build_mission_brain_contract, index_mission_brain_decisions  # noqa: E402
from core.mission_planner import MissionPlanner  # noqa: E402


class MissionBrainContractTests(unittest.TestCase):
    def test_mission_is_single_dispatch_authority_and_knowledge_is_reused_first(self):
        contract = build_mission_brain_contract([
            {
                "id": "reuse",
                "status": "reuse_existing",
                "gap_type": "reuse_existing",
                "recommended_skill_ids": ["skill-verified"],
                "decision_trace": [{"step": "knowledge_check", "result": "available"}],
            },
            {
                "id": "learn",
                "status": "needs_learning",
                "gap_type": "capability_gap",
                "blockers": [],
                "validation_checks": ["run regression"],
            },
            {"id": "input", "status": "needs_input", "blockers": ["source_path"]},
        ])

        self.assertEqual(contract["decision_owner"], "mission")
        self.assertEqual(contract["dispatch_mode"], "centralized")
        self.assertEqual(contract["worker_to_worker_dispatch"], "request_mission_coordination")
        self.assertEqual(contract["knowledge_policy"], "verified_reuse_before_new_research")
        self.assertEqual(contract["validation_policy"], "evidence_required_before_knowledge_promotion")
        decisions = index_mission_brain_decisions(contract)
        self.assertEqual(decisions["reuse"]["decision"], "reuse_verified_knowledge_first")
        self.assertEqual(decisions["reuse"]["verified_skill_ids"], ["skill-verified"])
        self.assertEqual(decisions["learn"]["decision"], "research_capability_gap")
        self.assertEqual(decisions["input"]["decision"], "request_missing_input")

    def test_contract_ignores_invalid_nodes_and_preserves_decision_trace(self):
        trace = [{"step": "capability_match", "result": "matched"}]
        contract = build_mission_brain_contract([
            None,
            {"status": "ready"},
            {"id": "node-a", "status": "ready", "gap_type": "knowledge_gap", "decision_trace": trace},
        ])
        self.assertEqual(len(contract["node_decisions"]), 1)
        self.assertEqual(contract["node_decisions"][0]["decision"], "run_minimal_validating_experiment")
        self.assertEqual(contract["node_decisions"][0]["decision_trace"], trace)


    def test_action_runtime_carries_brain_decision_into_execution_record(self):
        from admin.mission_action_runtime import create_mission_action_runtime_bindings

        trace = [{"step": "knowledge_check", "result": "available"}]
        contract = build_mission_brain_contract([{
            "id": "node-reuse",
            "status": "reuse_existing",
            "gap_type": "reuse_existing",
            "recommended_skill_ids": ["skill-a"],
            "validation_checks": ["run tests"],
            "decision_trace": trace,
        }])
        bindings = create_mission_action_runtime_bindings(
            normalize_string_list=lambda value: value if isinstance(value, list) else [],
            task_priority_cls=object,
        )
        result = bindings["build_mission_actions"](
            task_queue=None,
            tenant_id="tenant-a",
            mission_run_id="mission-a",
            plan={
                "orchestration": contract,
                "nodes": [{
                    "id": "node-reuse",
                    "title": "Reuse verified skill",
                    "task_type": "plan",
                    "status": "reuse_existing",
                    "capability_type": "automation",
                    "recommended_skill_ids": ["skill-a"],
                    "recommended_skills": [],
                    "decision_trace": trace,
                    "next_actions": ["reuse skill"],
                }],
            },
            context={},
            work_type={},
            work_type_summary={},
        )
        action = result["actions"][0]
        self.assertEqual(action["orchestration_owner"], "mission")
        self.assertEqual(action["dispatch_mode"], "centralized")
        self.assertEqual(action["mission_brain_decision"], "reuse_verified_knowledge_first")
        self.assertEqual(action["verified_skill_ids"], ["skill-a"])
        self.assertEqual(action["decision_trace"], trace)

    def test_mission_planner_embeds_central_brain_contract(self):
        class EmptyRegistry:
            def list_descriptors(self):
                return []

        with tempfile.TemporaryDirectory() as tmp:
            planner = MissionPlanner(Path(tmp), registry=EmptyRegistry())
            plan = planner.plan(
                tenant_id="tenant-a",
                goal="Build a reusable project workflow",
                mission_kind="automation_operation",
                context={},
            )

        contract = plan["orchestration"]
        self.assertEqual(contract["schema_version"], "mission.brain.contract.v1")
        self.assertEqual(contract["decision_owner"], "mission")
        self.assertEqual(
            [item["node_id"] for item in contract["node_decisions"]],
            [item["id"] for item in plan["nodes"]],
        )


if __name__ == "__main__":
    unittest.main()
