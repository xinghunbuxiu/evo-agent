"""Regression tests for trace propagation through mission startup."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin import mission_runtime  # noqa: E402


class MissionTracePropagationTests(unittest.TestCase):
    def test_planner_decision_trace_is_preserved_in_mission_run_plan(self):
        trace = [{
            "step": "input_validation",
            "rule_id": "mission.required_inputs.v1",
            "result": "passed",
            "evidence": {"blocker_codes": []},
        }]
        plan = {"title": "test plan", "nodes": [{"id": "node-a", "decision_trace": trace}]}
        prepared = {
            "goal": "test goal",
            "mission_kind": "test_kind",
            "context": {},
            "work_type_validation": {"valid": True, "missing_inputs": []},
            "work_type": {"work_type_id": "test"},
            "work_type_summary": {"deliverables": ["test output"]},
            "runtime_route": {"primary_worker_id": "worker-a"},
        }

        class Planner:
            def plan(self, **kwargs):
                return dict(plan)

        def build_mission_run(**kwargs):
            return {
                "mission_run_id": "trace-run",
                "plan": kwargs["plan"],
                "context": kwargs["context"],
            }

        with mock.patch.object(mission_runtime, "load_mission_runs", return_value={"items": []}), \
             mock.patch.object(mission_runtime, "save_mission_runs"):
            start = mission_runtime.create_start_mission(
                workspace=Path("."),
                task_queue=object(),
                tenant_manager=object(),
                prepare_mission_work_type_bundle=lambda **kwargs: prepared,
                mission_planner=Planner(),
                upsert_plan_learning_tasks=lambda **kwargs: [],
                build_mission_run=build_mission_run,
                refresh_mission_runs_fn=lambda **kwargs: {"items": []},
                error_response=lambda message, status: {"error": message, "status": status},
            )
            latest, error = start({"goal": "user goal", "tenant_id": "tenant"}, refresh_runs=False)

        self.assertIsNone(error)
        self.assertEqual(latest["mission_run_id"], "trace-run")
        self.assertEqual(latest["plan"]["nodes"][0]["decision_trace"], trace)
        self.assertEqual(latest["plan"]["nodes"][0]["decision_trace"][0]["rule_id"], "mission.required_inputs.v1")

    def test_follow_up_context_preserves_run_lineage_without_mutating_source(self):
        source_context = {
            "autonomy_cycle": 1,
            "nested": {"keep": True},
            "runtime_primary_worker_id": "worker-a",
        }
        source = {
            "mission_run_id": "run-previous",
            "root_mission_run_id": "run-root",
            "autonomy_session_id": "session-1",
            "context": source_context,
            "runtime_route": {"primary_worker_id": "worker-a"},
            "summary": {"next_cycle_plan": {
                "next_steps": ["inspect failed step", "retry with evidence"],
                "focus_points": ["dispatch trace"],
            }},
        }

        context = mission_runtime.derive_follow_up_context(source)

        self.assertEqual(context["previous_mission_run_id"], "run-previous")
        self.assertEqual(context["root_mission_run_id"], "run-root")
        self.assertEqual(context["autonomy_session_id"], "session-1")
        self.assertEqual(context["autonomy_cycle"], 2)
        self.assertEqual(context["deliverable_goal"], "inspect failed step；retry with evidence")
        self.assertEqual(context["goal_hint"], "dispatch trace")
        self.assertNotIn("previous_mission_run_id", source_context)
        context["nested"]["keep"] = False
        self.assertTrue(source_context["nested"]["keep"])

    def test_auto_continue_is_blocked_after_a_source_run_has_triggered_follow_up(self):
        base = {
            "status": "completed",
            "context": {"auto_continue": True, "autonomy_cycle": 1, "max_autonomy_cycles": 3},
            "summary": {"next_cycle_plan": {"status": "ready"}},
        }
        self.assertTrue(mission_runtime.should_auto_continue_mission(base))
        self.assertFalse(mission_runtime.should_auto_continue_mission({
            **base, "auto_continue_source_mission_run_id": "run-source"
        }))
        self.assertFalse(mission_runtime.should_auto_continue_mission({
            **base, "auto_continue_triggered_run_id": "run-next"
        }))

    def test_refresh_records_source_and_target_ids_for_auto_continue(self):
        current = {
            "mission_run_id": "run-source",
            "tenant_id": "tenant-a",
            "status": "completed",
            "context": {
                "auto_continue": True,
                "autonomy_cycle": 1,
                "max_autonomy_cycles": 3,
                "runtime_primary_worker_id": "worker-a",
            },
            "runtime_route": {"primary_worker_id": "worker-a"},
            "summary": {"next_cycle_plan": {
                "status": "ready",
                "next_steps": ["verify failed output"],
                "focus_points": ["retry safely"],
            }},
        }
        spawned = {"mission_run_id": "run-next", "context": {"previous_mission_run_id": "run-source"}}
        captured = {}

        def starter(payload, *, refresh_runs):
            captured["payload"] = payload
            captured["refresh_runs"] = refresh_runs
            return spawned, None

        persisted = {"items": [current]}
        def load_state(workspace):
            return persisted
        def save_state(workspace, payload):
            persisted.update(payload)

        with mock.patch.object(mission_runtime, "load_mission_runs", side_effect=load_state), \\
             mock.patch.object(mission_runtime, "save_mission_runs", side_effect=save_state) as save:
            state = mission_runtime.refresh_mission_runs(
                workspace=Path("."),
                task_queue=object(),
                tenant_manager=object(),
                refresh_runtime_learning_tasks=lambda **kwargs: None,
                refresh_mission_run=lambda **kwargs: kwargs["mission_run"],
                mission_starter=starter,
            )

        self.assertEqual(captured["refresh_runs"], False)
        self.assertEqual(captured["payload"]["context"]["previous_mission_run_id"], "run-source")
        self.assertEqual(state["items"][0]["mission_run_id"], "run-next")
        self.assertEqual(state["items"][0]["auto_continue_source_mission_run_id"], "run-source")
        source_after = next(item for item in state["items"] if item["mission_run_id"] == "run-source")
        self.assertEqual(source_after["auto_continue_triggered_run_id"], "run-next")
        self.assertEqual(source_after["auto_continue_status"], "triggered")
        save.assert_called_once()

    def test_refresh_records_auto_continue_start_failure(self):
        current = {
            "mission_run_id": "run-source",
            "status": "completed",
            "context": {"auto_continue": True, "autonomy_cycle": 1, "max_autonomy_cycles": 3},
            "summary": {"next_cycle_plan": {"status": "ready"}},
        }
        persisted = {"items": [current]}
        def load_state(workspace):
            return persisted
        def save_state(workspace, payload):
            persisted.update(payload)

        with mock.patch.object(mission_runtime, "load_mission_runs", side_effect=load_state), \\
             mock.patch.object(mission_runtime, "save_mission_runs", side_effect=save_state):
            state = mission_runtime.refresh_mission_runs(
                workspace=Path("."),
                task_queue=object(),
                tenant_manager=object(),
                refresh_runtime_learning_tasks=lambda **kwargs: None,
                refresh_mission_run=lambda **kwargs: kwargs["mission_run"],
                mission_starter=lambda payload, refresh_runs: (None, {"error": "boom"}),
            )

        source = state["items"][0]
        self.assertEqual(source["auto_continue_status"], "failed")
        self.assertEqual(source["auto_continue_error"], "自动续跑启动失败")


if __name__ == "__main__":
    unittest.main()
