"""A deterministic end-to-end smoke test for Mission worker dispatch and result verification.

The worker adapter is intentionally a test double: this verifies the Mission runtime's
dispatch contract and evidence propagation, not LLM code generation or a production Python worker.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_action_runtime import create_mission_action_runtime_bindings  # noqa: E402
from core.mission_brain import build_mission_brain_contract  # noqa: E402


class FakePriority:
    HIGH = 1
    NORMAL = 2


class MissionSimpleTaskExecutionTests(unittest.TestCase):
    def test_dispatch_execute_verify_and_preserve_decision_evidence(self):
        trace = [
            {
                "step": "capability_match",
                "rule_id": "mission.capability_match.v1",
                "result": "matched",
                "evidence": {"capability_type": "python", "capability_ids": ["python-test-worker"]},
            },
            {
                "step": "status_decision",
                "rule_id": "mission.status.ready.v1",
                "result": "ready",
                "evidence": {"gap_type": None, "blocker_codes": []},
            },
        ]
        node = {
            "id": "implement_even_check",
            "title": "实现偶数判断函数",
            "task_type": "execute",
            "capability_type": "python",
            "status": "ready",
            "reasoning": ["使用取模运算判断整数奇偶"],
            "blockers": [],
            "recommended_skill_ids": [],
            "recommended_skills": [],
            "recommended_strategies": [],
            "validation_checks": [
                "验证正偶数、正奇数、负数和零",
                "所有断言通过后才报告成功",
            ],
            "decision_trace": trace,
            "parallel_safe": False,
            "workforce_decision": {
                "decision": "assign_existing_worker_recommended",
                "recommended_worker_id": "python-test-worker",
                "required_capabilities": ["python"],
                "dispatch_state": "recommendation_only",
                "dispatch_authorized": False,
            },
        }
        evidence = {}

        def deterministic_python_worker(**kwargs):
            # Test-only adapter: execute a small implementation and validate edge cases.
            code = (
                "def is_even(value):\\n"
                "    if not isinstance(value, int):\\n"
                "        raise TypeError('value must be an integer')\\n"
                "    return value % 2 == 0\\n"
                "assert is_even(2) is True\\n"
                "assert is_even(3) is False\\n"
                "assert is_even(-4) is True\\n"
                "assert is_even(-3) is False\\n"
                "assert is_even(0) is True\\n"
            )
            namespace = {}
            exec(compile(code, "<mission-test-worker>", "exec"), namespace)
            evidence["checks"] = {
                "2": namespace["is_even"](2),
                "3": namespace["is_even"](3),
                "-4": namespace["is_even"](-4),
                "-3": namespace["is_even"](-3),
                "0": namespace["is_even"](0),
            }
            evidence["passed"] = (
                evidence["checks"] == {"2": True, "3": False, "-4": True, "-3": False, "0": True}
            )
            kwargs["append_action"](
                node_id=kwargs["node"]["id"],
                title=kwargs["node"]["title"],
                action_type="test_worker_execution",
                status="completed" if evidence["passed"] else "failed",
                detail="Python smoke test executed and assertions evaluated",
                extra={"execution_evidence": dict(evidence)},
            )
            return evidence["passed"]

        orchestration = build_mission_brain_contract([node])
        bindings = create_mission_action_runtime_bindings(
            normalize_string_list=lambda value: (
                [str(item) for item in value if str(item).strip()]
                if isinstance(value, list) else []
            ),
            task_priority_cls=FakePriority,
            mission_action_handlers={"python-test-worker": deterministic_python_worker},
        )
        result = bindings["build_mission_actions"](
            task_queue=object(),
            tenant_id="demo-tenant",
            mission_run_id="mission-even-number",
            plan={
                "goal": "写一个 Python 函数判断整数是否为偶数，并说明如何验证结果",
                "mission_kind": "even_number_demo",
                "runtime_route": {"primary_worker_id": "python-test-worker"},
                "nodes": [node],
                "orchestration": orchestration,
            },
            context={},
            work_type={},
            work_type_summary={"deliverables": ["is_even 函数及验证证据"]},
        )

        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["checks"], {"2": True, "3": False, "-4": True, "-3": False, "0": True})
        self.assertEqual(len(result["actions"]), 1)
        action = result["actions"][0]
        self.assertEqual(action["action_type"], "test_worker_execution")
        self.assertEqual(action["status"], "completed")
        self.assertEqual(action["decision_trace"], trace)
        self.assertTrue(action["mission_runtime_authorization"]["authorized"])
        self.assertEqual(action["execution_evidence"]["checks"]["-4"], True)
        self.assertEqual(action["execution_evidence"]["checks"]["-3"], False)


if __name__ == "__main__":
    unittest.main()
