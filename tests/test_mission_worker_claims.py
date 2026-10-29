"""Integration tests for Mission's atomic worker reservation and release lifecycle."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.organization_runtime import OrganizationRegistry
from admin.mission_action_runtime import create_mission_action_runtime_bindings
from admin.mission_execution_runtime import create_mission_execution_bindings
from admin.mission_runtime import load_mission_runs, save_mission_runs


def _plan(node_specs):
    nodes = []
    decisions = []
    coordination = []
    for spec in node_specs:
        node = {
            "id": spec["id"],
            "title": spec.get("title", spec["id"]),
            "task_type": "analyze",
            "capability_type": "android",
            "required_capabilities": ["android"],
            "parallel_safe": bool(spec.get("parallel_safe", False)),
            "depends_on": [],
            "status": "ready",
            "decision_trace": [],
            "blockers": [],
            "recommended_skill_ids": [],
            "validation_checks": ["check output"],
            "next_actions": [],
        }
        nodes.append(node)
        workforce = dict(spec["workforce_decision"])
        decisions.append({
            "node_id": node["id"],
            "status": "ready",
            "decision": "run_minimal_validating_experiment",
            "reasoning": [],
            "blockers": [],
            "verified_skill_ids": [],
            "validation_checks": list(node["validation_checks"]),
            "workforce_decision": workforce,
            "parallel_safe": node["parallel_safe"],
            "decision_trace": [],
        })
        coordination.append({
            "node_id": node["id"],
            "action": "await_dispatch_authorization",
            "reason_code": "workforce_selection_is_recommendation_only",
            "dispatch_authorized": False,
        })
    return {
        "goal": "atomic workforce dispatch test",
        "runtime_route": {"primary_worker_id": "worker-a"},
        "nodes": nodes,
        "orchestration": {
            "schema_version": "mission.brain.contract.v1",
            "decision_owner": "mission",
            "dispatch_mode": "centralized",
            "node_decisions": decisions,
            "coordination_plan": {
                "schema_version": "mission.coordination.v1",
                "decision_owner": "mission",
                "dispatch_authorized": False,
                "actions": coordination,
            },
        },
    }


def _workforce(decision, **extra):
    return {
        "decision": decision,
        "required_capabilities": ["android"],
        "recommended_role_id": "android",
        "recommended_worker_id": "worker-a" if decision == "assign_existing_worker_recommended" else None,
        "recommended_source_worker_id": "worker-a" if decision == "clone_worker_recommended" else None,
        "dispatch_state": "recommendation_only",
        "dispatch_authorized": False,
        **extra,
    }


def _execution_bindings(registry):
    return create_mission_execution_bindings(
        load_learning_tasks=lambda workspace: {"tasks": {}},
        save_learning_tasks=lambda workspace, payload: None,
        collect_task_verified_skills=lambda *args, **kwargs: [],
        skill_ids_from_items=lambda *args, **kwargs: [],
        infer_framework_hint_from_delivery=lambda *args, **kwargs: "",
        create_mission_delivery_skill_candidate=lambda **kwargs: {},
        safe_float=lambda value, default=0.0: float(value) if value is not None else default,
        trim_candidate_text=lambda value, limit=180: str(value or "")[:limit],
        record_growth_event=lambda *args, **kwargs: {},
        build_snapshot_signature=lambda *args, **kwargs: {},
        normalize_string_list=lambda value: [str(item) for item in value] if isinstance(value, list) else [],
        build_external_learning_plan=lambda **kwargs: {},
        execute_learning_task=lambda **kwargs: {"task_id": "learning-task", "status": "needs_learning"},
        make_learning_task_id=lambda *args, **kwargs: "learning-task",
        extract_task_snapshot=lambda *args, **kwargs: {},
        resolve_effective_growth_policy=lambda **kwargs: {},
        growth_policy_decision_label=lambda *args, **kwargs: "",
        effective_platform_promotion_status=lambda *args, **kwargs: "candidate",
        mission_post_action_handlers={},
        mission_summary_handlers={},
        organization_registry=registry,
    )


class MissionWorkerClaimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = OrganizationRegistry(Path(self.temp.name))
        self.registry.create_role(
            role_id="android",
            title="Android Worker",
            responsibilities=["analyze"],
            required_capabilities=["android"],
        )
        self.registry.create_worker(
            worker_id="worker-a",
            role_id="android",
            profile={"handler_id": "worker-a", "capability_type": "android"},
        )

    def _bindings(self, handler):
        return create_mission_action_runtime_bindings(
            normalize_string_list=lambda value: [str(item) for item in value] if isinstance(value, list) else [],
            task_priority_cls=object,
            mission_action_handlers={"worker-a": handler},
            organization_registry=self.registry,
        )

    @staticmethod
    def _handler(**kwargs):
        node = kwargs["node"]
        task_id = "task-" + node["id"]
        kwargs["submitted_task_ids"].append(task_id)
        kwargs["counts"]["submitted"] += 1
        kwargs["actions"].append({
            "node_id": node["id"],
            "title": node.get("title"),
            "action_type": "task_submitted",
            "status": "submitted",
            "task_id": task_id,
            "task_type": node.get("task_type"),
            "detail": "queued",
        })
        return True

    def test_one_worker_cannot_be_claimed_by_two_nodes_in_same_mission(self):
        calls = []
        def handler(**kwargs):
            calls.append(kwargs["node"]["id"])
            return self._handler(**kwargs)

        plan = _plan([
            {"id": "node-one", "workforce_decision": _workforce("assign_existing_worker_recommended")},
            {"id": "node-two", "workforce_decision": _workforce("assign_existing_worker_recommended")},
        ])
        result = self._bindings(handler)["build_mission_actions"](
            task_queue=object(), tenant_id="tenant-a", mission_run_id="run-a",
            plan=plan, context={"runtime_primary_worker_id": "worker-a"},
            work_type={}, work_type_summary={},
        )
        self.assertEqual(calls, ["node-one"])
        worker = self.registry.get_worker("worker-a")
        self.assertEqual(worker["status"], "busy")
        self.assertEqual(len(worker["active_task_ids"]), 1)
        denied = next(item for item in result["actions"] if item["node_id"] == "node-two")
        self.assertEqual(denied["action_type"], "dispatch_denied")
        self.assertEqual(denied["mission_runtime_authorization"]["reason_code"], "recommended_worker_not_available")

    def test_handler_error_after_submission_keeps_claim_until_task_ends(self):
        def partial_handler(**kwargs):
            node = kwargs["node"]
            task_id = "task-partial"
            kwargs["submitted_task_ids"].append(task_id)
            kwargs["counts"]["submitted"] += 1
            kwargs["actions"].append({
                "node_id": node["id"],
                "title": node.get("title"),
                "action_type": "task_submitted",
                "status": "submitted",
                "task_id": task_id,
                "task_type": "analyze",
                "detail": "submitted before handler error",
            })
            raise RuntimeError("post-submit failure")

        plan = _plan([{
            "id": "partial-node",
            "workforce_decision": _workforce("assign_existing_worker_recommended"),
        }])
        result = self._bindings(partial_handler)["build_mission_actions"](
            task_queue=object(), tenant_id="tenant-a", mission_run_id="run-partial",
            plan=plan, context={"runtime_primary_worker_id": "worker-a"},
            work_type={}, work_type_summary={},
        )
        action = next(item for item in result["actions"] if item.get("task_id") == "task-partial")
        self.assertEqual(action["worker_claim"]["state"], "claimed")
        self.assertEqual(action["handler_error_type"], "RuntimeError")
        worker = self.registry.get_worker("worker-a")
        self.assertEqual(worker["status"], "busy")
        self.assertEqual(len(worker["active_task_ids"]), 1)

    def test_parallel_safe_busy_worker_is_cloned_then_clone_is_claimed(self):
        self.registry.claim_worker_task(worker_id="worker-a", task_id="existing-task")
        plan = _plan([{
            "id": "parallel-node",
            "parallel_safe": True,
            "workforce_decision": _workforce("clone_worker_recommended"),
        }])
        result = self._bindings(self._handler)["build_mission_actions"](
            task_queue=object(), tenant_id="tenant-a", mission_run_id="run-clone",
            plan=plan, context={"runtime_primary_worker_id": "worker-a"},
            work_type={}, work_type_summary={},
        )
        action = next(item for item in result["actions"] if item["node_id"] == "parallel-node" and item["action_type"] == "task_submitted")
        claim = action["worker_claim"]
        self.assertEqual(claim["origin"], "clone")
        clone = self.registry.get_worker(claim["worker_id"])
        self.assertEqual(clone["created_from_worker_id"], "worker-a")
        self.assertEqual(clone["status"], "busy")
        self.assertEqual(clone["active_task_ids"], [claim["claim_id"]])
        self.assertEqual(action["organization_worker_id"], claim["worker_id"])

    def test_failed_and_cancelled_tasks_also_release_worker_claims(self):
        refresh = _execution_bindings(self.registry)["refresh_mission_run"]
        for terminal_status in ("failed", "cancelled"):
            claim_id = "mission-" + terminal_status
            self.registry.claim_worker_task(worker_id="worker-a", task_id=claim_id)

            class Queue:
                def get_task(self, task_id):
                    if task_id != "task-terminal":
                        return None
                    return SimpleNamespace(
                        id=task_id,
                        tenant_id="tenant-a",
                        status=SimpleNamespace(value=terminal_status),
                        result={},
                        error="terminal",
                        payload={},
                        type="analyze",
                    )

            run = {
                "mission_run_id": "run-" + terminal_status,
                "tenant_id": "tenant-a",
                "goal": "terminal release",
                "context": {},
                "plan": {"nodes": [{"id": "node-a", "role_reflection_context": {}}]},
                "actions": [{
                    "node_id": "node-a",
                    "title": "terminal task",
                    "action_type": "task_submitted",
                    "status": "submitted",
                    "task_id": "task-terminal",
                    "task_type": "analyze",
                    "decision_trace": [],
                    "worker_claim": {"worker_id": "worker-a", "claim_id": claim_id, "state": "claimed"},
                }],
                "submitted_task_ids": ["task-terminal"],
            }
            result = refresh(
                workspace=Path(self.temp.name), task_queue=Queue(), tenant_manager=SimpleNamespace(get_knowledge_policy=lambda tenant_id: {}),
                mission_run=run, build_mission_next_cycle_plan=lambda *args, **kwargs: {},
                build_mission_growth_timeline=lambda *args, **kwargs: [],
            )
            self.assertEqual(self.registry.get_worker("worker-a")["status"], "available")
            self.assertEqual(result["actions"][0]["worker_claim"]["state"], "released")

    def test_worker_claim_is_released_only_after_all_attached_tasks_are_terminal(self):
        claim_id = "mission-claim-123"
        self.registry.claim_worker_task(worker_id="worker-a", task_id=claim_id)

        class Queue:
            def __init__(self):
                self.tasks = {
                    "task-one": SimpleNamespace(status=SimpleNamespace(value="success"), result={"summary": "one"}, error=None, payload={}, type="analyze"),
                    "task-two": SimpleNamespace(status=SimpleNamespace(value="running"), result={}, error=None, payload={}, type="analyze"),
                }
            def get_task(self, task_id):
                return self.tasks.get(task_id)

        queue = Queue()
        run = {
            "mission_run_id": "run-release",
            "tenant_id": "tenant-a",
            "goal": "release claim",
            "context": {},
            "plan": {"nodes": [{"id": "node-a", "role_reflection_context": {}}]},
            "actions": [
                {"node_id": "node-a", "title": "one", "action_type": "task_submitted", "status": "submitted", "task_id": "task-one", "task_type": "analyze", "decision_trace": [], "worker_claim": {"worker_id": "worker-a", "claim_id": claim_id, "state": "claimed"}},
                {"node_id": "node-a", "title": "two", "action_type": "task_submitted", "status": "submitted", "task_id": "task-two", "task_type": "analyze", "decision_trace": [], "worker_claim": {"worker_id": "worker-a", "claim_id": claim_id, "state": "claimed"}},
            ],
            "submitted_task_ids": ["task-one", "task-two"],
        }
        refresh = _execution_bindings(self.registry)["refresh_mission_run"]
        first = refresh(
            workspace=Path(self.temp.name), task_queue=queue, tenant_manager=SimpleNamespace(get_knowledge_policy=lambda tenant_id: {}),
            mission_run=run, build_mission_next_cycle_plan=lambda *args, **kwargs: {},
            build_mission_growth_timeline=lambda *args, **kwargs: [],
        )
        self.assertEqual(self.registry.get_worker("worker-a")["status"], "busy")
        self.assertTrue(all(item["worker_claim"]["state"] == "claimed" for item in first["actions"]))

        queue.tasks["task-two"].status = SimpleNamespace(value="success")
        second = refresh(
            workspace=Path(self.temp.name), task_queue=queue, tenant_manager=SimpleNamespace(get_knowledge_policy=lambda tenant_id: {}),
            mission_run=first, build_mission_next_cycle_plan=lambda *args, **kwargs: {},
            build_mission_growth_timeline=lambda *args, **kwargs: [],
        )
        self.assertEqual(self.registry.get_worker("worker-a")["status"], "available")
        self.assertEqual(self.registry.get_worker("worker-a")["active_task_ids"], [])
        self.assertTrue(all(item["worker_claim"]["state"] == "released" for item in second["actions"]))

    def test_persisted_history_never_prunes_run_with_active_worker_claim(self):
        workspace = Path(self.temp.name)
        runs = [
            {
                "mission_run_id": f"run-{index}",
                "actions": [{
                    "action_type": "task_submitted",
                    "task_id": f"task-{index}",
                    "worker_claim": {
                        "worker_id": "worker-a",
                        "claim_id": f"claim-{index}",
                        "state": "claimed" if index == 50 else "released",
                    },
                }],
            }
            for index in range(51)
        ]
        save_mission_runs(workspace, {"items": runs})
        restored = load_mission_runs(workspace)["items"]
        restored_ids = {item["mission_run_id"] for item in restored}

        # The oldest run is outside the normal 50-run history window, but is
        # still the durable source of evidence for a busy worker.
        self.assertIn("run-50", restored_ids)
        self.assertEqual(len(restored), 51)

        # Once the old claim is terminal/released, the same history bound applies.
        runs[50]["actions"][0]["worker_claim"]["state"] = "released"
        save_mission_runs(workspace, {"items": runs})
        pruned = load_mission_runs(workspace)["items"]
        self.assertEqual(len(pruned), 50)
        self.assertNotIn("run-50", {item["mission_run_id"] for item in pruned})


if __name__ == "__main__":
    unittest.main()
