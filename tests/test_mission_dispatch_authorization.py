"""Runtime dispatch requires an explicit Talent Center staffing assignment."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_action_runtime import create_mission_action_runtime_bindings
from core.mission_brain import build_mission_brain_contract
from core.organization_runtime import OrganizationRegistry
from workers.javascript_reverse.runtime import handle_javascript_reverse_mission_node


class FakeTaskQueue:
    def __init__(self):
        self.submissions = []

    def submit(self, **kwargs):
        self.submissions.append(kwargs)
        return SimpleNamespace(id=f"task-{len(self.submissions)}")


class FakePriority:
    HIGH = 1
    NORMAL = 2


class MissionDispatchAuthorizationTests(unittest.TestCase):
    def _registry(self, temp_dir, handler_id="worker-a"):
        registry = OrganizationRegistry(Path(temp_dir))
        registry.create_role(
            role_id="javascript-role",
            title="JavaScript Engineer",
            responsibilities=["Analyze JavaScript bundles"],
            required_capabilities=["javascript"],
        )
        registry.create_worker(
            worker_id="worker-a",
            role_id="javascript-role",
            profile={"handler_id": "worker-a"},
            owner_tenant_id="tenant-a",
            owner_member_id="employee-a",
        )
        return registry

    def _node(self):
        return {
            "id": "analyze-bundle",
            "title": "Analyze JavaScript bundle",
            "task_type": "analyze",
            "status": "ready",
            "reasoning": [],
            "blockers": [],
            "recommended_skill_ids": [],
            "recommended_skills": [],
            "validation_checks": ["analysis result reviewed"],
            "decision_trace": [],
            "parallel_safe": False,
            "workforce_decision": {
                "decision": "assign_existing_worker_recommended",
                "recommended_worker_id": "worker-a",
                "required_capabilities": ["javascript"],
                "dispatch_state": "recommendation_only",
                "dispatch_authorized": False,
            },
        }

    def _build(self, runtime_worker_id, *, approved=True):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = self._registry(temp_dir)
            node = self._node()
            queue = FakeTaskQueue()
            plan = {
                "goal": "Analyze a JavaScript bundle",
                "mission_kind": "javascript_reverse",
                "runtime_route": {"primary_worker_id": runtime_worker_id},
                "nodes": [node],
                "orchestration": build_mission_brain_contract([node]),
            }
            if approved:
                plan["staffing_assignments"] = [{
                    "schema_version": "talent.staffing_assignment.v1",
                    "decision_owner": "talent_center",
                    "status": "approved",
                    "tenant_id": "tenant-a",
                    "mission_run_id": "mission-a",
                    "node_id": "analyze-bundle",
                    "request_id": "mission-a:analyze-bundle",
                    "employee_member_id": "employee-a",
                    "worker_id": "worker-a",
                }]
            bindings = create_mission_action_runtime_bindings(
                normalize_string_list=lambda value: (
                    [str(item) for item in value if str(item).strip()]
                    if isinstance(value, list) else []
                ),
                task_priority_cls=FakePriority,
                mission_action_handlers={
                    runtime_worker_id: handle_javascript_reverse_mission_node,
                },
                organization_registry=registry,
                record_worker_employee_link=lambda **kwargs: None,
            )
            state = bindings["build_mission_actions"](
                task_queue=queue,
                tenant_id="tenant-a",
                mission_run_id="mission-a",
                plan=plan,
                context={"source_path": "/tmp/sample/main.js"},
                work_type={},
                work_type_summary={},
            )
            return state, queue

    def test_approved_assignment_dispatches_to_the_selected_worker(self):
        state, queue = self._build("worker-a")
        self.assertEqual(len(queue.submissions), 1)
        authorization = queue.submissions[0]["payload"]["_mission_dispatch_authorization"]
        self.assertTrue(authorization["authorized"])
        self.assertEqual(authorization["reason_code"], "authorized")
        self.assertEqual(state["actions"][0]["worker_claim"]["origin"], "talent_center_approved")

    def test_missing_talent_center_assignment_is_denied_before_submit(self):
        state, queue = self._build("worker-a", approved=False)
        self.assertEqual(queue.submissions, [])
        self.assertEqual(state["submitted_task_ids"], [])
        self.assertEqual(
            state["actions"][0]["mission_runtime_authorization"]["reason_code"],
            "staffing_assignment_missing",
        )

    def test_runtime_handler_mismatch_is_denied(self):
        state, queue = self._build("worker-b")
        self.assertEqual(queue.submissions, [])
        self.assertEqual(
            state["actions"][0]["mission_runtime_authorization"]["reason_code"],
            "staffing_assignment_handler_mismatch",
        )

    def test_worker_creation_recommendation_never_incubates_worker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = OrganizationRegistry(Path(temp_dir))
            registry.create_role(
                role_id="javascript-role",
                title="JavaScript Engineer",
                responsibilities=["Analyze JavaScript bundles"],
                required_capabilities=["javascript"],
            )
            registry.create_worker(
                worker_id="template",
                role_id="javascript-role",
                profile={"handler_id": "worker-a"},
            )
            node = self._node()
            node["workforce_decision"] = {
                "decision": "create_worker_recommended",
                "recommended_role_id": "javascript-role",
                "required_capabilities": ["javascript"],
                "dispatch_state": "recommendation_only",
                "dispatch_authorized": False,
            }
            queue = FakeTaskQueue()
            bindings = create_mission_action_runtime_bindings(
                normalize_string_list=lambda value: value if isinstance(value, list) else [],
                task_priority_cls=FakePriority,
                mission_action_handlers={"worker-a": handle_javascript_reverse_mission_node},
                organization_registry=registry,
            )
            state = bindings["build_mission_actions"](
                task_queue=queue,
                tenant_id="tenant-a",
                mission_run_id="mission-create",
                plan={
                    "goal": "Analyze bundle",
                    "mission_kind": "javascript_reverse",
                    "runtime_route": {"primary_worker_id": "worker-a"},
                    "nodes": [node],
                    "orchestration": build_mission_brain_contract([node]),
                },
                context={},
                work_type={},
                work_type_summary={},
            )
            self.assertEqual(queue.submissions, [])
            self.assertEqual(len(registry.list_workers(role_id="javascript-role")), 1)
            self.assertEqual(
                state["actions"][0]["mission_runtime_authorization"]["reason_code"],
                "staffing_assignment_missing",
            )


if __name__ == "__main__":
    unittest.main()
