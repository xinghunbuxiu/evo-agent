"""Regression tests for Mission's central-brain coordination contract."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.mission_brain import build_mission_brain_contract, index_mission_brain_decisions  # noqa: E402
from core.mission_planner import MissionPlanner  # noqa: E402
from core.organization_runtime import OrganizationRegistry  # noqa: E402


class MissionBrainContractTests(unittest.TestCase):
    def test_mission_is_single_dispatch_authority_and_knowledge_is_reused_first(self):
        contract = build_mission_brain_contract([
            {
                "id": "reuse",
                "status": "reuse_existing",
                "gap_type": "reuse_existing",
                "reasoning": [],
                "blockers": [],
                "recommended_skill_ids": ["skill-verified"],
                "validation_checks": [],
                "decision_trace": [{"step": "knowledge_check", "result": "available"}],
                "parallel_safe": False,
            },
            {
                "id": "learn",
                "status": "needs_learning",
                "gap_type": "capability_gap",
                "reasoning": [],
                "blockers": [],
                "recommended_skill_ids": [],
                "validation_checks": ["run regression"],
                "decision_trace": [],
                "parallel_safe": False,
            },
            {
                "id": "input",
                "status": "needs_input",
                "reasoning": [],
                "blockers": ["source_path"],
                "recommended_skill_ids": [],
                "validation_checks": [],
                "decision_trace": [],
                "parallel_safe": False,
            },
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

    def test_contract_rejects_invalid_nodes_and_preserves_trace_for_valid_node(self):
        with self.assertRaisesRegex(ValueError, "must be an object"):
            build_mission_brain_contract([None])

        with self.assertRaisesRegex(ValueError, "requires a non-empty id"):
            build_mission_brain_contract([{
                "status": "ready",
                "reasoning": [],
                "blockers": [],
                "recommended_skill_ids": [],
                "validation_checks": [],
                "decision_trace": [],
                "parallel_safe": False,
            }])

        trace = [{"step": "capability_match", "result": "matched"}]
        contract = build_mission_brain_contract([{
            "id": "node-a",
            "status": "ready",
            "gap_type": "knowledge_gap",
            "reasoning": [],
            "blockers": [],
            "recommended_skill_ids": [],
            "validation_checks": [],
            "decision_trace": trace,
            "parallel_safe": False,
        }])
        self.assertEqual(len(contract["node_decisions"]), 1)
        self.assertEqual(contract["node_decisions"][0]["decision"], "run_minimal_validating_experiment")
        self.assertEqual(contract["node_decisions"][0]["decision_trace"], trace)


    def test_action_runtime_carries_brain_decision_into_execution_record(self):
        from admin.mission_action_runtime import create_mission_action_runtime_bindings

        trace = [{"step": "knowledge_check", "result": "available"}]
        verification_contract = {
            "schema_version": "mission.verification.v1",
            "checks": [{"check_id": "readme_exists", "type": "file_exists", "path": "README.md"}],
        }
        contract = build_mission_brain_contract([{
            "id": "node-reuse",
            "verification_contract": verification_contract,
            "status": "reuse_existing",
            "gap_type": "reuse_existing",
            "reasoning": [],
            "blockers": [],
            "recommended_skill_ids": ["skill-a"],
            "validation_checks": ["run tests"],
            "decision_trace": trace,
            "parallel_safe": False,
            "workforce_decision": {
                "decision": "assign_existing_worker_recommended",
                "recommended_worker_id": "worker-a",
                "dispatch_authorized": False,
                "dispatch_state": "recommendation_only",
            },
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
                    "blockers": [],
                    "recommended_skill_ids": ["skill-a"],
                    "recommended_skills": [],
                    "validation_checks": ["run tests"],
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
        self.assertEqual(action["verification_contract"], verification_contract)
        self.assertEqual(action["workforce_decision"]["recommended_worker_id"], "worker-a")
        self.assertFalse(action["workforce_dispatch_authorized"])

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
                context={
                    "channel": "internal",
                    "deliverable_goal": "build and verify a reusable project workflow",
                },
            )

        contract = plan["orchestration"]
        self.assertEqual(contract["schema_version"], "mission.brain.contract.v1")
        self.assertEqual(contract["decision_owner"], "mission")
        self.assertEqual(
            [item["node_id"] for item in contract["node_decisions"]],
            [item["id"] for item in plan["nodes"]],
        )
        self.assertTrue(contract["workforce_policy"]["dynamic_dispatch_enabled"])
        self.assertTrue(contract["workforce_policy"]["atomic_claim_required_before_handler"])
        self.assertEqual(
            contract["workforce_policy"]["automatic_worker_creation"],
            "existing_role_and_compatible_handler_only",
        )
        self.assertFalse(contract["workforce_policy"]["automatic_role_creation"])
        self.assertTrue(all(
            item["workforce_decision"]["decision"] == "catalog_unavailable"
            for item in plan["nodes"]
        ))

    def test_planner_uses_organization_catalog_but_only_recommends_dispatch(self):
        class EmptyRegistry:
            def list_descriptors(self):
                return []

        with tempfile.TemporaryDirectory() as tmp:
            organization = OrganizationRegistry(Path(tmp))
            organization.create_role(
                role_id="android-role", title="Android Specialist",
                responsibilities=["plan", "execute"],
                required_capabilities=["android", "kotlin"],
            )
            organization.create_worker(
                worker_id="android-a", role_id="android-role",
                profile={"skills": ["workflow"]},
            )
            planner = MissionPlanner(Path(tmp), registry=EmptyRegistry())
            plan = planner.plan(
                tenant_id="tenant-a",
                goal="Build a reusable project workflow",
                mission_kind="automation_operation",
                context={
                    "required_capabilities": ["android", "kotlin"],
                    "channel": "internal",
                    "deliverable_goal": "build and verify a reusable project workflow",
                },
            )

        first = plan["nodes"][0]["workforce_decision"]
        self.assertEqual(first["decision"], "assign_existing_worker_recommended")
        self.assertEqual(first["recommended_worker_id"], "android-a")
        self.assertFalse(first["dispatch_authorized"])
        self.assertEqual(first["dispatch_state"], "recommendation_only")
        self.assertEqual(
            plan["orchestration"]["node_decisions"][0]["workforce_decision"],
            first,
        )
        self.assertEqual(
            plan["orchestration"]["workforce_policy"]["decision_counts"]["assign_existing_worker_recommended"],
            1,
        )
        self.assertTrue(plan["orchestration"]["workforce_policy"]["dynamic_dispatch_enabled"])
        self.assertTrue(plan["orchestration"]["workforce_policy"]["release_after_all_linked_tasks_terminal"])


if __name__ == "__main__":
    unittest.main()
