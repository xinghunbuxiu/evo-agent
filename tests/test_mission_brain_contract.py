"""Regression tests for Mission's central-brain coordination contract."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.mission_brain import build_mission_brain_contract, index_mission_brain_decisions  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
