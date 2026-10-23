"""Mission remains the single authority for coordination and dispatch."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.mission_brain import build_mission_brain_contract  # noqa: E402


class MissionBrainCoordinationTests(unittest.TestCase):
    def test_contract_creates_central_actions_without_authorizing_dispatch(self):
        contract = build_mission_brain_contract([
            {
                "id": "missing-input",
                "status": "needs_input",
                "blockers": ["source_path"],
                "reasoning": [],
                "recommended_skill_ids": [],
                "validation_checks": [],
                "parallel_safe": False,
            },
            {
                "id": "worker-recommended",
                "status": "ready",
                "blockers": [],
                "reasoning": [],
                "recommended_skill_ids": [],
                "validation_checks": ["run-tests"],
                "parallel_safe": True,
                "workforce_decision": {
                    "decision": "assign_existing_worker_recommended",
                    "dispatch_state": "recommendation_only",
                    "recommended_worker_id": "worker-a",
                    "dispatch_authorized": False,
                },
            },
            {
                "id": "ready-node",
                "status": "ready",
                "blockers": [],
                "reasoning": [],
                "recommended_skill_ids": [],
                "validation_checks": [],
                "parallel_safe": False,
            },
            {
                "id": "learning-gap",
                "status": "needs_learning",
                "gap_type": "capability_gap",
                "blockers": [],
                "reasoning": [],
                "recommended_skill_ids": [],
                "validation_checks": [],
                "parallel_safe": False,
            },
        ])

        plan = contract["coordination_plan"]
        actions = {item["node_id"]: item for item in plan["actions"]}

        self.assertEqual(plan["schema_version"], "mission.coordination.v1")
        self.assertEqual(actions["missing-input"]["action"], "request_missing_input")
        self.assertEqual(actions["worker-recommended"]["action"], "await_dispatch_authorization")
        self.assertEqual(actions["ready-node"]["action"], "prepare_for_authorized_dispatch")
        self.assertEqual(actions["learning-gap"]["action"], "resolve_capability_or_learning_gap")
        self.assertTrue(actions["worker-recommended"]["parallel_safe"])
        self.assertEqual(plan["parallel_safe_node_ids"], ["worker-recommended"])
        self.assertEqual(plan["blocked_node_ids"], ["missing-input", "learning-gap"])
        self.assertFalse(plan["dispatch_authorized"])
        self.assertTrue(all(item["dispatch_authorized"] is False for item in plan["actions"]))
        self.assertEqual(plan["policy"], "never_dispatch_from_plan_recommendation_alone")

    def test_contract_accepts_mission_node_objects(self):
        class Node:
            def to_dict(self):
                return {
                    "id": "node-object",
                    "status": "needs_input",
                    "blockers": ["required-input"],
                    "reasoning": [],
                    "recommended_skill_ids": [],
                    "validation_checks": [],
                    "parallel_safe": True,
                }

        plan = build_mission_brain_contract([Node()])["coordination_plan"]
        self.assertEqual(plan["actions"][0]["node_id"], "node-object")
        self.assertTrue(plan["actions"][0]["parallel_safe"])


    def test_contract_rejects_missing_node_id_instead_of_silently_skipping(self):
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

    def test_contract_rejects_missing_decision_evidence(self):
        with self.assertRaisesRegex(ValueError, "requires list field 'decision_trace'"):
            build_mission_brain_contract([{
                "id": "missing-trace",
                "status": "ready",
                "reasoning": [],
                "blockers": [],
                "recommended_skill_ids": [],
                "validation_checks": [],
                "parallel_safe": False,
            }])


if __name__ == "__main__":
    unittest.main()
