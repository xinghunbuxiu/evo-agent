"""Runtime dispatch must validate Mission authorization before a worker can submit tasks."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_action_runtime import create_mission_action_runtime_bindings  # noqa: E402
from core.mission_brain import build_mission_brain_contract  # noqa: E402
from workers.javascript_reverse.runtime import handle_javascript_reverse_mission_node  # noqa: E402
from workers.self_media_operations.runtime import handle_self_media_operation_mission_node  # noqa: E402


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
    def _build(self, runtime_worker_id):
        trace = [{
            "step": "workforce_catalog_match",
            "rule_id": "mission.workforce_recommendation.v1",
            "result": "assign_existing_worker_recommended",
            "evidence": {"recommended_worker_id": "worker-a"},
        }]
        node = {
            "id": "analyze-bundle",
            "title": "Analyze JavaScript bundle",
            "task_type": "analyze",
            "status": "ready",
            "reasoning": [],
            "blockers": [],
            "recommended_skill_ids": [],
            "recommended_skills": [],
            "recommended_strategies": [{
                "id": "js-bundle-inspection",
                "name": "Inspect bundle entrypoints first",
                "domain": "javascript",
                "description": "Trace entrypoints before deeper analysis",
                "steps": [{"action": "inspect_entrypoints"}],
                "success_rate": 0.75,
                "usage_count": 4,
            }],
            "validation_checks": ["analysis result reviewed"],
            "decision_trace": trace,
            "parallel_safe": False,
            "workforce_decision": {
                "decision": "assign_existing_worker_recommended",
                "recommended_worker_id": "worker-a",
                "dispatch_state": "recommendation_only",
                "dispatch_authorized": False,
            },
        }
        contract = build_mission_brain_contract([node])
        queue = FakeTaskQueue()
        bindings = create_mission_action_runtime_bindings(
            normalize_string_list=lambda value: (
                [str(item) for item in value if str(item).strip()]
                if isinstance(value, list) else []
            ),
            task_priority_cls=FakePriority,
            mission_action_handlers={
                runtime_worker_id: handle_javascript_reverse_mission_node,
            },
        )
        state = bindings["build_mission_actions"](
            task_queue=queue,
            tenant_id="tenant-a",
            mission_run_id="mission-a",
            plan={
                "goal": "Analyze a JavaScript bundle",
                "mission_kind": "javascript_reverse",
                "runtime_route": {"primary_worker_id": runtime_worker_id},
                "nodes": [node],
                "orchestration": contract,
            },
            context={"source_path": "/tmp/sample/main.js"},
            work_type={},
            work_type_summary={},
        )
        return state, queue, trace

    def test_matching_worker_requires_runtime_authorization_and_receives_evidence(self):
        state, queue, trace = self._build("worker-a")

        self.assertEqual(len(queue.submissions), 1)
        payload = queue.submissions[0]["payload"]
        authorization = payload["_mission_dispatch_authorization"]
        self.assertTrue(authorization["authorized"])
        self.assertEqual(authorization["decision_owner"], "mission_runtime")
        self.assertEqual(authorization["reason_code"], "authorized")
        self.assertEqual(authorization["mission_run_id"], "mission-a")
        self.assertEqual(authorization["node_id"], "analyze-bundle")
        self.assertEqual(payload["_mission_decision_trace"], trace)

        action = state["actions"][0]
        self.assertEqual(action["action_type"], "task_submitted")
        self.assertEqual(action["task_id"], "task-1")
        self.assertEqual(action["recommended_strategies"][0]["id"], "js-bundle-inspection")
        self.assertTrue(action["mission_runtime_authorization"]["authorized"])
        self.assertFalse(action["mission_coordination_dispatch_authorized"])
        self.assertFalse(action["workforce_dispatch_authorized"])
        self.assertEqual(state["submitted_task_ids"], ["task-1"])

    def test_self_media_review_tasks_carry_authorization_and_decision_trace(self):
        trace = [{
            "step": "workforce_catalog_match",
            "rule_id": "mission.workforce_recommendation.v1",
            "result": "assign_existing_worker_recommended",
            "evidence": {"recommended_worker_id": "worker-a"},
        }]
        node = {
            "id": "review_and_iterate",
            "title": "Review and iterate",
            "task_type": "review",
            "status": "ready",
            "reasoning": [],
            "blockers": [],
            "recommended_skill_ids": [],
            "recommended_skills": [],
            "validation_checks": ["review feedback"],
            "decision_trace": trace,
            "parallel_safe": False,
            "workforce_decision": {
                "decision": "assign_existing_worker_recommended",
                "recommended_worker_id": "worker-a",
                "dispatch_state": "recommendation_only",
                "dispatch_authorized": False,
            },
        }
        queue = FakeTaskQueue()
        bindings = create_mission_action_runtime_bindings(
            normalize_string_list=lambda value: (
                [str(item) for item in value if str(item).strip()]
                if isinstance(value, list) else []
            ),
            task_priority_cls=FakePriority,
            mission_action_handlers={
                "worker-a": handle_self_media_operation_mission_node,
            },
        )

        state = bindings["build_mission_actions"](
            task_queue=queue,
            tenant_id="tenant-a",
            mission_run_id="mission-media",
            plan={
                "goal": "Review Toutiao performance",
                "mission_kind": "self_media_operations",
                "runtime_route": {"primary_worker_id": "worker-a"},
                "nodes": [node],
                "orchestration": build_mission_brain_contract([node]),
            },
            context={
                "channel": "toutiao",
                "analytics_types": ["fans"],
                "auto_collect_feedback": True,
            },
            work_type={"work_type_id": "media-ops"},
            work_type_summary={},
        )

        self.assertEqual(len(queue.submissions), 2)
        for submission in queue.submissions:
            payload = submission["payload"]
            self.assertEqual(payload["_mission_decision_trace"], trace)
            authorization = payload["_mission_dispatch_authorization"]
            self.assertTrue(authorization["authorized"])
            self.assertEqual(authorization["mission_run_id"], "mission-media")
            self.assertEqual(authorization["node_id"], "review_and_iterate")
        self.assertEqual(state["counts"]["submitted"], 2)
        self.assertTrue(all(
            action["mission_runtime_authorization"]["authorized"]
            for action in state["actions"]
        ))

    def test_worker_mismatch_is_denied_before_any_task_is_submitted(self):
        state, queue, _ = self._build("worker-b")

        self.assertEqual(queue.submissions, [])
        self.assertEqual(state["submitted_task_ids"], [])
        self.assertEqual(state["counts"]["submitted"], 0)
        action = state["actions"][0]
        self.assertEqual(action["action_type"], "dispatch_denied")
        self.assertEqual(action["status"], "blocked")
        authorization = action["mission_runtime_authorization"]
        self.assertFalse(authorization["authorized"])
        self.assertEqual(authorization["reason_code"], "runtime_worker_does_not_match_recommendation")
        self.assertFalse(action["mission_coordination_dispatch_authorized"])


if __name__ == "__main__":
    unittest.main()
