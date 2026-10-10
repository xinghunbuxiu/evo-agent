"""Regression tests for mission understanding inputs and runtime dispatch preparation."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_request_runtime import prepare_mission_work_type_bundle  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
