"""Mission strategy feedback must be explicit and idempotent."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_execution_runtime import create_mission_execution_bindings  # noqa: E402
from core.learning import Strategy, StrategyEngine  # noqa: E402


def build_bindings():
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
    )


class MissionStrategyFeedbackTests(unittest.TestCase):
    def _seed_strategy(self, workspace):
        engine = StrategyEngine(workspace, tenant_id="tenant-a")
        engine.strategies.append(Strategy(
            id="strategy-a",
            name="Strategy A",
            domain="python",
            description="",
            applicable_when=[],
            steps=[{"action": "run"}],
            success_rate=1.0,
            usage_count=1,
        ))
        engine._save_strategies()

    def test_recommendation_without_explicit_usage_does_not_update_strategy(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._seed_strategy(workspace)
            action = {"task_type": "analyze", "recommended_strategies": [{"id": "strategy-a"}]}
            task = SimpleNamespace(id="task-1", result={"summary": "done"}, error="")
            recorded = build_bindings()["record_strategy_execution_feedback"](
                workspace=workspace, tenant_id="tenant-a", action=action,
                task=task, execution_success=True,
            )
            strategy = StrategyEngine(workspace, tenant_id="tenant-a").strategies[0]
            self.assertFalse(recorded)
            self.assertEqual(strategy.usage_count, 1)
            self.assertNotIn("strategy_feedback_recorded", action)

    def test_explicit_usage_updates_once_across_repeated_refresh_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._seed_strategy(workspace)
            action = {
                "task_type": "analyze",
                "title": "Analyze source",
                "mission_run_id": "mission-1",
                "recommended_strategies": [{"id": "strategy-a"}],
            }
            task = SimpleNamespace(
                id="task-2",
                result={
                    "summary": "execution finished",
                    "strategy_usage": {
                        "strategy_id": "strategy-a",
                        "strategy_used": True,
                        "verification_passed": True,
                        "domain": "python",
                    },
                },
                error="",
            )
            feedback = build_bindings()["record_strategy_execution_feedback"]
            self.assertTrue(feedback(
                workspace=workspace, tenant_id="tenant-a", action=action,
                task=task, execution_success=True,
            ))
            self.assertFalse(feedback(
                workspace=workspace, tenant_id="tenant-a", action=action,
                task=task, execution_success=True,
            ))
            strategy = StrategyEngine(workspace, tenant_id="tenant-a").strategies[0]
            self.assertEqual(strategy.usage_count, 2)
            self.assertEqual(strategy.success_rate, 1.0)
            self.assertEqual(strategy.feedback_task_ids, ["task-2"])
            # A fresh engine simulates process restart. Replaying the same task
            # evidence must not increment the strategy a second time.
            restarted_engine = StrategyEngine(workspace, tenant_id="tenant-a")
            from core.learning import Experience
            replay = Experience(
                id="mission-strategy-feedback-task-2",
                domain="python",
                task_type="analyze",
                input_summary="Analyze source",
                output_summary="execution finished",
                quality_score=1.0,
                metadata={
                    "strategy_id": "strategy-a",
                    "execution_success": True,
                    "task_id": "task-2",
                    "verification_passed": True,
                },
            )
            restarted_engine.evolve_strategy(replay)
            persisted = StrategyEngine(workspace, tenant_id="tenant-a").strategies[0]
            self.assertEqual(persisted.usage_count, 2)
            self.assertEqual(persisted.feedback_task_ids, ["task-2"])
            self.assertTrue(action["strategy_feedback_recorded"])
            self.assertEqual(action["strategy_feedback_task_id"], "task-2")

    def test_usage_claim_for_unrecommended_strategy_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._seed_strategy(workspace)
            action = {"recommended_strategies": [{"id": "another-strategy"}]}
            task = SimpleNamespace(
                id="task-unrecommended",
                result={"strategy_usage": {"strategy_id": "strategy-a", "strategy_used": True}},
                error="",
            )
            recorded = build_bindings()["record_strategy_execution_feedback"](
                workspace=workspace, tenant_id="tenant-a", action=action,
                task=task, execution_success=True,
            )
            strategy = StrategyEngine(workspace, tenant_id="tenant-a").strategies[0]
            self.assertFalse(recorded)
            self.assertEqual(strategy.usage_count, 1)
            self.assertNotIn("strategy_feedback_recorded", action)

    def test_feedback_is_tenant_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._seed_strategy(workspace)
            action = {}
            task = SimpleNamespace(
                id="task-3",
                result={"strategy_usage": {"strategy_id": "strategy-a", "strategy_used": True}},
                error="",
            )
            recorded = build_bindings()["record_strategy_execution_feedback"](
                workspace=workspace, tenant_id="tenant-b", action=action,
                task=task, execution_success=True,
            )
            self.assertFalse(recorded)
            self.assertFalse((workspace / ".tenants" / "tenant-b" / "strategies.json").exists())


if __name__ == "__main__":
    unittest.main()
