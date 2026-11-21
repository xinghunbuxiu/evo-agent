import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from starlette.requests import Request

from admin.mission_runtime import load_mission_runs, save_mission_runs
from admin.routes.missions import register_mission_routes
from core.organization_runtime import OrganizationRegistry


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


class Queue:
    def get_task(self, task_id):
        return SimpleNamespace(status=SimpleNamespace(value="success"))


def make_request(payload, *, authenticated=True):
    body = json.dumps(payload).encode("utf-8")
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    headers = [(b"content-type", b"application/json")]
    if authenticated:
        headers.append((b"cookie", b"session=valid"))
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/missions/worker-claims/claim-a/release",
        "headers": headers,
        "query_string": b"",
    }, receive)


class MissionWorkerClaimReleaseRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.registry = OrganizationRegistry(self.workspace)
        self.registry.create_role(
            role_id="android",
            title="Android",
            responsibilities=["execute"],
            required_capabilities=["android"],
        )
        self.registry.create_worker(
            worker_id="worker-a",
            role_id="android",
            profile={"handler_id": "android"},
        )
        self.registry.claim_worker_task(worker_id="worker-a", task_id="claim-a")
        save_mission_runs(self.workspace, {"items": [{
            "mission_run_id": "run-a",
            "tenant_id": "tenant-a",
            "actions": [{
                "task_id": "task-a",
                "worker_claim": {
                    "claim_id": "claim-a",
                    "worker_id": "worker-a",
                    "state": "claimed",
                    "recovery_status": "needs_review",
                },
            }],
        }]})
        self.role = "tenant_admin"
        self.app = RouteApp()
        register_mission_routes(
            self.app,
            workspace=self.workspace,
            task_queue=Queue(),
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
            get_session_user=lambda request: {"id": 7, "auth_provider": "password"} if request.cookies.get("session") == "valid" else None,
            authorize_tenant=lambda user, tenant_id: tenant_id == "tenant-a",
            tenant_role=lambda user, tenant_id: self.role if tenant_id == "tenant-a" else None,
            organization_registry=self.registry,
        )

    def test_tenant_admin_can_release_and_audit_claim(self):
        handler = self.app.routes[("POST", "/api/missions/worker-claims/{claim_id}/release")]
        response = asyncio.run(handler(
            request=make_request({
                "tenant_id": "tenant-a",
                "mission_run_id": "run-a",
                "reason": "Reviewed task status and confirmed terminal completion",
            }),
            claim_id="claim-a",
        ))
        self.assertEqual(response["data"]["state"], "released")
        claim = load_mission_runs(self.workspace)["items"][0]["actions"][0]["worker_claim"]
        self.assertEqual(claim["state"], "released")
        self.assertEqual(self.registry.get_worker("worker-a")["status"], "available")

    def test_member_and_viewer_cannot_release_claim(self):
        handler = self.app.routes[("POST", "/api/missions/worker-claims/{claim_id}/release")]
        for role in ("member", "viewer", None):
            with self.subTest(role=role):
                self.role = role
                response = asyncio.run(handler(
                    request=make_request({
                        "tenant_id": "tenant-a",
                        "mission_run_id": "run-a",
                        "reason": "Reviewed task status and confirmed terminal completion",
                    }),
                    claim_id="claim-a",
                ))
                self.assertEqual(response["status"], 403)
        self.assertEqual(self.registry.get_worker("worker-a")["status"], "busy")

    def test_anonymous_cannot_release_claim(self):
        handler = self.app.routes[("POST", "/api/missions/worker-claims/{claim_id}/release")]
        response = asyncio.run(handler(
            request=make_request({
                "tenant_id": "tenant-a",
                "mission_run_id": "run-a",
                "reason": "Reviewed task status and confirmed terminal completion",
            }, authenticated=False),
            claim_id="claim-a",
        ))
        self.assertEqual(response["status"], 401)
        self.assertEqual(self.registry.get_worker("worker-a")["status"], "busy")


if __name__ == "__main__":
    unittest.main()
