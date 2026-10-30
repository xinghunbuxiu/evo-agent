import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from starlette.requests import Request

from admin.routes.missions import register_mission_routes
from admin.mission_runtime import save_mission_runs


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


class MissionWorkerClaimRecoveryRouteTests(unittest.TestCase):
    def test_recovery_review_endpoint_lists_only_claimed_items_needing_review_without_refresh(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            save_mission_runs(workspace, {"items": [
                {
                    "mission_run_id": "run-review",
                    "tenant_id": "tenant-a",
                    "goal": "recover worker",
                    "actions": [{
                        "node_id": "node-a",
                        "title": "inspect task",
                        "task_id": "task-missing",
                        "worker_claim": {
                            "claim_id": "claim-a",
                            "worker_id": "worker-a",
                            "state": "claimed",
                            "recovery_status": "needs_review",
                            "recovery_reason": "queue_task_missing",
                            "recovery_checked_at": "2026-10-29T10:00:00+08:00",
                        },
                    }],
                },
                {
                    "mission_run_id": "run-released",
                    "tenant_id": "tenant-a",
                    "actions": [{
                        "task_id": "task-done",
                        "worker_claim": {
                            "claim_id": "claim-b",
                            "worker_id": "worker-b",
                            "state": "released",
                            "recovery_status": "recovered",
                        },
                    }],
                },
                {
                    "mission_run_id": "run-other-tenant",
                    "tenant_id": "tenant-b",
                    "actions": [{
                        "task_id": "task-other",
                        "worker_claim": {
                            "claim_id": "claim-c",
                            "worker_id": "worker-c",
                            "state": "claimed",
                            "recovery_status": "needs_review",
                        },
                    }],
                },
            ]})

            refresh_calls = []
            app = RouteApp()
            register_mission_routes(
                app,
                workspace=workspace,
                task_queue=object(),
                tenant_manager=object(),
                prepare_mission_work_type_bundle=lambda **kwargs: {},
                mission_planner=object(),
                upsert_plan_learning_tasks=lambda **kwargs: [],
                refresh_mission_runs=lambda **kwargs: refresh_calls.append(kwargs) or {"items": []},
                start_mission=lambda *args, **kwargs: (None, None),
                find_mission_run=lambda *args: None,
                derive_follow_up_goal=lambda run: "",
                derive_follow_up_context=lambda run: {},
                success_response=lambda data, message="": {"data": data, "message": message},
                error_response=lambda message, status: {"error": message, "status": status},
                get_session_user=lambda request: {"id": 7} if request.cookies.get("session") == "valid" else None,
                authorize_tenant=lambda user, tenant_id: user.get("id") == 7 and tenant_id == "tenant-a",
            )

            handler = app.routes[("GET", "/api/missions/worker-claims/recovery-review")]
            request = Request({"type": "http", "method": "GET", "path": "/api/missions/worker-claims/recovery-review", "headers": [(b"cookie", b"session=valid")], "query_string": b""})
            response = asyncio.run(handler(request=request, tenant_id="tenant-a", limit=100))

            self.assertEqual(response["data"]["count"], 1)
            item = response["data"]["items"][0]
            self.assertEqual(item["mission_run_id"], "run-review")
            self.assertEqual(item["task_id"], "task-missing")
            self.assertEqual(item["worker_claim"]["recovery_reason"], "queue_task_missing")
            self.assertEqual(refresh_calls, [])

            anonymous_request = Request({"type": "http", "method": "GET", "path": "/api/missions/worker-claims/recovery-review", "headers": [], "query_string": b""})
            anonymous = asyncio.run(handler(request=anonymous_request, tenant_id="tenant-a", limit=100))
            self.assertEqual(anonymous["status"], 401)

            cross_tenant_request = Request({"type": "http", "method": "GET", "path": "/api/missions/worker-claims/recovery-review", "headers": [(b"cookie", b"session=valid")], "query_string": b""})
            forbidden = asyncio.run(handler(request=cross_tenant_request, tenant_id="tenant-b", limit=100))
            self.assertEqual(forbidden["status"], 403)

            missing_tenant = asyncio.run(handler(request=cross_tenant_request, tenant_id=None, limit=100))
            self.assertEqual(missing_tenant["status"], 400)


if __name__ == "__main__":
    unittest.main()
