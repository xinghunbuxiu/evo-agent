"""Tests for the explicitly authorized Mission Skill Replay route."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from starlette.requests import Request

from admin.mission_runtime import load_mission_runs, save_mission_runs
from admin.routes.missions import register_mission_routes


class RouteApp:
    def __init__(self):
        self.routes = {}

    def get(self, path):
        def decorator(handler):
            self.routes[("GET", path)] = handler
            return handler
        return decorator

    def post(self, path):
        def decorator(handler):
            self.routes[("POST", path)] = handler
            return handler
        return decorator


def _request(body=None, *, authenticated=True):
    payload = json.dumps(body or {}).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    headers = [(b"cookie", b"session=valid")] if authenticated else []
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/missions/run-a/skills/skill-a/replay",
        "headers": headers,
        "query_string": b"",
    }, receive)


def _register(app, workspace, runtime, *, authorized=True):
    return register_mission_routes(
        app,
        workspace=workspace,
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
        get_session_user=lambda request: {"id": 7} if request.cookies.get("session") == "valid" else None,
        authorize_tenant=lambda user, tenant_id: authorized and tenant_id == "tenant-a",
        tenant_role=lambda user, tenant_id: "tenant_admin" if authorized and tenant_id == "tenant-a" else None,
        organization_registry=object(),
        skill_replay_runtime=runtime,
    )


class _ReplayRuntime:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.result = result or {
            "schema_version": "mission.skill-replay-operation.v1",
            "task_id": "task-a",
            "stage_receipt": {"signature": {"key_id": "broker-test"}},
            "replay": {
                "result": {"execution_succeeded": True},
                "skill_replay_output": {"success": True, "value": {"ok": True}},
                "evidence": {"evidence_id": "evidence-a"},
                "experience": {"id": "experience-a"},
            },
        }
        self.error = error

    def replay_candidate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class MissionSkillReplayRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        save_mission_runs(self.workspace, {"items": [{
            "mission_run_id": "run-a",
            "tenant_id": "tenant-a",
            "goal": "test replay",
            "plan": {"nodes": [{"id": "node-a"}]},
            "actions": [],
        }]})

    def tearDown(self):
        self.temp.cleanup()

    def test_authorized_replay_persists_broker_evidence_lineage(self):
        runtime = _ReplayRuntime()
        app = RouteApp()
        _register(app, self.workspace, runtime)
        handler = app.routes[("POST", "/api/missions/{mission_run_id}/skills/{skill_id}/replay")]
        response = asyncio.run(handler(
            request=_request({"node_id": "node-a"}),
            mission_run_id="run-a",
            skill_id="skill-a",
        ))
        self.assertEqual(response["data"]["replay"]["evidence"]["evidence_id"], "evidence-a")
        self.assertEqual(len(runtime.calls), 1)
        self.assertEqual(runtime.calls[0]["tenant_id"], "tenant-a")
        self.assertEqual(runtime.calls[0]["node_id"], "node-a")
        state = load_mission_runs(self.workspace)
        actions = state["items"][0]["actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action_type"], "skill_replay")
        self.assertEqual(actions[0]["status"], "completed")
        self.assertEqual(actions[0]["evidence_id"], "evidence-a")
        self.assertEqual(actions[0]["experience_id"], "experience-a")
        self.assertTrue(actions[0]["execution_succeeded"])

    def test_cross_tenant_user_is_rejected_before_broker_call(self):
        runtime = _ReplayRuntime()
        app = RouteApp()
        _register(app, self.workspace, runtime, authorized=False)
        handler = app.routes[("POST", "/api/missions/{mission_run_id}/skills/{skill_id}/replay")]
        response = asyncio.run(handler(
            request=_request({"node_id": "node-a"}),
            mission_run_id="run-a",
            skill_id="skill-a",
        ))
        self.assertEqual(response["status"], 403)
        self.assertEqual(runtime.calls, [])
        self.assertEqual(load_mission_runs(self.workspace)["items"][0]["actions"], [])

    def test_recipe_rejection_is_durably_recorded_without_success_evidence(self):
        runtime = _ReplayRuntime(error=ValueError("Recipe candidates cannot be replayed"))
        app = RouteApp()
        _register(app, self.workspace, runtime)
        handler = app.routes[("POST", "/api/missions/{mission_run_id}/skills/{skill_id}/replay")]
        response = asyncio.run(handler(
            request=_request({"node_id": "node-a"}),
            mission_run_id="run-a",
            skill_id="skill-a",
        ))
        self.assertEqual(response["status"], 409)
        action = load_mission_runs(self.workspace)["items"][0]["actions"][0]
        self.assertEqual(action["status"], "failed")
        self.assertNotIn("evidence_id", action)
        self.assertEqual(action["error_type"], "skill_replay_rejected_or_unavailable")

    def test_unknown_node_is_rejected_without_action_or_broker_call(self):
        runtime = _ReplayRuntime()
        app = RouteApp()
        _register(app, self.workspace, runtime)
        handler = app.routes[("POST", "/api/missions/{mission_run_id}/skills/{skill_id}/replay")]
        response = asyncio.run(handler(
            request=_request({"node_id": "not-in-plan"}),
            mission_run_id="run-a",
            skill_id="skill-a",
        ))
        self.assertEqual(response["status"], 400)
        self.assertEqual(runtime.calls, [])
        self.assertEqual(load_mission_runs(self.workspace)["items"][0]["actions"], [])

    def test_missing_broker_configuration_keeps_endpoint_fail_closed(self):
        app = RouteApp()
        _register(app, self.workspace, None)
        handler = app.routes[("POST", "/api/missions/{mission_run_id}/skills/{skill_id}/replay")]
        response = asyncio.run(handler(
            request=_request({"node_id": "node-a"}),
            mission_run_id="run-a",
            skill_id="skill-a",
        ))
        self.assertEqual(response["status"], 503)
        self.assertEqual(load_mission_runs(self.workspace)["items"][0]["actions"], [])


if __name__ == "__main__":
    unittest.main()
