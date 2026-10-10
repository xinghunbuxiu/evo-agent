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


if __name__ == "__main__":
    unittest.main()
