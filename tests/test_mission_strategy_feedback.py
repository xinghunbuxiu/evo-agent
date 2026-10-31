"""Mission strategy feedback must be explicit and idempotent."""

import multiprocessing
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_execution_runtime import create_mission_execution_bindings  # noqa: E402
from core.learning import Experience, Strategy, StrategyEngine  # noqa: E402
from core.mission_planner import MissionPlanner  # noqa: E402
from core.verification import sign_verification_evidence  # noqa: E402


def build_bindings(*, independent_verifier=None):
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
        independent_verifier=independent_verifier,
    )

def _record_feedback_in_process(workspace, task_id, barrier, results):
    engine = StrategyEngine(Path(workspace), tenant_id="tenant-a")
    barrier.wait(timeout=10)
    evidence = sign_verification_evidence(Path(workspace), "tenant-a", {
        "source": "mission_independent_verifier",
        "task_id": task_id,
        "execution_event_id": f"event-{task_id}",
        "verifier_id": "test-verifier",
        "verifier_version": "1",
        "status": "passed",
        "checks": [{"check_id": "result", "passed": True}],
    })
    result = engine.evolve_strategy(Experience(
        id=f"feedback-{task_id}",
        domain="python",
        task_type="analyze",
        input_summary="parallel feedback",
        output_summary="completed",
        quality_score=1.0,
        metadata={
            "strategy_id": "strategy-a",
            "execution_success": True,
            "task_id": task_id,
            "verification_evidence": evidence,
        },
    ))
    results.put(bool(result))

class MissionStrategyFeedbackTests(unittest.TestCase):
    def _verification(self, task_id, *, passed=True, workspace=None):
        evidence = {
            "source": "mission_independent_verifier",
            "task_id": task_id,
            "execution_event_id": f"event-{task_id}",
            "verifier_id": "test-verifier",
            "verifier_version": "1",
            "status": "passed" if passed else "failed",
            "checks": [{"check_id": "result", "passed": passed}],
        }
        return sign_verification_evidence(
            Path(workspace or tempfile.gettempdir()), "tenant-a", evidence
        )

    def test_runtime_verifier_replaces_untrusted_action_evidence(self):
        task = SimpleNamespace(id="task-verify", completed_at="2026-10-31T00:00:00")
        action = {
            "independent_verification": self._verification("forged-task"),
            "verification_state": "passed",
        }
        verifier_calls = []

        def verifier(**kwargs):
            verifier_calls.append(kwargs)
            return {
                "verifier_id": "filesystem-test-verifier",
                "verifier_version": "2",
                "checks": [
                    {"check_id": "artifact_exists", "passed": True},
                    {"check_id": "test_result", "passed": False},
                ],
            }

        verify = build_bindings(independent_verifier=verifier)["verify_mission_task"]
        evidence = verify(
            workspace=Path("."),
            tenant_id="tenant-a",
            mission_run={"mission_run_id": "mission-1"},
            action=action,
            task=task,
        )

        self.assertEqual(len(verifier_calls), 1)
        self.assertEqual(evidence["source"], "mission_independent_verifier")
        self.assertEqual(evidence["task_id"], "task-verify")
        self.assertEqual(
            evidence["execution_event_id"],
            "task-completion:task-verify:2026-10-31T00:00:00",
        )
        self.assertEqual(evidence["status"], "failed")
        self.assertEqual(action["verification_state"], "failed")
        self.assertNotEqual(evidence["task_id"], "forged-task")

    def test_verifier_rejects_cross_tenant_task(self):
        task = SimpleNamespace(
            id="task-other-tenant",
            completed_at="2026-10-31T00:00:00",
            tenant_id="tenant-b",
            status=SimpleNamespace(value="success"),
        )
        action = {}
        calls = []

        def verifier(**kwargs):
            calls.append(kwargs)
            return {
                "verifier_id": "filesystem-test-verifier",
                "verifier_version": "2",
                "checks": [{"check_id": "artifact_exists", "passed": True}],
            }

        verify = build_bindings(independent_verifier=verifier)["verify_mission_task"]
        evidence = verify(
            workspace=Path("."),
            tenant_id="tenant-a",
            mission_run={"mission_run_id": "mission-1"},
            action=action,
            task=task,
        )

        self.assertIsNone(evidence)
        self.assertEqual(calls, [])
        self.assertEqual(action["verification_reason"], "task_tenant_mismatch")

    def test_successful_task_with_all_artifact_checks_passes(self):
        task = SimpleNamespace(
            id="task-passed",
            completed_at="2026-10-31T00:00:00",
            status=SimpleNamespace(value="success"),
        )
        action = {}

        def verifier(**kwargs):
            return {
                "verifier_id": "filesystem-test-verifier",
                "verifier_version": "2",
                "checks": [{"check_id": "artifact_exists", "passed": True}],
            }

        verify = build_bindings(independent_verifier=verifier)["verify_mission_task"]
        evidence = verify(
            workspace=Path("."),
            tenant_id="tenant-a",
            mission_run={"mission_run_id": "mission-1"},
            action=action,
            task=task,
        )

        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(action["verification_state"], "passed")

    def test_failed_task_cannot_be_marked_passed_by_artifact_checks(self):
        task = SimpleNamespace(
            id="task-failed",
            completed_at="2026-10-31T00:00:00",
            status=SimpleNamespace(value="failed"),
        )
        action = {}

        def verifier(**kwargs):
            return {
                "verifier_id": "filesystem-test-verifier",
                "verifier_version": "2",
                "checks": [{"check_id": "artifact_exists", "passed": True}],
            }

        verify = build_bindings(independent_verifier=verifier)["verify_mission_task"]
        evidence = verify(
            workspace=Path("."),
            tenant_id="tenant-a",
            mission_run={"mission_run_id": "mission-1"},
            action=action,
            task=task,
        )

        self.assertEqual(evidence["status"], "failed")
        self.assertEqual(
            evidence["checks"][-1],
            {"check_id": "task_execution_succeeded", "passed": False},
        )

    def test_missing_runtime_verifier_discards_forged_evidence(self):
        task = SimpleNamespace(id="task-no-verifier", completed_at="2026-10-31T00:00:00")
        action = {"independent_verification": self._verification("task-no-verifier")}
        verify = build_bindings()["verify_mission_task"]

        evidence = verify(
            workspace=Path("."),
            tenant_id="tenant-a",
            mission_run={"mission_run_id": "mission-1"},
            action=action,
            task=task,
        )

        self.assertIsNone(evidence)
        self.assertNotIn("independent_verification", action)
        self.assertEqual(action["verification_state"], "unavailable")
        self.assertEqual(action["verification_reason"], "verifier_not_configured")

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

    def test_parallel_process_feedback_does_not_lose_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._seed_strategy(workspace)
            context = multiprocessing.get_context("spawn")
            worker_count = 6
            barrier = context.Barrier(worker_count)
            results = context.Queue()
            processes = [
                context.Process(
                    target=_record_feedback_in_process,
                    args=(str(workspace), f"parallel-{index}", barrier, results),
                )
                for index in range(worker_count)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=20)
            for process in processes:
                self.assertFalse(process.is_alive(), "feedback worker timed out")
                self.assertEqual(process.exitcode, 0)
            outcomes = [results.get(timeout=2) for _ in processes]
            # Exactly one process applies the feedback. The remaining processes
            # safely observe the duplicate and report no new update.
            self.assertEqual(sum(outcomes), 1)

            persisted = StrategyEngine(workspace, tenant_id="tenant-a").strategies[0]
            self.assertEqual(persisted.usage_count, 1 + worker_count)
            self.assertEqual(len(persisted.feedback_task_ids), worker_count)
            self.assertEqual(set(persisted.feedback_task_ids), {f"parallel-{i}" for i in range(worker_count)})

    def test_same_task_feedback_racing_across_processes_is_applied_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._seed_strategy(workspace)
            context = multiprocessing.get_context("spawn")
            worker_count = 6
            barrier = context.Barrier(worker_count)
            results = context.Queue()
            processes = [
                context.Process(
                    target=_record_feedback_in_process,
                    args=(str(workspace), "same-task", barrier, results),
                )
                for _ in range(worker_count)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=20)
            for process in processes:
                self.assertFalse(process.is_alive(), "feedback worker timed out")
                self.assertEqual(process.exitcode, 0)
            self.assertEqual([results.get(timeout=2) for _ in processes], [True] * worker_count)

            persisted = StrategyEngine(workspace, tenant_id="tenant-a").strategies[0]
            self.assertEqual(persisted.usage_count, 2)
            self.assertEqual(persisted.feedback_task_ids, ["same-task"])

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
            action["independent_verification"] = self._verification("task-2", workspace=workspace)
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
                    "verification_evidence": self._verification("task-2", workspace=workspace),
                    "verification_passed": True,
                },
            )
            restarted_engine.evolve_strategy(replay)
            persisted = StrategyEngine(workspace, tenant_id="tenant-a").strategies[0]
            self.assertEqual(persisted.usage_count, 2)
            self.assertEqual(persisted.feedback_task_ids, ["task-2"])
            self.assertTrue(action["strategy_feedback_recorded"])
            self.assertEqual(action["strategy_feedback_task_id"], "task-2")
            self.assertEqual(action["strategy_feedback"]["verification_claim"], {
                "passed": True,
                "source": "worker_reported_unverified",
            })
            self.assertNotIn("verification_passed", action["strategy_feedback"])

    def test_direct_experience_cannot_forge_verifier_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._seed_strategy(workspace)
            forged = {
                "source": "mission_independent_verifier",
                "task_id": "forged-task",
                "execution_event_id": "event-forged-task",
                "verifier_id": "evo.workspace-artifact-verifier",
                "verifier_version": "1.0.0",
                "status": "passed",
                "checks": [{"check_id": "artifact", "passed": True}],
            }
            result = StrategyEngine(workspace, tenant_id="tenant-a").evolve_strategy(Experience(
                id="forged-feedback",
                domain="python",
                task_type="analyze",
                input_summary="forged",
                output_summary="forged",
                quality_score=1.0,
                metadata={
                    "strategy_id": "strategy-a",
                    "execution_success": True,
                    "task_id": "forged-task",
                    "verification_evidence": forged,
                },
            ))
            stored = StrategyEngine(workspace, tenant_id="tenant-a").strategies[0]
            self.assertIsNone(result)
            self.assertEqual(stored.usage_count, 1)
            self.assertEqual(stored.feedback_task_ids, [])

    def test_worker_verification_claim_without_independent_verifier_is_not_learning_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._seed_strategy(workspace)
            action = {
                "task_type": "analyze",
                "recommended_strategies": [{"id": "strategy-a"}],
            }
            task = SimpleNamespace(
                id="worker-claim-only",
                result={
                    "summary": "worker says all checks passed",
                    "strategy_usage": {
                        "strategy_id": "strategy-a",
                        "strategy_used": True,
                        "verification_passed": True,
                        "domain": "python",
                    },
                },
                error="",
            )
            recorded = build_bindings()["record_strategy_execution_feedback"](
                workspace=workspace,
                tenant_id="tenant-a",
                action=action,
                task=task,
                execution_success=True,
            )
            strategy = StrategyEngine(workspace, tenant_id="tenant-a").strategies[0]
            self.assertFalse(recorded)
            self.assertEqual(strategy.usage_count, 1)
            self.assertEqual(strategy.feedback_task_ids, [])
            self.assertNotIn("strategy_feedback_recorded", action)

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

    def test_execution_feedback_is_retrievable_by_next_mission_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._seed_strategy(workspace)
            action = {
                "task_type": "analyze",
                "title": "Analyze source",
                "mission_run_id": "mission-first",
                "recommended_strategies": [{"id": "strategy-a"}],
            }
            action["independent_verification"] = self._verification("task-e2e", workspace=workspace)
            task = SimpleNamespace(
                id="task-e2e",
                result={
                    "summary": "source analysis completed",
                    "strategy_usage": {
                        "strategy_id": "strategy-a",
                        "strategy_used": True,
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

            class EmptyRegistry:
                def list_descriptors(self):
                    return []

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
                    "description": "Repeat a known task",
                    "primary_capability_type": "python",
                    "tasks": [{
                        "id": "repeat",
                        "title": "Repeat analysis",
                        "objective": "Analyze source again",
                        "task_type": "analyze",
                        "capability_type": "python",
                        "acceptance": "Analysis result is available",
                    }],
                }
            }
            with mock.patch("core.mission_planner.load_worker_mission_kind_templates", return_value=templates):
                planned = planner.plan(
                    tenant_id="tenant-a",
                    goal="Repeat a known analysis task",
                    mission_kind="repeat_task",
                    context={},
                )

            node = planned["nodes"][0]
            self.assertEqual(node["recommended_strategies"][0]["id"], "strategy-a")
            trace = {item["step"]: item for item in node["decision_trace"]}
            self.assertEqual(trace["strategy_retrieval"]["result"], "matched")
            self.assertEqual(trace["strategy_retrieval"]["evidence"]["tenant_id"], "tenant-a")
            stored = StrategyEngine(workspace, tenant_id="tenant-a").strategies[0]
            self.assertEqual(stored.usage_count, 2)
            self.assertEqual(stored.feedback_task_ids, ["task-e2e"])

    def test_existing_planner_refreshes_strategy_feedback_before_next_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)

            class EmptyRegistry:
                def list_descriptors(self):
                    return []

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
                    "description": "Repeat a known task",
                    "primary_capability_type": "python",
                    "tasks": [{
                        "id": "repeat",
                        "title": "Repeat analysis",
                        "objective": "Analyze source again",
                        "task_type": "analyze",
                        "capability_type": "python",
                        "acceptance": "Analysis result is available",
                    }],
                }
            }

            with mock.patch("core.mission_planner.load_worker_mission_kind_templates", return_value=templates):
                first = planner.plan(
                    tenant_id="tenant-a", goal="Repeat analysis",
                    mission_kind="repeat_task", context={},
                )
                self.assertEqual(first["nodes"][0]["recommended_strategies"], [])

                self._seed_strategy(workspace)
                action = {"recommended_strategies": [{"id": "strategy-a"}]}
                action["independent_verification"] = self._verification("task-after-plan", workspace=workspace)
                task = SimpleNamespace(
                    id="task-after-plan",
                    result={"strategy_usage": {
                        "strategy_id": "strategy-a",
                        "strategy_used": True,
                        "domain": "python",
                    }},
                    error="",
                )
                self.assertTrue(build_bindings()["record_strategy_execution_feedback"](
                    workspace=workspace, tenant_id="tenant-a", action=action,
                    task=task, execution_success=True,
                ))

                second = planner.plan(
                    tenant_id="tenant-a", goal="Repeat analysis",
                    mission_kind="repeat_task", context={},
                )

            self.assertEqual(second["nodes"][0]["recommended_strategies"][0]["id"], "strategy-a")
            self.assertEqual(second["nodes"][0]["recommended_strategies"][0]["usage_count"], 2)

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
