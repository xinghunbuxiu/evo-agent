"""Mission staffing approval must resolve an active tenant employee profile."""
import asyncio
import json
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.routes import missions as mission_routes  # noqa: E402


class _App:
    def __init__(self):
        self.routes = {}

    def get(self, path):
        def decorate(handler):
            self.routes[("GET", path)] = handler
            return handler
        return decorate

    def post(self, path):
        def decorate(handler):
            self.routes[("POST", path)] = handler
            return handler
        return decorate


def _request():
    payload = json.dumps({
        "tenant_id": "tenant-a",
        "node_id": "node-a",
        "employee_member_id": "employee-a",
        "worker_id": "worker-a",
    }).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/missions/run-a/staffing-assignments",
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
    }, receive)


def _mission_run():
    return {
        "mission_run_id": "run-a",
        "tenant_id": "tenant-a",
        "runtime_route": {"primary_worker_id": "worker-a"},
        "context": {},
        "staffing_requests": [{
            "schema_version": "talent.staffing_request.v1",
            "request_id": "run-a:node-a",
            "tenant_id": "tenant-a",
            "mission_run_id": "run-a",
            "node_id": "node-a",
            "role_id": "python",
            "required_capabilities": ["python"],
            "status": "pending",
            "decision_owner": "mission",
            "dispatch_authorized": False,
        }],
        "staffing_assignments": [],
        "plan": {
            "runtime_route": {"primary_worker_id": "worker-a"},
            "nodes": [{"id": "node-a"}],
            "staffing_assignments": [],
        },
        "actions": [],
        "submitted_task_ids": [],
    }


class MissionStaffingApprovalRouteTests(unittest.TestCase):
    def _handler(self, mission, members):
        app = _App()
        registry = mock.Mock()
        registry.get_role.return_value = {
            "role_id": "python",
            "status": "active",
            "required_capabilities": ["python"],
        }
        registry.get_worker.return_value = {
            "worker_id": "worker-a",
            "owner_tenant_id": "tenant-a",
            "owner_member_id": "employee-a",
            "status": "available",
            "active_task_ids": [],
            "role_id": "python",
            "profile": {"handler_id": "worker-a"},
        }
        save = mock.Mock()
        with mock.patch.object(
            mission_routes, "load_mission_runs_strict", return_value={"items": [mission]}
        ), mock.patch.object(mission_routes, "save_mission_runs", save), mock.patch.object(
            mission_routes, "exclusive_mission_claim_lock", side_effect=lambda workspace: nullcontext()
        ):
            mission_routes.register_mission_routes(
                app,
                workspace=Path("."),
                task_queue=object(),
                tenant_manager=object(),
                prepare_mission_work_type_bundle=lambda **kwargs: {},
                mission_planner=object(),
                upsert_plan_learning_tasks=lambda **kwargs: [],
                refresh_mission_runs=lambda **kwargs: {"items": []},
                start_mission=lambda *args, **kwargs: (None, None),
                find_mission_run=lambda *args: None,
                derive_follow_up_goal=lambda run: "",
                derive_follow_up_context=lambda run: {},
                success_response=lambda data, message="": {"data": data, "message": message},
                error_response=lambda message, status: {"error": message, "status": status},
                get_session_user=lambda request: {"id": 7},
                authorize_tenant=lambda user, tenant_id: tenant_id == "tenant-a",
                tenant_role=lambda user, tenant_id: "tenant_admin",
                organization_registry=registry,
                resolve_tenant_members=lambda tenant_id: members,
                build_mission_actions=None,
            )
            handler = app.routes[("POST", "/api/missions/{mission_run_id}/staffing-assignments")]
            response = asyncio.run(handler(request=_request(), mission_run_id="run-a"))
        return response, mission, save

    def test_active_employee_can_be_assigned_to_matching_worker(self):
        mission = _mission_run()
        response, saved_run, save = self._handler(mission, [{
            "member_id": "employee-a",
            "name": "Python Engineer",
            "primary_role": "python_engineer",
            "status": "active",
            "tenant_id": "tenant-a",
        }])
        self.assertIn("data", response)
        assignment = response["data"]["assignment"]
        self.assertEqual(assignment["employee_member_id"], "employee-a")
        self.assertEqual(assignment["worker_id"], "worker-a")
        self.assertEqual(assignment["decision_owner"], "talent_center")
        self.assertEqual(saved_run["staffing_assignments"], [assignment])
        self.assertEqual(saved_run["plan"]["staffing_assignments"], [assignment])
        save.assert_called_once()

    def test_inactive_or_talent_development_member_cannot_be_assigned(self):
        for member in (
            {"member_id": "employee-a", "status": "inactive", "primary_role": "python_engineer"},
            {"member_id": "employee-a", "status": "active", "primary_role": "talent_development"},
        ):
            with self.subTest(member=member):
                mission = _mission_run()
                response, saved_run, save = self._handler(mission, [member])
                self.assertEqual(response.get("status"), 409)
                self.assertEqual(saved_run["staffing_assignments"], [])
                save.assert_not_called()

    def test_cross_tenant_employee_cannot_be_assigned(self):
        mission = _mission_run()
        response, saved_run, save = self._handler(mission, [{
            "member_id": "employee-a",
            "status": "active",
            "primary_role": "python_engineer",
            "tenant_id": "tenant-b",
        }])
        self.assertEqual(response.get("status"), 403)
        self.assertEqual(saved_run["staffing_assignments"], [])
        save.assert_not_called()
 
    def test_staffing_options_do_not_expose_workers_for_inactive_employees(self):
        app = _App()
        mission = _mission_run()
        mission["staffing_requests"].append({
            "request_id": "run-a:already-finished",
            "tenant_id": "tenant-a",
            "mission_run_id": "run-a",
            "node_id": "already-finished",
            "role_id": "python",
            "required_capabilities": ["python"],
            "status": "approved",
        })
        registry = mock.Mock()
        registry.get_role.return_value = {
            "role_id": "python",
            "status": "active",
            "required_capabilities": ["python"],
        }
        registry.list_workers.return_value = [{
            "worker_id": "worker-a",
            "owner_tenant_id": "tenant-a",
            "owner_member_id": "employee-inactive",
            "role_id": "python",
            "status": "available",
            "active_task_ids": [],
            "profile": {"handler_id": "worker-a"},
        }]
        members = [{
            "member_id": "employee-inactive",
            "name": "Inactive",
            "primary_role": "python_engineer",
            "status": "inactive",
        }]
        with mock.patch.object(
            mission_routes, "load_mission_runs_strict", return_value={"items": [mission]}
        ), mock.patch.object(
            mission_routes, "exclusive_mission_claim_lock", side_effect=lambda workspace: nullcontext()
        ):
            mission_routes.register_mission_routes(
                app,
                workspace=Path("."),
                task_queue=object(),
                tenant_manager=object(),
                prepare_mission_work_type_bundle=lambda **kwargs: {},
                mission_planner=object(),
                upsert_plan_learning_tasks=lambda **kwargs: [],
                refresh_mission_runs=lambda **kwargs: {"items": []},
                start_mission=lambda *args, **kwargs: (None, None),
                find_mission_run=lambda *args: None,
                derive_follow_up_goal=lambda run: "",
                derive_follow_up_context=lambda run: {},
                success_response=lambda data, message="": {"data": data, "message": message},
                error_response=lambda message, status: {"error": message, "status": status},
                get_session_user=lambda request: {"id": 7},
                authorize_tenant=lambda user, tenant_id: tenant_id == "tenant-a",
                tenant_role=lambda user, tenant_id: "tenant_admin",
                organization_registry=registry,
                resolve_tenant_members=lambda tenant_id: members,
                build_mission_actions=None,
            )
            handler = app.routes[("GET", "/api/missions/{mission_run_id}/staffing-options")]
            response = asyncio.run(handler(
                request=_request(), mission_run_id="run-a", tenant_id="tenant-a",
            ))
        self.assertIn("data", response)
        self.assertEqual(response["data"]["employees"], [])
        self.assertEqual(response["data"]["workers"], [])

    def test_staffing_options_are_tenant_scoped_and_mark_only_available_workers(self):
        app = _App()
        mission = _mission_run()
        registry = mock.Mock()
        registry.list_workers.return_value = [
            {
                "worker_id": "worker-a",
                "owner_tenant_id": "tenant-a",
                "owner_member_id": "employee-a",
                "role_id": "python",
                "status": "available",
                "active_task_ids": [],
                "profile": {"handler_id": "worker-a"},
            },
            {
                "worker_id": "worker-busy",
                "owner_tenant_id": "tenant-a",
                "owner_member_id": "employee-a",
                "role_id": "python",
                "status": "busy",
                "active_task_ids": ["task-1"],
                "profile": {"handler_id": "worker-a"},
            },
            {
                "worker_id": "worker-other-tenant",
                "owner_tenant_id": "tenant-b",
                "owner_member_id": "employee-a",
                "role_id": "python",
                "status": "available",
                "active_task_ids": [],
                "profile": {"handler_id": "worker-a"},
            },
        ]
        members = [
            {"member_id": "employee-a", "name": "Python Engineer", "primary_role": "python_engineer", "status": "active"},
            {"member_id": "talent", "name": "Talent Center", "primary_role": "talent_development", "status": "active"},
        ]
        with mock.patch.object(
            mission_routes, "load_mission_runs_strict", return_value={"items": [mission]}
        ), mock.patch.object(
            mission_routes, "exclusive_mission_claim_lock", side_effect=lambda workspace: nullcontext()
        ):
            mission_routes.register_mission_routes(
                app,
                workspace=Path("."),
                task_queue=object(),
                tenant_manager=object(),
                prepare_mission_work_type_bundle=lambda **kwargs: {},
                mission_planner=object(),
                upsert_plan_learning_tasks=lambda **kwargs: [],
                refresh_mission_runs=lambda **kwargs: {"items": []},
                start_mission=lambda *args, **kwargs: (None, None),
                find_mission_run=lambda *args: None,
                derive_follow_up_goal=lambda run: "",
                derive_follow_up_context=lambda run: {},
                success_response=lambda data, message="": {"data": data, "message": message},
                error_response=lambda message, status: {"error": message, "status": status},
                get_session_user=lambda request: {"id": 7},
                authorize_tenant=lambda user, tenant_id: tenant_id == "tenant-a",
                tenant_role=lambda user, tenant_id: "tenant_admin",
                organization_registry=registry,
                resolve_tenant_members=lambda tenant_id: members,
                build_mission_actions=None,
            )
            handler = app.routes[("GET", "/api/missions/{mission_run_id}/staffing-options")]
            response = asyncio.run(handler(
                request=_request(), mission_run_id="run-a", tenant_id="tenant-a",
            ))
        self.assertIn("data", response)
        data = response["data"]
        self.assertEqual([item["member_id"] for item in data["employees"]], ["employee-a"])
        self.assertEqual(
            {item["worker_id"]: item["available"] for item in data["workers"]},
            {"worker-a": True, "worker-busy": False},
        )
        self.assertEqual([item["node_id"] for item in data["pending_requests"]], ["node-a"])


if __name__ == "__main__":
    unittest.main()
