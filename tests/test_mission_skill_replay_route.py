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

    def broker_request_status(self, request_id, mission_context):
        return {"status": "completed"}

    def validator_request_status(self, request_id, mission_context):
        return {"status": "indeterminate"}

    def verify_recovery_responses(self, **kwargs):
        return {
            "broker_execution": "verified",
            "validator": "not_checked",
            "execution_succeeded": True,
            "validation_id": None,
            "broker_promotion": "not_checked",
        }

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

    def test_admin_confirmed_recovery_resumes_only_promotion_and_reconciles_mission(self):
        action = {
            "action_type": "skill_replay",
            "status": "interrupted",
            "recovery_status": "needs_review",
            "task_id": "task-a",
            "node_id": "node-a",
            "skill_id": "skill-a",
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
            "validation_request_id": "55555555-5555-4555-8555-555555555555",
            "promotion_request_id": "66666666-6666-4666-8666-666666666666",
        }
        save_mission_runs(self.workspace, {"items": [{
            "mission_run_id": "run-a",
            "tenant_id": "tenant-a",
            "plan": {"nodes": [{"id": "node-a"}]},
            "actions": [action],
        }]})
        runtime = _ReplayRuntime()
        calls = []
        runtime.resume_promotion = lambda **kwargs: (
            calls.append(kwargs) or {
                "status": "published",
                "artifact": {"skill_id": "skill-a", "version": "1.0.0"},
                "validation_provenance": {"validation_id": "validation-a"},
            }
        )
        app = RouteApp()
        _register(app, self.workspace, runtime)
        route = "/api/missions/{mission_run_id}/skills/{skill_id}/recovery/{task_id}/resume-promotion"
        handler = app.routes[("POST", route)]
        response = asyncio.run(handler(
            request=_request({"confirm": True}),
            mission_run_id="run-a",
            skill_id="skill-a",
            task_id="task-a",
        ))
        self.assertEqual(response["data"]["status"], "reconciled")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["promotion_request_id"], action["promotion_request_id"])
        self.assertEqual(calls[0]["skill_binding"], action["skill_binding"])
        self.assertEqual(calls[0]["tenant_id"], "tenant-a")
        saved = load_mission_runs(self.workspace)["items"][0]["actions"][0]
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["recovery_status"], "reconciled")
        self.assertEqual(saved["promotion_status"], "published")
        self.assertEqual(saved["published_artifact"]["skill_id"], "skill-a")
        self.assertEqual(saved["recovery_attempts"][-1]["operation"], "resume_promotion_only")
        self.assertEqual(saved["recovery_attempts"][-1]["status"], "completed")

    def test_stale_in_progress_recovery_lease_can_be_retried_with_audit(self):
        from datetime import datetime, timedelta

        action = {
            "action_type": "skill_replay",
            "status": "interrupted",
            "recovery_status": "needs_review",
            "recovery_attempt_status": "in_progress",
            "recovery_attempt_id": "77777777-7777-4777-8777-777777777777",
            "recovery_attempts": [{
                "attempt_id": "77777777-7777-4777-8777-777777777777",
                "operation": "resume_promotion_only",
                "status": "in_progress",
                "started_at": (datetime.now().astimezone() - timedelta(hours=1)).isoformat(),
            }],
            "task_id": "task-a",
            "node_id": "node-a",
            "skill_id": "skill-a",
            "skill_binding": {
                "schema_version": "mission.skill-replay-binding.v1",
                "skill_id": "skill-a", "skill_version": "1.0.0",
                "content_sha256": "a" * 64, "trust_level": "draft",
                "mission_context": {
                    "tenant_id": "tenant-a", "mission_run_id": "run-a",
                    "node_id": "node-a", "task_id": "task-a",
                },
            },
            "stage_request_id": "33333333-3333-4333-8333-333333333333",
            "execution_request_id": "44444444-4444-4444-8444-444444444444",
            "validation_request_id": "55555555-5555-4555-8555-555555555555",
            "promotion_request_id": "66666666-6666-4666-8666-666666666666",
        }
        save_mission_runs(self.workspace, {"items": [{
            "mission_run_id": "run-a", "tenant_id": "tenant-a",
            "plan": {"nodes": [{"id": "node-a"}]}, "actions": [action],
        }]})
        runtime = _ReplayRuntime()
        calls = []
        runtime.resume_promotion = lambda **kwargs: (
            calls.append(kwargs) or {
                "status": "published",
                "artifact": {"skill_id": "skill-a", "version": "1.0.0"},
            }
        )
        app = RouteApp()
        _register(app, self.workspace, runtime)
        route = "/api/missions/{mission_run_id}/skills/{skill_id}/recovery/{task_id}/resume-promotion"
        response = asyncio.run(app.routes[("POST", route)](
            request=_request({"confirm": True}),
            mission_run_id="run-a", skill_id="skill-a", task_id="task-a",
        ))
        self.assertEqual(response["data"]["status"], "reconciled")
        self.assertEqual(len(calls), 1)
        saved = load_mission_runs(self.workspace)["items"][0]["actions"][0]
        previous = next(
            item for item in saved["recovery_attempts"]
            if item["attempt_id"] == "77777777-7777-4777-8777-777777777777"
        )
        self.assertEqual(previous["status"], "indeterminate")
        self.assertEqual(previous["recovery_reason"], "recovery_lease_expired")
        self.assertEqual(saved["recovery_attempts"][-1]["status"], "completed")

    def test_active_recovery_lease_blocks_concurrent_resume(self):
        from datetime import datetime, timedelta

        attempt_id = "77777777-7777-4777-8777-777777777777"
        action = {
            "action_type": "skill_replay",
            "status": "interrupted",
            "recovery_status": "needs_review",
            "recovery_attempt_status": "in_progress",
            "recovery_attempt_id": attempt_id,
            "recovery_attempts": [{
                "attempt_id": attempt_id,
                "operation": "resume_promotion_only",
                "status": "in_progress",
                "started_at": (datetime.now().astimezone() - timedelta(minutes=2)).isoformat(),
            }],
            "task_id": "task-a",
            "node_id": "node-a",
            "skill_id": "skill-a",
        }
        save_mission_runs(self.workspace, {"items": [{
            "mission_run_id": "run-a", "tenant_id": "tenant-a",
            "plan": {"nodes": [{"id": "node-a"}]}, "actions": [action],
        }]})
        runtime = _ReplayRuntime()
        runtime.resume_promotion = lambda **kwargs: self.fail(
            "an unexpired recovery lease must prevent a concurrent promotion"
        )
        app = RouteApp()
        _register(app, self.workspace, runtime)
        route = "/api/missions/{mission_run_id}/skills/{skill_id}/recovery/{task_id}/resume-promotion"
        response = asyncio.run(app.routes[("POST", route)](
            request=_request({"confirm": True}),
            mission_run_id="run-a", skill_id="skill-a", task_id="task-a",
        ))
        self.assertEqual(response["status"], 409)
        saved = load_mission_runs(self.workspace)["items"][0]["actions"][0]
        self.assertEqual(saved["recovery_attempt_status"], "in_progress")
        self.assertEqual(saved["recovery_attempt_id"], attempt_id)
        self.assertEqual(len(saved["recovery_attempts"]), 1)
        self.assertEqual(saved["recovery_attempts"][0]["status"], "in_progress")

    def test_in_progress_recovery_with_untrusted_timestamp_fails_closed(self):
        action = {
            "action_type": "skill_replay", "status": "interrupted",
            "recovery_status": "needs_review", "recovery_attempt_status": "in_progress",
            "recovery_attempt_id": "77777777-7777-4777-8777-777777777777",
            "recovery_attempts": [{
                "attempt_id": "77777777-7777-4777-8777-777777777777",
                "status": "in_progress", "started_at": "not-a-timestamp",
            }],
            "task_id": "task-a", "node_id": "node-a", "skill_id": "skill-a",
        }
        save_mission_runs(self.workspace, {"items": [{
            "mission_run_id": "run-a", "tenant_id": "tenant-a",
            "plan": {"nodes": [{"id": "node-a"}]}, "actions": [action],
        }]})
        runtime = _ReplayRuntime()
        runtime.resume_promotion = lambda **kwargs: self.fail("untrusted lease must not dispatch")
        app = RouteApp()
        _register(app, self.workspace, runtime)
        route = "/api/missions/{mission_run_id}/skills/{skill_id}/recovery/{task_id}/resume-promotion"
        response = asyncio.run(app.routes[("POST", route)](
            request=_request({"confirm": True}),
            mission_run_id="run-a", skill_id="skill-a", task_id="task-a",
        ))
        self.assertEqual(response["status"], 409)
        saved = load_mission_runs(self.workspace)["items"][0]["actions"][0]
        self.assertEqual(saved["recovery_attempt_status"], "in_progress")
        self.assertEqual(len(saved["recovery_attempts"]), 1)


    def test_recovery_requires_explicit_confirmation_and_tenant_admin(self):
        runtime = _ReplayRuntime()
        runtime.resume_promotion = lambda **kwargs: self.fail("must not dispatch")
        app = RouteApp()
        _register(app, self.workspace, runtime, role="member")
        route = "/api/missions/{mission_run_id}/skills/{skill_id}/recovery/{task_id}/resume-promotion"
        handler = app.routes[("POST", route)]
        denied = asyncio.run(handler(
            request=_request({"confirm": True}),
            mission_run_id="run-a", skill_id="skill-a", task_id="task-a",
        ))
        self.assertEqual(denied["status"], 403)
        bad_confirmation = asyncio.run(handler(
            request=_request({"confirm": "yes"}),
            mission_run_id="run-a", skill_id="skill-a", task_id="task-a",
        ))
        self.assertEqual(bad_confirmation["status"], 400)

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
                    "validation_request_id": "55555555-5555-4555-8555-555555555555",
                    "promotion_request_id": "66666666-6666-4666-8666-666666666666",
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
        self.assertEqual(item["broker_status"]["stage"]["status"], "completed")
        self.assertEqual(item["broker_status"]["execution"]["status"], "completed")
        self.assertEqual(item["broker_status"]["promotion"]["status"], "completed")
        self.assertEqual(item["validator_status"]["status"], "indeterminate")
        self.assertEqual(item["verified_receipts"]["broker_execution"], "verified")
        self.assertEqual(item["verified_receipts"]["validator"], "not_checked")
        self.assertEqual(item["recovery_assessment"]["status"], "indeterminate")
        self.assertFalse(item["recovery_assessment"]["automatic_resume"])
        self.assertEqual(item["recovery_assessment"]["next_step"], "operator_review_required_no_replay")

        member_app = RouteApp()
        _register(member_app, self.workspace, _ReplayRuntime(), role="member")
        member_handler = member_app.routes[("GET", "/api/missions/skill-replays/recovery-review")]
        denied = asyncio.run(member_handler(request=_get_request(), tenant_id="tenant-a", limit=20))
        self.assertEqual(denied["status"], 403)

    def test_recovery_review_reports_not_found_without_authorizing_automatic_replay(self):
        save_mission_runs(self.workspace, {"items": [{
            "mission_run_id": "run-a",
            "tenant_id": "tenant-a",
            "goal": "review missing Broker request",
            "actions": [{
                "action_type": "skill_replay",
                "status": "interrupted",
                "recovery_status": "needs_review",
                "task_id": "task-a",
                "node_id": "node-a",
                "skill_id": "skill-a",
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
                "validation_request_id": "55555555-5555-4555-8555-555555555555",
                "promotion_request_id": "66666666-6666-4666-8666-666666666666",
            }],
        }]})
        runtime = _ReplayRuntime()
        runtime.broker_request_status = lambda request_id, mission_context: {
            "status": "not_found" if request_id == "66666666-6666-4666-8666-666666666666" else "completed"
        }
        runtime.validator_request_status = lambda request_id, mission_context: {"status": "completed"}
        app = RouteApp()
        _register(app, self.workspace, runtime)
        handler = app.routes[("GET", "/api/missions/skill-replays/recovery-review")]
        response = asyncio.run(handler(request=_get_request(), tenant_id="tenant-a", limit=20))
        item = response["data"]["items"][0]
        self.assertEqual(item["recovery_assessment"]["status"], "not_found")
        self.assertFalse(item["recovery_assessment"]["automatic_resume"])
        self.assertEqual(
            item["recovery_assessment"]["next_step"],
            "verify_original_immutable_payload_before_same_request_reissue",
        )

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


    def test_real_runtime_reconciles_completed_broker_publication_through_admin_route(self):
        from unittest.mock import patch
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from core import Skill, SkillTrustLevel
        from core.skill_replay_contract import build_skill_replay_binding
        from admin.knowledge_runtime import write_skill_candidate
        from admin.skill_replay_runtime import (
            create_skill_replay_runtime,
            _deterministic_request_id,
        )

        root = self.workspace.parent
        evidence_root = root / "evidence"
        evidence_root.mkdir(mode=0o700)
        broker_key_path = root / "broker.pub"
        broker_key = Ed25519PrivateKey.generate()
        broker_key_path.write_bytes(broker_key.public_key().public_bytes_raw())
        broker_key_path.chmod(0o400)
        validator_key_path = root / "validator.pub"
        validator_key = Ed25519PrivateKey.generate()
        validator_key_path.write_bytes(validator_key.public_key().public_bytes_raw())
        validator_key_path.chmod(0o400)
        environ = {
            "EVO_SKILL_REPLAY_BROKER_SOCKET": "/run/evo-sandbox-broker.sock",
            "EVO_SKILL_REPLAY_WORKSPACE_ID": "workspace-a",
            "EVO_SKILL_REPLAY_BROKER_PUBLIC_KEY": str(broker_key_path),
            "EVO_SKILL_REPLAY_BROKER_KEY_ID": "broker-test-key",
            "EVO_SKILL_REPLAY_EVIDENCE_ROOT": str(evidence_root),
            "EVO_SKILL_REPLAY_VALIDATOR_SOCKET": "/run/evo-skill-validator.sock",
            "EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY": str(validator_key_path),
            "EVO_SKILL_REPLAY_VALIDATOR_KEY_ID": "validator-test-key",
        }
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=environ)
        skill = Skill(
            id="skill-a",
            name="Recovery integration Skill",
            domain="python",
            description="test immutable publication reconciliation",
            code="def run(context):\n    return {'ok': True}\n",
            parameters={
                "mission_run_id": "run-a",
                "mission_node_id": "node-a",
                "execution_contract": {
                    "kind": "python_run_context",
                    "replay_eligible": True,
                },
            },
            trust_level=SkillTrustLevel.DRAFT,
            version="1.0.0",
        )
        write_skill_candidate(self.workspace, "tenant-a", skill)

        context = {
            "tenant_id": "tenant-a",
            "mission_run_id": "run-a",
            "node_id": "node-a",
            "task_id": "task-a",
        }
        binding = build_skill_replay_binding(skill, context)
        stage_id = "33333333-3333-4333-8333-333333333333"
        execution_id = "44444444-4444-4444-8444-444444444444"
        validation_id = "55555555-5555-4555-8555-555555555555"
        validation_attestation = {
            "validation_id": "validation-a",
            "validator_id": "validator-independent",
            "policy_id": "policy-a",
            "policy_sha256": "a" * 64,
            "checks_sha256": "b" * 64,
        }
        promotion_id = _deterministic_request_id("promotion", {
            "mission_context": context,
            "skill_id": skill.id,
            "skill_version": skill.version,
            "content_sha256": binding["content_sha256"],
            "validation_attestation": validation_attestation,
        })
        artifact = {
            "schema_version": "mission.skill-artifact.v2",
            "tenant_id": "tenant-a",
            "skill_id": "skill-a",
            "skill_version": "1.0.0",
            "content_sha256": binding["content_sha256"],
            "trust_level": "verified",
        }
        provenance = {
            "schema_version": "mission.skill-validation-provenance.v1",
            "validation_id": "validation-a",
            "validator_id": "validator-independent",
        }
        promotion_receipt = {
            "artifact": artifact,
            "validation_provenance": provenance,
        }
        runtime.broker_request_status = lambda request_id, mission_context: {
            "status": "completed",
            "response": (
                promotion_receipt
                if request_id == promotion_id
                else {"receipt": request_id}
            ),
        }
        runtime.validator_request_status = lambda request_id, mission_context: {
            "status": "completed",
            "response": {"attestation": "original-validator-receipt"},
        }
        runtime.verify_recovery_responses = lambda **kwargs: {
            "broker_stage": "verified",
            "broker_execution": "verified",
            "execution_succeeded": True,
            "validator": "verified",
            "validation_id": "validation-a",
            "broker_promotion": "verified",
        }
        runtime.adapter.execute = lambda *args, **kwargs: self.fail(
            "reconciliation must never execute Skill code"
        )

        save_mission_runs(self.workspace, {"items": [{
            "mission_run_id": "run-a",
            "tenant_id": "tenant-a",
            "plan": {"nodes": [{"id": "node-a"}]},
            "actions": [{
                "action_type": "skill_replay",
                "status": "interrupted",
                "recovery_status": "needs_review",
                "task_id": "task-a",
                "node_id": "node-a",
                "skill_id": "skill-a",
                "skill_binding": binding,
                "stage_request_id": stage_id,
                "execution_request_id": execution_id,
                "validation_request_id": validation_id,
                "promotion_request_id": promotion_id,
            }],
        }]})

        app = RouteApp()
        _register(app, self.workspace, runtime)
        review = asyncio.run(app.routes[(
            "GET", "/api/missions/skill-replays/recovery-review"
        )](request=_get_request(), tenant_id="tenant-a", limit=20))
        review_item = review["data"]["items"][0]
        self.assertEqual(
            review_item["recovery_assessment"]["status"],
            "artifact_published_verified",
        )
        self.assertEqual(
            review_item["recovery_assessment"]["next_step"],
            "human_reconcile_mission_from_verified_immutable_artifact",
        )
        self.assertFalse(review_item["recovery_assessment"]["automatic_resume"])

        route = (
            "/api/missions/{mission_run_id}/skills/{skill_id}/recovery/"
            "{task_id}/resume-promotion"
        )
        with patch(
            "admin.skill_replay_runtime.verify_validation_response",
            return_value=validation_attestation,
        ), patch(
            "admin.skill_replay_runtime.promote_skill_candidate_via_broker",
            side_effect=AssertionError("completed publication must not be published again"),
        ) as publish:
            response = asyncio.run(app.routes[("POST", route)](
                request=_request({"confirm": True}),
                mission_run_id="run-a",
                skill_id="skill-a",
                task_id="task-a",
            ))

        self.assertEqual(response["data"]["status"], "reconciled")
        self.assertEqual(response["data"]["artifact"], artifact)
        self.assertEqual(response["data"]["validation_provenance"], provenance)
        publish.assert_not_called()
        saved = load_mission_runs(self.workspace)["items"][0]["actions"][0]
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["recovery_status"], "reconciled")
        self.assertEqual(saved["promotion_status"], "published")
        self.assertEqual(saved["published_artifact"], artifact)
        self.assertEqual(saved["recovery_attempt_status"], "completed")
        self.assertEqual(
            saved["recovery_attempts"][-1]["operation"],
            "reconcile_existing_publication",
        )
        self.assertTrue(
            saved["recovery_attempts"][-1]["reconciled_existing_publication"]
        )

if __name__ == "__main__":
    unittest.main()
