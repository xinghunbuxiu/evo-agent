"""Single-flow integration test for Mission execution, strategy feedback, and reuse.

The worker is deterministic and test-only. This proves evidence continuity and persistence
across the runtime/feedback/planner boundaries; it does not claim production AI execution.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_action_runtime import create_mission_action_runtime_bindings  # noqa: E402
from admin.mission_execution_runtime import create_mission_execution_bindings  # noqa: E402
from core.learning import Strategy, StrategyEngine  # noqa: E402
from core.mission_brain import build_mission_brain_contract  # noqa: E402
from core.mission_planner import MissionPlanner  # noqa: E402


class FakePriority:
    HIGH = 1
    NORMAL = 2


class EmptyRegistry:
    def list_descriptors(self):
        return []


def build_feedback_bindings():
    return create_mission_execution_bindings(
        load_learning_tasks=lambda workspace: {"tasks": {}},
        save_learning_tasks=lambda workspace, payload: None,
        collect_task_verified_skills=lambda *args, **kwargs: [],
        skill_ids_from_items=lambda items: [],
        infer_framework_hint_from_delivery=lambda *args, **kwargs: "",
        create_mission_delivery_skill_candidate=lambda *args, **kwargs: {},
        safe_float=lambda value, default=0.0: default,
        trim_candidate_text=lambda value, limit=280: str(value or "")[:limit],
        record_growth_event=lambda *args, **kwargs: None,
        build_snapshot_signature=lambda *args, **kwargs: {},
        normalize_string_list=lambda value: value if isinstance(value, list) else [],
        build_external_learning_plan=lambda **kwargs: {},
        execute_learning_task=lambda **kwargs: {},
        make_learning_task_id=lambda tenant_id, sample: "learning",
        extract_task_snapshot=lambda *args, **kwargs: {},
        resolve_effective_growth_policy=lambda **kwargs: {},
        growth_policy_decision_label=lambda *args, **kwargs: "",
        effective_platform_promotion_status=lambda *args, **kwargs: "",
    )["record_strategy_execution_feedback"]


class MissionExecutionLearningE2ETests(unittest.TestCase):
    def test_one_task_execution_feedback_restart_and_next_plan_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            tenant_id = "tenant-e2e"
            strategy = StrategyEngine(workspace, tenant_id=tenant_id)
            strategy.strategies.append(Strategy(
                id="strategy-even-python",
                name="Python integer parity checks",
                domain="python",
                description="Use modulo and verify positive, negative, and zero inputs.",
                applicable_when=["parity"],
                steps=[{"action": "implement"}, {"action": "run assertions"}],
                success_rate=1.0,
                usage_count=1,
            ))
            strategy._save_strategies()

            trace = [
                {
                    "step": "strategy_retrieval",
                    "rule_id": "mission.strategy_retrieval.v1",
                    "result": "matched",
                    "evidence": {"strategy_ids": ["strategy-even-python"], "tenant_id": tenant_id},
                },
                {
                    "step": "status_decision",
                    "rule_id": "mission.status.ready.v1",
                    "result": "ready",
                    "evidence": {"blocker_codes": []},
                },
            ]
            node = {
                "id": "implement_even_check",
                "title": "Implement and test is_even",
                "task_type": "execute",
                "capability_type": "python",
                "status": "ready",
                "reasoning": ["Apply modulo and verify edge cases."],
                "blockers": [],
                "recommended_skill_ids": [],
                "recommended_skills": [],
                "recommended_strategies": [{
                    "id": "strategy-even-python",
                    "name": "Python integer parity checks",
                }],
                "validation_checks": ["Assertions pass for positive, negative, and zero."],
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
            runtime_evidence = {}

            def deterministic_worker(**kwargs):
                code = (
                    "def is_even(value):\n"
                    "    if not isinstance(value, int):\n"
                    "        raise TypeError('value must be an integer')\n"
                    "    return value % 2 == 0\n"
                    "assert is_even(2) is True\n"
                    "assert is_even(3) is False\n"
                    "assert is_even(-4) is True\n"
                    "assert is_even(-3) is False\n"
                    "assert is_even(0) is True\n"
                )
                namespace = {}
                exec(compile(code, "<mission-e2e-test-worker>", "exec"), namespace)
                checks = {
                    "2": namespace["is_even"](2),
                    "3": namespace["is_even"](3),
                    "-4": namespace["is_even"](-4),
                    "-3": namespace["is_even"](-3),
                    "0": namespace["is_even"](0),
                }
                runtime_evidence.update({
                    "passed": checks == {"2": True, "3": False, "-4": True, "-3": False, "0": True},
                    "checks": checks,
                    "strategy_usage": {
                        "strategy_id": "strategy-even-python",
                        "strategy_used": True,
                        # This is a worker claim, not independent verification evidence.
                        "verification_passed": True,
                        "domain": "python",
                    },
                })
                kwargs["append_action"](
                    actions=kwargs["actions"],
                    node_id=kwargs["node"]["id"],
                    title=kwargs["node"]["title"],
                    action_type="test_worker_execution",
                    status="completed" if runtime_evidence["passed"] else "failed",
                    detail="Deterministic Python assertions executed.",
                    matched_skill_ids=kwargs["matched_skill_ids"],
                    matched_skills=kwargs["matched_skills"],
                    work_type=kwargs["work_type"],
                    work_type_summary=kwargs["work_type_summary"],
                    extra={"execution_evidence": dict(runtime_evidence),
                           "strategy_usage": dict(runtime_evidence["strategy_usage"])},
                )
                return runtime_evidence["passed"]

            runtime = create_mission_action_runtime_bindings(
                normalize_string_list=lambda value: (
                    [str(item) for item in value if str(item).strip()]
                    if isinstance(value, list) else []
                ),
                task_priority_cls=FakePriority,
                mission_action_handlers={"python-test-worker": deterministic_worker},
            )
            dispatched = runtime["build_mission_actions"](
                task_queue=object(),
                tenant_id=tenant_id,
                mission_run_id="mission-e2e-even",
                plan={
                    "goal": "Implement and test a Python integer parity function",
                    "mission_kind": "even_number_demo",
                    "runtime_route": {"primary_worker_id": "python-test-worker"},
                    "nodes": [node],
                    "orchestration": build_mission_brain_contract([node]),
                },
                context={},
                work_type={},
                work_type_summary={"deliverables": ["is_even and assertion evidence"]},
            )

            self.assertTrue(runtime_evidence["passed"])
            self.assertEqual(len(dispatched["actions"]), 1)
            action = dispatched["actions"][0]
            self.assertTrue(action["mission_runtime_authorization"]["authorized"])
            self.assertEqual(action["decision_trace"], trace)
            self.assertEqual(action["recommended_strategies"][0]["id"], "strategy-even-python")
            self.assertEqual(action["execution_evidence"]["checks"]["-4"], True)

            # Feed back the exact strategy-usage evidence produced by the dispatched action.
            task = SimpleNamespace(
                id="task-even-e2e",
                result={
                    "summary": "is_even passed all five assertions",
                    "strategy_usage": action["strategy_usage"],
                },
                error="",
            )
            feedback = build_feedback_bindings()
            self.assertTrue(feedback(
                workspace=workspace, tenant_id=tenant_id, action=action,
                task=task, execution_success=True,
            ))
            self.assertFalse(feedback(
                workspace=workspace, tenant_id=tenant_id, action=action,
                task=task, execution_success=True,
            ))
            self.assertEqual(action["strategy_feedback_task_id"], "task-even-e2e")
            self.assertEqual(action["strategy_feedback"]["verification_claim"], {
                "passed": True, "source": "worker_reported_unverified",
            })
            self.assertNotIn("verification_passed", action["strategy_feedback"])

            # Fresh engine = process restart; persisted feedback must not count twice.
            restarted = StrategyEngine(workspace, tenant_id=tenant_id)
            persisted = next(item for item in restarted.strategies if item.id == "strategy-even-python")
            self.assertEqual(persisted.usage_count, 2)
            self.assertEqual(persisted.feedback_task_ids, ["task-even-e2e"])

            planner = MissionPlanner(workspace, registry=EmptyRegistry())
            planner._knowledge_signals = mock.Mock(return_value={
                "experience_count": 0,
                "verified_skill_count": 0,
                "top_experience_ids": [],
                "top_verified_skill_ids": [],
            })
            planner._role_reflection_context = mock.Mock(return_value={})
            planner._match_verified_skills = mock.Mock(return_value=[])
            templates = {
                "repeat_task": {
                    "title": "Repeat task",
                    "description": "Repeat the same kind of Python analysis",
                    "primary_capability_type": "python",
                    "tasks": [{
                        "id": "repeat",
                        "title": "Implement parity check again",
                        "objective": "Implement and validate integer parity",
                        "task_type": "execute",
                        "capability_type": "python",
                        "acceptance": "Assertions pass for positive, negative, and zero.",
                    }],
                }
            }
            with mock.patch("core.mission_planner.load_worker_mission_kind_templates", return_value=templates):
                next_plan = planner.plan(
                    tenant_id=tenant_id,
                    goal="Implement and validate integer parity again",
                    mission_kind="repeat_task",
                    context={},
                )

            next_node = next_plan["nodes"][0]
            self.assertEqual(next_node["recommended_strategies"][0]["id"], "strategy-even-python")
            next_trace = {item["step"]: item for item in next_node["decision_trace"]}
            self.assertEqual(next_trace["strategy_retrieval"]["result"], "matched")
            self.assertEqual(
                next_trace["strategy_retrieval"]["evidence"]["tenant_id"], tenant_id
            )
            final_strategy = next(
                item for item in StrategyEngine(workspace, tenant_id=tenant_id).strategies
                if item.id == "strategy-even-python"
            )
            self.assertEqual(final_strategy.usage_count, 2)
            self.assertEqual(final_strategy.feedback_task_ids, ["task-even-e2e"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
