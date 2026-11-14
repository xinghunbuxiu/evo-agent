"""Visible, reproducible example of the mission analysis chain for a small coding task."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.mission_planner import MissionPlanner  # noqa: E402


class EmptyRegistry:
    def list_descriptors(self):
        return []


class MissionSimpleTaskAnalysisTests(unittest.TestCase):
    def test_trace_simple_even_number_function_task(self):
        goal = "写一个 Python 函数判断整数是否为偶数，并说明如何验证结果"
        template = {
            "even_number_demo": {
                "title": "Even number function",
                "description": "Implement and verify a tiny Python function",
                "primary_capability_type": "python",
                "tasks": [{
                    "id": "implement_even_check",
                    "title": "实现偶数判断函数",
                    "objective": "编写 is_even(value) 并覆盖偶数、奇数和负数测试",
                    "task_type": "execute",
                    "capability_type": "python",
                    "acceptance": "函数结果正确，测试覆盖偶数、奇数和负数",
                }],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            planner = MissionPlanner(Path(tmp), registry=EmptyRegistry())
            planner._knowledge_signals = mock.Mock(return_value={
                "experience_count": 0,
                "verified_skill_count": 0,
                "top_experience_ids": [],
                "top_verified_skill_ids": [],
            })
            planner._role_reflection_context = mock.Mock(return_value={})
            planner._match_verified_skills = mock.Mock(return_value=[])
            with mock.patch("core.mission_planner.load_worker_mission_kind_templates", return_value=template):
                plan = planner.plan(
                    tenant_id="demo-tenant",
                    goal=goal,
                    mission_kind="even_number_demo",
                    context={},
                )

        node = plan["nodes"][0]
        trace = [
            {
                "step": item.get("step"),
                "rule_id": item.get("rule_id"),
                "result": item.get("result"),
                "evidence": item.get("evidence"),
            }
            for item in node.get("decision_trace", [])
        ]
        report = {
            "task": goal,
            "plan_version": plan.get("plan_version"),
            "node": {
                "id": node.get("id"),
                "title": node.get("title"),
                "capability_type": node.get("capability_type"),
                "status": node.get("status"),
                "gap_type": node.get("gap_type"),
                "blockers": node.get("blockers"),
                "recommended_strategies": node.get("recommended_strategies"),
            },
            "decision_trace": trace,
            "execution_note": "This test exercises planning and trace generation only; it does not dispatch a worker or execute Python code.",
        }
        print("\nMISSION_SIMPLE_TASK_ANALYSIS=" + json.dumps(report, ensure_ascii=False, sort_keys=True))
        self.assertEqual(node["id"], "implement_even_check")
        self.assertTrue(trace)
        self.assertEqual([item["step"] for item in trace], [
            "input_validation", "capability_match", "knowledge_check",
            "strategy_retrieval", "status_decision", "workforce_catalog_match",
        ])
        self.assertIn(node["status"], {"ready", "needs_learning", "needs_input", "reuse_existing"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
