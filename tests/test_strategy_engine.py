"""Regression tests for persistent, evidence-gated strategy evolution."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.learning import Experience, Strategy, StrategyEngine  # noqa: E402


class StrategyEngineTests(unittest.TestCase):
    def make_experience(self, metadata, *, domain="python"):
        return Experience(
            id="experience-1",
            domain=domain,
            task_type="implement",
            input_summary="Create a minimal program",
            output_summary="Program executed and output checked",
            quality_score=1.0,
            metadata=metadata,
        )

    def test_unverified_proposal_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = StrategyEngine(Path(tmp))
            result = engine.evolve_strategy(self.make_experience({
                "strategy_proposal": {
                    "id": "hello-world",
                    "name": "Hello World",
                    "steps": [{"action": "run"}],
                },
                "validation_passed": False,
            }))
            self.assertIsNone(result)
            self.assertEqual(engine.strategies, [])
            self.assertFalse(engine.strategy_file.exists())

    def test_verified_proposal_persists_and_can_be_reused_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            engine = StrategyEngine(workspace)
            proposal = {
                "id": "python-hello-world",
                "name": "Run a minimal Python program",
                "domain": "python",
                "description": "Create, run, and verify the expected output.",
                "applicable_when": ["python"],
                "steps": [{"action": "execute"}, {"action": "assert_output"}],
            }
            # A caller-supplied boolean is not validation evidence.
            unverified = engine.evolve_strategy(self.make_experience({
                "strategy_proposal": proposal,
                "validation_passed": True,
            }))
            self.assertIsNone(unverified)
            self.assertEqual(engine.strategies, [])

            mismatched_evidence = engine.evolve_strategy(self.make_experience({
                "task_id": "task-verified-1",
                "strategy_proposal": proposal,
                "validation_passed": True,
                "validation_evidence": {
                    "task_id": "different-task",
                    "source": "mission_independent_verifier",
                    "execution_event_id": "event-1",
                    "verifier_id": "test-verifier",
                    "verifier_version": "1",
                    "status": "passed",
                    "checks": [{"check_id": "expected_output", "passed": True}],
                },
            }))
            self.assertIsNone(mismatched_evidence)
            self.assertEqual(engine.strategies, [])

            promoted = engine.evolve_strategy(self.make_experience({
                "task_id": "task-verified-1",
                "strategy_proposal": proposal,
                "validation_passed": True,
                "validation_evidence": {
                    "task_id": "task-verified-1",
                    "source": "mission_independent_verifier",
                    "execution_event_id": "event-task-verified-1",
                    "verifier_id": "test-verifier",
                    "verifier_version": "1",
                    "status": "passed",
                    "checks": [{"check_id": "expected_output", "passed": True}],
                },
            }))
            self.assertIsNotNone(promoted)
            self.assertTrue(engine.strategy_file.is_file())

            restarted = StrategyEngine(workspace)
            found = restarted.find_strategy("python", {"language": "python", "goal": "hello"})
            self.assertIsNotNone(found)
            self.assertEqual(found.id, "python-hello-world")
            self.assertEqual(found.usage_count, 1)

    def test_execution_feedback_updates_observed_success_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            engine = StrategyEngine(workspace)
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

            engine.evolve_strategy(self.make_experience({
                "strategy_id": "strategy-a",
                "execution_success": False,
                "task_id": "task-execution-feedback-1",
                "verification_evidence": {
                    "source": "mission_independent_verifier",
                    "task_id": "task-execution-feedback-1",
                    "execution_event_id": "event-task-execution-feedback-1",
                    "verifier_id": "test-verifier",
                    "verifier_version": "1",
                    "status": "failed",
                    "checks": [{"check_id": "expected_output", "passed": False}],
                },
            }))
            reloaded = StrategyEngine(workspace)
            strategy = next(item for item in reloaded.strategies if item.id == "strategy-a")
            self.assertEqual(strategy.usage_count, 2)
            self.assertEqual(strategy.success_rate, 0.5)

    def test_high_quality_score_alone_does_not_create_strategy(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = StrategyEngine(Path(tmp))
            engine.evolve_strategy(self.make_experience({"notes": "looks good"}))
            self.assertEqual(engine.strategies, [])
            self.assertFalse(engine.strategy_file.exists())


if __name__ == "__main__":
    unittest.main()
