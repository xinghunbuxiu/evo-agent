"""Tests for tenant-authenticated Experience Reflection APIs."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from starlette.requests import Request

from admin.routes.experience_reflections import register_experience_reflection_routes
from core import Experience, ExperienceStore


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


def make_request(method, path, body=None, *, actor_id=1, role="member", authorized=True, key=None):
    payload = json.dumps(body or {}).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    headers = [(b"cookie", b"session=valid")]
    if key:
        headers.append((b"idempotency-key", key.encode("ascii")))
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers,
        "query_string": b"",
    }, receive)


class ExperienceReflectionRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        ExperienceStore(self.workspace, "tenant-a").save(Experience(
            id="source-1",
            domain="android",
            task_type="analysis",
            input_summary="source input",
            output_summary="source result",
            quality_score=0.8,
            metadata={"evidence_ids": ["evidence-1"]},
        ))
        self.current_user = {"id": 1, "auth_provider": "password"}
        self.role = "member"
        self.authorized = True
        self.app = RouteApp()
        register_experience_reflection_routes(
            self.app,
            workspace=self.workspace,
            get_session_user=lambda request: self.current_user if request.cookies.get("session") == "valid" else None,
            authorize_tenant=lambda user, tenant: self.authorized and tenant == "tenant-a",
            tenant_role=lambda user, tenant: self.role if self.authorized and tenant == "tenant-a" else None,
            success_response=lambda data, message="": {"data": data, "message": message},
            error_response=lambda message, status: {"error": message, "status": status},
        )

    def tearDown(self):
        self.temp.cleanup()

    def submit(self):
        handler = self.app.routes[("POST", "/api/tenants/{tenant_id}/experience-reflections")]
        return asyncio.run(handler(
            make_request("POST", "/api/tenants/tenant-a/experience-reflections", {
                "source_experience_id": "source-1",
                "findings": {
                    "observed_outcome": "Observed",
                    "steps": ["Inspect the evidence", "Apply the verified correction"],
                },
                "source_evidence_refs": ["evidence-1"],
            }, key="11111111-1111-4111-8111-111111111111"),
            tenant_id="tenant-a",
        ))

    def test_submit_derives_author_and_tenant_from_authenticated_context(self):
        response = self.submit()
        self.assertIn("reflection", response["data"])
        payload = response["data"]["reflection"]["metadata"]["experience_reflection"]
        self.assertEqual(payload["tenant_id"], "tenant-a")
        self.assertEqual(payload["author"], "password:1")
        self.assertEqual(payload["state"], "pending")

    def test_submit_rejects_client_supplied_identity_fields(self):
        handler = self.app.routes[("POST", "/api/tenants/{tenant_id}/experience-reflections")]
        response = asyncio.run(handler(
            make_request("POST", "/api/tenants/tenant-a/experience-reflections", {
                "tenant_id": "tenant-b",
                "author": "tenant-b:admin",
                "source_experience_id": "source-1",
                "findings": {"observed_outcome": "Observed"},
            }, key="11111111-1111-4111-8111-111111111112"),
            tenant_id="tenant-a",
        ))
        self.assertEqual(response["status"], 400)

    def test_cross_tenant_access_is_denied(self):
        self.authorized = False
        response = self.submit()
        self.assertEqual(response["status"], 403)

    def test_viewer_cannot_submit(self):
        self.role = "viewer"
        response = self.submit()
        self.assertEqual(response["status"], 403)

    def test_admin_can_decide_but_author_cannot_self_review(self):
        submitted = self.submit()["data"]["reflection"]
        reflection_id = submitted["id"]
        decide = self.app.routes[("POST", "/api/tenants/{tenant_id}/experience-reflections/{reflection_id}/decision")]
        self.role = "tenant_admin"
        self.current_user = {"id": 1, "auth_provider": "password"}
        self_review = asyncio.run(decide(
            make_request("POST", "decision", {"decision": "accepted"}, key="22222222-2222-4222-8222-222222222221"),
            tenant_id="tenant-a",
            reflection_id=reflection_id,
        ))
        self.assertEqual(self_review["status"], 403)
        self.current_user = {"id": 2, "auth_provider": "password"}
        accepted = asyncio.run(decide(
            make_request("POST", "decision", {"decision": "accepted"}, key="22222222-2222-4222-8222-222222222222"),
            tenant_id="tenant-a",
            reflection_id=reflection_id,
        ))
        self.assertEqual(accepted["data"]["decision"]["metadata"]["experience_reflection_decision"]["decision"], "accepted")

    def test_review_queue_lists_all_tenant_reflections(self):
        self.submit()
        handler = self.app.routes[("GET", "/api/tenants/{tenant_id}/experience-reflections")]
        response = asyncio.run(handler(
            make_request("GET", "/api/tenants/tenant-a/experience-reflections"),
            tenant_id="tenant-a",
        ))
        self.assertEqual(len(response["data"]["items"]), 1)
        self.assertEqual(response["data"]["items"][0]["effective_state"], "pending")

    def test_member_cannot_decide(self):
        submitted = self.submit()["data"]["reflection"]
        handler = self.app.routes[("POST", "/api/tenants/{tenant_id}/experience-reflections/{reflection_id}/decision")]
        response = asyncio.run(handler(
            make_request("POST", "decision", {"decision": "accepted"}, key="22222222-2222-4222-8222-222222222223"),
            tenant_id="tenant-a",
            reflection_id=submitted["id"],
        ))
        self.assertEqual(response["status"], 403)

    def test_admin_can_generate_recipe_from_accepted_reflection(self):
        submitted = self.submit()["data"]["reflection"]
        reflection_id = submitted["id"]
        self.role = "tenant_admin"
        self.current_user = {"id": 2, "auth_provider": "password"}
        decide = self.app.routes[("POST", "/api/tenants/{tenant_id}/experience-reflections/{reflection_id}/decision")]
        accepted = asyncio.run(decide(
            make_request("POST", "decision", {"decision": "accepted"}, key="22222222-2222-4222-8222-222222222224"),
            tenant_id="tenant-a",
            reflection_id=reflection_id,
        ))
        self.assertIn("decision", accepted["data"])
        create_recipe = self.app.routes[("POST", "/api/tenants/{tenant_id}/experience-reflections/{reflection_id}/recipe")]
        response = asyncio.run(create_recipe(
            make_request("POST", "recipe"),
            tenant_id="tenant-a",
            reflection_id=reflection_id,
        ))
        self.assertEqual(response["data"]["recipe"]["trust_level"], "draft")
        self.assertTrue(response["data"]["recipe"]["skill_id"].startswith("recipe-"))
        self.assertTrue(Path(response["data"]["recipe"]["visible_path"]).is_file())

    def test_admin_can_create_executable_candidate_from_accepted_reflection(self):
        submitted = self.submit()["data"]["reflection"]
        reflection_id = submitted["id"]
        self.role = "tenant_admin"
        self.current_user = {"id": 2, "auth_provider": "password"}
        decide = self.app.routes[("POST", "/api/tenants/{tenant_id}/experience-reflections/{reflection_id}/decision")]
        accepted = asyncio.run(decide(
            make_request("POST", "decision", {"decision": "accepted"}, key="22222222-2222-4222-8222-222222222230"),
            tenant_id="tenant-a", reflection_id=reflection_id,
        ))
        self.assertIn("decision", accepted["data"])
        create_candidate = self.app.routes[("POST", "/api/tenants/{tenant_id}/experience-reflections/{reflection_id}/executable-candidate")]
        response = asyncio.run(create_candidate(
            make_request("POST", "candidate", {
                "name": "Validate source result",
                "domain": "python",
                "description": "Validate the supplied result.",
                "code": "def run(context):\n    return context.get('ok') is True\n",
            }),
            tenant_id="tenant-a", reflection_id=reflection_id,
        ))
        candidate = response["data"]["candidate"]
        self.assertEqual(candidate["trust_level"], "draft")
        self.assertEqual(candidate["replay_status"], "awaiting_broker_replay")
        self.assertTrue(Path(candidate["visible_path"]).is_file())

    def test_member_cannot_create_executable_candidate(self):
        submitted = self.submit()["data"]["reflection"]
        create_candidate = self.app.routes[("POST", "/api/tenants/{tenant_id}/experience-reflections/{reflection_id}/executable-candidate")]
        response = asyncio.run(create_candidate(
            make_request("POST", "candidate", {
                "name": "No",
                "domain": "python",
                "description": "No",
                "code": "def run(context):\n    return context\n",
            }),
            tenant_id="tenant-a", reflection_id=submitted["id"],
        ))
        self.assertEqual(response["status"], 403)

    def test_member_cannot_generate_recipe_skill(self):
        submitted = self.submit()["data"]["reflection"]
        create_recipe = self.app.routes[("POST", "/api/tenants/{tenant_id}/experience-reflections/{reflection_id}/recipe")]
        response = asyncio.run(create_recipe(
            make_request("POST", "recipe"),
            tenant_id="tenant-a",
            reflection_id=submitted["id"],
        ))
        self.assertEqual(response["status"], 403)


if __name__ == "__main__":
    unittest.main()
