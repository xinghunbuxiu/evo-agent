"""Regression tests for mission understanding inputs and runtime dispatch preparation."""
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_request_runtime import prepare_mission_work_type_bundle  # noqa: E402
from admin import mission_runtime  # noqa: E402


class MissionRequestRuntimeTests(unittest.TestCase):
    def _prepare(self, *, goal, route, context=None, validation=None):
        calls = {}

        def resolve_context(workspace, **kwargs):
            calls["resolve"] = kwargs
            return {
                "work_type": {"work_type_id": "design", "title": "设计"},
                "goal": kwargs["goal"],
                "mission_kind": kwargs["mission_kind"] or "general",
                "context": dict(kwargs["context"]),
            }

        def resolve_route(workspace, **kwargs):
            calls["route"] = kwargs
            return route

        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = prepare_mission_work_type_bundle(
                workspace=Path(temp_dir),
                work_type_id="design",
                goal=goal,
                mission_kind="general",
                context=context or {},
                resolve_work_type_context=resolve_context,
                summarize_work_type=lambda wt: {
                    "title": "设计",
                    "capability_type": "design",
                    "required_inputs": ["brief"],
                    "optional_inputs": ["reference_images"],
                    "deliverables": ["design_spec"],
                    "knowledge_policy": {},
                    "type_key": "design",
                },
                validate_work_type_request=lambda **kwargs: validation or {"valid": True, "missing_inputs": []},
                resolve_runtime_route=resolve_route,
                load_work_types=lambda *args, **kwargs: {},
                builtin_worker_manifests=lambda *args, **kwargs: {},
                load_worker_registry_config=lambda *args, **kwargs: {},
                build_project_package_runtime_entries=lambda *args, **kwargs: [],
            )
        return bundle, calls

    def test_preserves_user_goal_and_required_input_contract(self):
        goal = "分析这份户型图，检查动线并输出改进方案"
        bundle, calls = self._prepare(
            goal=goal,
            route={"workers": [{"worker_id": "floorplan_worker", "enabled": True, "task_types": ["analyze"]}]},
            context={"brief": "两室一厅户型图"},
        )
        self.assertEqual(calls["resolve"]["goal"], goal)
        self.assertEqual(bundle["goal"], goal)
        self.assertEqual(bundle["context"]["work_type_required_inputs"], ["brief"])
        self.assertEqual(bundle["context"]["work_type_deliverables"], ["design_spec"])
        self.assertEqual(bundle["runtime_route"]["primary_worker_id"], "floorplan_worker")
        self.assertEqual(bundle["context"]["runtime_primary_worker_id"], "floorplan_worker")

    def test_dispatch_prefers_first_enabled_worker_not_disabled_worker(self):
        bundle, _ = self._prepare(
            goal="检查任务",
            route={"workers": [
                {"worker_id": "disabled_worker", "enabled": False},
                {"worker_id": "review_worker", "enabled": True, "task_types": ["review"]},
                {"worker_id": "fallback_worker", "enabled": True},
            ]},
        )
        self.assertEqual(bundle["runtime_route"]["worker_ids"], [
            "disabled_worker", "review_worker", "fallback_worker"
        ])
        self.assertEqual(bundle["runtime_route"]["primary_worker_id"], "review_worker")

    def test_normalizes_capabilities_and_deduplicates_capability_ids(self):
        bundle, _ = self._prepare(
            goal="拆解任务",
            route={"packages": [
                {"package_id": "pkg-a", "capabilities": [
                    {"capability_id": "vision", "supported_tasks": ["read_plan"]},
                    {"capability_id": "geometry"},
                ]},
                {"package_id": "pkg-b", "capabilities": [
                    {"capability_id": "vision", "name": "重复能力"},
                ]},
            ]},
        )
        self.assertEqual(bundle["runtime_route"]["primary_package_id"], "pkg-a")
        self.assertEqual(bundle["runtime_route"]["package_ids"], ["pkg-a", "pkg-b"])
        self.assertEqual(bundle["runtime_route"]["capability_ids"], ["vision", "geometry"])
        self.assertEqual(bundle["runtime_route"]["primary_capability_id"], "vision")
        self.assertEqual(bundle["runtime_route"]["execution_preference"], "capability_package")


class MissionStartOrchestrationTests(unittest.TestCase):
    def test_start_passes_resolved_goal_context_and_dispatch_route_to_planner(self):
        calls = {}
        plan = {"title": "planned mission", "nodes": [{"id": "understand", "decision_trace": [{"step": "status_decision", "rule_id": "mission.status.capability_gap.v1", "result": "needs_learning", "evidence": {"gap_type": "capability_gap"}}]}, {"id": "execute", "decision_trace": []}]}

        class Planner:
            def plan(self, **kwargs):
                calls["planner"] = kwargs
                return dict(plan)

        prepared = {
            "goal": "识别户型图并检查门窗墙体",
            "mission_kind": "floorplan_review",
            "context": {"runtime_primary_worker_id": "floorplan_worker"},
            "work_type_validation": {"valid": True, "missing_inputs": []},
            "work_type": {"work_type_id": "floorplan"},
            "work_type_summary": {"deliverables": ["validated_floorplan"]},
            "runtime_route": {"primary_worker_id": "floorplan_worker", "worker_ids": ["floorplan_worker"]},
        }
        start = mission_runtime.create_start_mission(
            workspace=Path("."),
            task_queue=object(),
            tenant_manager=object(),
            prepare_mission_work_type_bundle=lambda **kwargs: prepared,
            mission_planner=Planner(),
            upsert_plan_learning_tasks=lambda **kwargs: ["learning-1"],
            build_mission_run=lambda **kwargs: {
                "mission_run_id": "mission-test",
                "plan": kwargs["plan"],
                "context": kwargs["context"],
            },
            refresh_mission_runs_fn=lambda **kwargs: {"items": []},
            error_response=lambda message, status: {"error": message, "status": status},
        )
        with (
            mock.patch.object(mission_runtime, "load_mission_runs", return_value={"items": []}),
            mock.patch.object(mission_runtime, "save_mission_runs"),
        ):
            latest, error = start({
                "goal": "  帮我看看户型图  ",
                "tenant_id": "tenant-a",
                "work_type_id": "floorplan",
                "context": {"image_path": "/tmp/floorplan.png"},
            }, refresh_runs=False)

        self.assertIsNone(error)
        self.assertEqual(calls["planner"]["tenant_id"], "tenant-a")
        self.assertEqual(calls["planner"]["goal"], "识别户型图并检查门窗墙体")
        self.assertEqual(calls["planner"]["mission_kind"], "floorplan_review")
        self.assertEqual(
            latest["plan"]["nodes"][0]["decision_trace"][0]["rule_id"],
            "mission.status.capability_gap.v1",
        )
        self.assertEqual(calls["planner"]["context"]["runtime_primary_worker_id"], "floorplan_worker")
        self.assertEqual(latest["plan"]["runtime_route"]["primary_worker_id"], "floorplan_worker")
        self.assertEqual(latest["plan"]["learning_task_ids"], ["learning-1"])

    def test_blank_goal_is_rejected_before_planner_or_task_creation(self):
        calls = {"planner": 0, "learning": 0}

        class Planner:
            def plan(self, **kwargs):
                calls["planner"] += 1
                return {}

        start = mission_runtime.create_start_mission(
            workspace=Path("."),
            task_queue=object(),
            tenant_manager=object(),
            prepare_mission_work_type_bundle=lambda **kwargs: {
                "goal": " ", "mission_kind": None, "context": {}, "work_type_validation": {}
            },
            mission_planner=Planner(),
            upsert_plan_learning_tasks=lambda **kwargs: calls.__setitem__("learning", calls["learning"] + 1) or [],
            build_mission_run=lambda **kwargs: self.fail("mission must not be built"),
            refresh_mission_runs_fn=lambda **kwargs: self.fail("refresh must not run"),
            error_response=lambda message, status: {"error": message, "status": status},
        )
        latest, error = start({"goal": "  "}, refresh_runs=False)
        self.assertIsNone(latest)
        self.assertEqual(error, {"error": "goal 不能为空", "status": 400})
        self.assertEqual(calls, {"planner": 0, "learning": 0})


if __name__ == "__main__":
    unittest.main()
