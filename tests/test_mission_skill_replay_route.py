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


def _request(body=None, *, authenticated=True, idempotency_key="11111111-1111-4111-8111-111111111111"):
    payload = json.dumps(body or {}).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    headers = [(b"cookie", b"session=valid")] if authenticated else []
    headers.append((b"idempotency-key", idempotency_key.encode("ascii")))
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/missions/run-a/skills/skill-a/replay",
        "headers": headers,
        "query_string": b"",
    }, receive)


def _get_request(*, tenant_id="tenant-a", authenticated=True):
    headers = [(b"cookie", b"session=valid")] if authenticated else []
    query = f"tenant_id={tenant_id}&limit=20".encode("utf-8") if tenant_id else b"limit=20"
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/missions/skill-replays/recovery-review",
        "headers": headers,
        "query_string": query,
    }, receive)


def _register(app, workspace, runtime, *, authorized=True, role="tenant_admin"):
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
        tenant_role=lambda user, tenant_id: role if authorized and tenant_id == "tenant-a" else None,
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
            "validation": {"status": "not_configured"},
            "promotion": {"status": "not_attempted"},
        }
        self.error = error

    def replay_candidate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error and isinstance(self.error, (FileNotFoundError, PermissionError, ValueError)):
            raise self.error
        callback = kwargs.get("on_candidate_bound")
        if callable(callback):
            context = {
                "tenant_id": "tenant-a",
                "mission_run_id": "run-a",
                "node_id": kwargs["node_id"],
                "task_id": kwargs["task_id"],
            }
            callback({
                "skill_binding": {
                    "schema_version": "mission.skill-replay-binding.v1",
                    "skill_id": kwargs["skill_id"],
                    "skill_version": "1.0.0",
                    "content_sha256": "a" * 64,
                    "trust_level": "draft",
                    "mission_context": context,
                },
                "stage_request_id": "33333333-3333-4333-8333-333333333333",
                "execution_request_id": "44444444-4444-4444-8444-444444444444",
            })
        validation_callback = kwargs.get("on_validation_request_bound")
        if callable(validation_callback):
            validation_callback({"validation_request_id": "55555555-5555-4555-8555-555555555555"})
        promotion_callback = kwargs.get("on_promotion_request_bound")
        if callable(promotion_callback):
            promotion_callback({"promotion_request_id": "66666666-6666-4666-8666-666666666666"})
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
        self.assertEqual(actions[0]["validation_status"], "not_configured")
        self.assertEqual(actions[0]["promotion_status"], "not_attempted")
        self.assertEqual(actions[0]["evidence_id"], "evidence-a")
        self.assertEqual(actions[0]["experience_id"], "experience-a")
        self.assertTrue(actions[0]["execution_succeeded"])
        self.assertEqual(actions[0]["idempotency_key"], "11111111-1111-4111-8111-111111111111")
        self.assertEqual(actions[0]["candidate_skill_version"], "1.0.0")
        self.assertEqual(actions[0]["candidate_content_sha256"], "a" * 64)
        self.assertEqual(actions[0]["stage_request_id"], "33333333-3333-4333-8333-333333333333")
        self.assertEqual(actions[0]["execution_request_id"], "44444444-4444-4444-8444-444444444444")
        self.assertEqual(actions[0]["validation_request_id"], "55555555-5555-4555-8555-555555555555")
        self.assertEqual(actions[0]["promotion_request_id"], "66666666-6666-4666-8666-666666666666")
        self.assertEqual(actions[0]["operation_result"], response["data"])

    def test_same_idempotency_key_returns_cached_operation_without_second_broker_call(self):
        runtime = _ReplayRuntime()
        app = RouteApp()
        _register(app, self.workspace, runtime)
        handler = app.routes[("POST", "/api/missions/{mission_run_id}/skills/{skill_id}/replay")]
        first = asyncio.run(handler(
            request=_request({"node_id": "node-a"}),
            mission_run_id="run-a",
            skill_id="skill-a",
        ))
        second = asyncio.run(handler(
            request=_request({"node_id": "node-a"}),
            mission_run_id="run-a",
            skill_id="skill-a",
        ))
        self.assertEqual(first, second)
        self.assertEqual(len(runtime.calls), 1)
        actions = load_mission_runs(self.workspace)["items"][0]["actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["status"], "completed")

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

    def test_interrupted_replay_requires_review_and_is_not_reexecuted(self):
        save_mission_runs(self.workspace, {"items": [{
            "mission_run_id": "run-a",
            "tenant_id": "tenant-a",
            "goal": "test replay",
            "plan": {"nodes": [{"id": "node-a"}]},
            "actions": [{
                "action_type": "skill_replay",
                "status": "interrupted",
                "recovery_status": "needs_review",
                "recovery_reason": "admin_process_restarted_during_replay",
                "task_id": "task-original",
                "skill_id": "skill-a",
                "node_id": "node-a",
            }],
        }]})
        runtime = _ReplayRuntime()
        app = RouteApp()
        _register(app, self.workspace, runtime)
        handler = app.routes[("POST", "/api/missions/{mission_run_id}/skills/{skill_id}/replay")]
        response = asyncio.run(handler(
            request=_request({"node_id": "node-a"}),
            mission_run_id="run-a",
            skill_id="skill-a",
        ))
        self.assertEqual(response["status"], 409)
        self.assertIn("不得直接重跑", response["error"])
        self.assertEqual(runtime.calls, [])
        actions = load_mission_runs(self.workspace)["items"][0]["actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["task_id"], "task-original")
        self.assertEqual(actions[0]["recovery_status"], "needs_review")

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

    def test_viewer_cannot_trigger_code_execution(self):
        runtime = _ReplayRuntime()
        app = RouteApp()
        _register(app, self.workspace, runtime, role="viewer")
        handler = app.routes[("POST", "/api/missions/{mission_run_id}/skills/{skill_id}/replay")]
        response = asyncio.run(handler(
            request=_request({"node_id": "node-a"}),
            mission_run_id="run-a",
            skill_id="skill-a",
        ))
        self.assertEqual(response["status"], 403)
        self.assertEqual(runtime.calls, [])
        self.assertEqual(load_mission_runs(self.workspace)["items"][0]["actions"], [])

    def test_partial_signed_evidence_reference_survives_experience_projection_failure(self):
        error = RuntimeError("Experience projection failed after evidence persistence")
        error.evidence_ref = {
            "schema_version": "mission.skill-replay-evidence-ref.v1",
            "evidence_id": "evidence-partial",
            "sha256": "a" * 64,
        }
        runtime = _ReplayRuntime(error=error)
        app = RouteApp()
        _register(app, self.workspace, runtime)
        handler = app.routes[("POST", "/api/missions/{mission_run_id}/skills/{skill_id}/replay")]
        response = asyncio.run(handler(
            request=_request({"node_id": "node-a"}),
            mission_run_id="run-a",
            skill_id="skill-a",
        ))
        self.assertEqual(response["status"], 502)
        action = load_mission_runs(self.workspace)["items"][0]["actions"][0]
        self.assertEqual(action["status"], "interrupted")
        self.assertEqual(action["recovery_status"], "needs_review")
        self.assertEqual(action["recovery_reason"], "skill_replay_outcome_indeterminate")
        self.assertEqual(action["evidence_id"], "evidence-partial")
        self.assertEqual(action["evidence_ref"]["sha256"], "a" * 64)

    def test_indeterminate_replay_blocks_a_new_idempotency_key(self):
        runtime = _ReplayRuntime(error=RuntimeError("Broker response outcome is unknown"))
        app = RouteApp()
        _register(app, self.workspace, runtime)
        handler = app.routes[("POST", "/api/missions/{mission_run_id}/skills/{skill_id}/replay")]
        first = asyncio.run(handler(
            request=_request({"node_id": "node-a"}),
            mission_run_id="run-a",
            skill_id="skill-a",
        ))
        second = asyncio.run(handler(
            request=_request(
                {"node_id": "node-a"},
                idempotency_key="22222222-2222-4222-8222-222222222222",
            ),
            mission_run_id="run-a",
            skill_id="skill-a",
        ))
        self.assertEqual(first["status"], 502)
        self.assertEqual(second["status"], 409)
        self.assertEqual(len(runtime.calls), 1)
        actions = load_mission_runs(self.workspace)["items"][0]["actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["status"], "interrupted")
        self.assertEqual(actions[0]["recovery_status"], "needs_review")

    def test_skill_replay_recovery_review_is_tenant_admin_only_and_exposes_pinned_identity(self):
        save_mission_runs(self.workspace, {"items": [
            {
                "mission_run_id": "run-a",
                "tenant_id": "tenant-a",
                "goal": "review interrupted replay",
                "actions": [{
                    "action_type": "skill_replay",
                    "status": "interrupted",
                    "recovery_status": "needs_review",
                    "recovery_reason": "skill_replay_outcome_indeterminate",
                    "task_id": "task-a",
                    "node_id": "node-a",
                    "skill_id": "skill-a",
                    "idempotency_key": "11111111-1111-4111-8111-111111111111",
                    "skill_binding": {
                        "schema_version": "mission.skill-replay-binding.v1",
                        "skill_id": "skill-a",
                        "skill_version": "1.0.0",
                        "content_sha256": "a" * 64,
                        "trust_level": "draft",
                        "mission_context": {
                            "tenant_id": "tenant-a",
                            "mission_run_id": "run-a",
                            "node_id": "node-a",
                            "task_id": "task-a",
                        },
                    },
                    "stage_request_id": "33333333-3333-4333-8333-333333333333",
                    "execution_request_id": "44444444-4444-4444-8444-444444444444",
                }, {
                    "action_type": "skill_replay",
                    "status": "completed",
                    "task_id": "task-done",
                    "node_id": "node-a",
                    "skill_id": "skill-a",
                }],
            },
            {
                "mission_run_id": "run-other",
                "tenant_id": "tenant-other",
                "actions": [{
                    "action_type": "skill_replay",
                    "status": "interrupted",
                    "recovery_status": "needs_review",
                    "task_id": "task-other",
                    "node_id": "node-other",
                    "skill_id": "skill-other",
                }],
            },
        ]})
        app = RouteApp()
        _register(app, self.workspace, _ReplayRuntime())
        handler = app.routes[("GET", "/api/missions/skill-replays/recovery-review")]
        response = asyncio.run(handler(request=_get_request(), tenant_id="tenant-a", limit=20))
        self.assertEqual(response["data"]["count"], 1)
        item = response["data"]["items"][0]
        self.assertEqual(item["candidate_binding_status"], "pinned")
        self.assertEqual(item["skill_binding"]["content_sha256"], "a" * 64)
        self.assertEqual(item["execution_request_id"], "44444444-4444-4444-8444-444444444444")
        self.assertEqual(item["validation_request_id"], "55555555-5555-4555-8555-555555555555")
        self.assertEqual(item["promotion_request_id"], "66666666-6666-4666-8666-666666666666")

        member_app = RouteApp()
        _register(member_app, self.workspace, _ReplayRuntime(), role="member")
        member_handler = member_app.routes[("GET", "/api/missions/skill-replays/recovery-review")]
        denied = asyncio.run(member_handler(request=_get_request(), tenant_id="tenant-a", limit=20))
        self.assertEqual(denied["status"], 403)

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
