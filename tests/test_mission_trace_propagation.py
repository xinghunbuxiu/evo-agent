"""Regression tests for trace propagation through mission startup."""
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin import mission_runtime, knowledge_runtime  # noqa: E402
from admin.mission_action_runtime import create_mission_action_runtime_bindings  # noqa: E402
from admin.mission_execution_runtime import create_mission_execution_bindings  # noqa: E402
from admin.mission_app_runtime import create_mission_app_runtime_bindings  # noqa: E402


class MissionTracePropagationTests(unittest.TestCase):
    def _dependency_plan(self):
        workforce = {
            "decision": "assign_existing_worker_recommended",
            "recommended_worker_id": "worker-a",
            "dispatch_state": "recommendation_only",
            "dispatch_authorized": False,
        }
        nodes = [
            {
                "id": "node-a", "title": "Prerequisite", "task_type": "analyze", "status": "ready",
                "decision_trace": [], "blockers": [], "recommended_skill_ids": [],
                "validation_checks": ["verify prerequisite"], "parallel_safe": False, "depends_on": [],
            },
            {
                "id": "node-b", "title": "Dependent", "task_type": "analyze", "status": "ready",
                "decision_trace": [], "blockers": [], "recommended_skill_ids": [],
                "validation_checks": ["verify dependent"], "parallel_safe": False, "depends_on": ["node-a"],
            },
        ]
        decisions = [{
            "node_id": node["id"], "status": "ready", "decision": "run_minimal_validating_experiment",
            "reasoning": [], "blockers": [], "verified_skill_ids": [],
            "validation_checks": node["validation_checks"], "workforce_decision": dict(workforce),
            "parallel_safe": False, "decision_trace": [],
        } for node in nodes]
        coordination_actions = [{
            "node_id": node["id"], "action": "await_dispatch_authorization",
            "reason_code": "workforce_selection_is_recommendation_only", "dispatch_authorized": False,
        } for node in nodes]
        return {
            "goal": "dependency test",
            "runtime_route": {"primary_worker_id": "worker-a"},
            "nodes": nodes,
            "orchestration": {
                "schema_version": "mission.brain.contract.v1", "decision_owner": "mission",
                "dispatch_mode": "centralized", "node_decisions": decisions,
                "coordination_plan": {
                    "schema_version": "mission.coordination.v1", "decision_owner": "mission",
                    "dispatch_authorized": False, "actions": coordination_actions,
                },
            },
        }

    def _execution_bindings(self, resume_callback):
        return create_mission_execution_bindings(
            load_learning_tasks=lambda workspace: {"tasks": {}},
            save_learning_tasks=lambda workspace, payload: None,
            collect_task_verified_skills=lambda *args, **kwargs: [],
            skill_ids_from_items=lambda *args, **kwargs: [],
            infer_framework_hint_from_delivery=lambda *args, **kwargs: "",
            create_mission_delivery_skill_candidate=lambda *args, **kwargs: {},
            safe_float=lambda value, default=0.0: float(value) if value is not None else default,
            trim_candidate_text=lambda value, limit=180: str(value or "")[:limit],
            record_growth_event=lambda *args, **kwargs: {},
            build_snapshot_signature=lambda *args, **kwargs: {},
            normalize_string_list=lambda value: [str(item) for item in value] if isinstance(value, list) else [],
            build_external_learning_plan=lambda **kwargs: {},
            execute_learning_task=lambda **kwargs: {"task_id": "learning-task", "status": "needs_learning"},
            make_learning_task_id=lambda tenant_id, sample: "learning-task",
            extract_task_snapshot=lambda *args, **kwargs: {},
            resolve_effective_growth_policy=lambda **kwargs: {},
            growth_policy_decision_label=lambda *args, **kwargs: "",
            effective_platform_promotion_status=lambda *args, **kwargs: "candidate",
            mission_post_action_handlers={}, mission_summary_handlers={},
            resume_mission_dependency_nodes=resume_callback,
        )

    def test_planner_decision_trace_is_preserved_in_mission_run_plan(self):
        trace = [{
            "step": "input_validation",
            "rule_id": "mission.required_inputs.v1",
            "result": "passed",
            "evidence": {"blocker_codes": []},
        }]
        plan = {"title": "test plan", "nodes": [{"id": "node-a", "decision_trace": trace}]}
        prepared = {
            "goal": "test goal",
            "mission_kind": "test_kind",
            "context": {},
            "work_type_validation": {"valid": True, "missing_inputs": []},
            "work_type": {"work_type_id": "test"},
            "work_type_summary": {"deliverables": ["test output"]},
            "runtime_route": {"primary_worker_id": "worker-a"},
        }

        class Planner:
            def plan(self, **kwargs):
                return dict(plan)

        def build_mission_run(**kwargs):
            return {
                "mission_run_id": "trace-run",
                "plan": kwargs["plan"],
                "context": kwargs["context"],
            }

        with mock.patch.object(mission_runtime, "load_mission_runs", return_value={"items": []}), \
             mock.patch.object(mission_runtime, "save_mission_runs"):
            start = mission_runtime.create_start_mission(
                workspace=Path("."),
                task_queue=object(),
                tenant_manager=object(),
                prepare_mission_work_type_bundle=lambda **kwargs: prepared,
                mission_planner=Planner(),
                upsert_plan_learning_tasks=lambda **kwargs: [],
                build_mission_run=build_mission_run,
                refresh_mission_runs_fn=lambda **kwargs: {"items": []},
                error_response=lambda message, status: {"error": message, "status": status},
            )
            latest, error = start({"goal": "user goal", "tenant_id": "tenant"}, refresh_runs=False)

        self.assertIsNone(error)
        self.assertEqual(latest["mission_run_id"], "trace-run")
        self.assertEqual(latest["plan"]["nodes"][0]["decision_trace"], trace)
        self.assertEqual(latest["plan"]["nodes"][0]["decision_trace"][0]["rule_id"], "mission.required_inputs.v1")

    def test_planner_decision_trace_is_propagated_to_action(self):
        trace = [{"step": "capability_match", "rule_id": "mission.capability.match.v1", "result": "matched"}]
        bindings = create_mission_action_runtime_bindings(
            normalize_string_list=lambda value: [str(item) for item in value] if isinstance(value, list) else [],
            task_priority_cls=object,
        )
        state = bindings["build_mission_actions"](
            task_queue=object(),
            tenant_id="tenant-a",
            mission_run_id="run-a",
            plan={
                "nodes": [{
                    "id": "node-a",
                    "title": "Design",
                    "task_type": "design",
                    "status": "planned",
                    "decision_trace": trace,
                    "blockers": [],
                    "recommended_skill_ids": [],
                    "validation_checks": [],
                }],
                "orchestration": {
                    "dispatch_mode": "centralized",
                    "coordination_plan": {
                        "schema_version": "mission.coordination.v1",
                        "decision_owner": "mission",
                        "dispatch_authorized": False,
                        "actions": [{
                            "node_id": "node-a",
                            "action": "await_dispatch_authorization",
                            "reason_code": "workforce_selection_is_recommendation_only",
                            "dispatch_authorized": False,
                        }],
                    },
                },
            },
            context={},
            work_type={},
            work_type_summary={},
        )
        self.assertEqual(state["actions"][0]["node_id"], "node-a")
        self.assertEqual(state["actions"][0]["decision_trace"], trace)
        self.assertEqual(state["actions"][0]["mission_coordination_action"], "await_dispatch_authorization")
        self.assertEqual(
            state["actions"][0]["mission_coordination_reason_code"],
            "workforce_selection_is_recommendation_only",
        )
        self.assertFalse(state["actions"][0]["mission_coordination_dispatch_authorized"])

    def test_planner_trace_is_attached_only_to_matching_node_action(self):
        trace_a = [{"step": "status_decision", "rule_id": "mission.status.input_gap.v1"}]
        trace_b = [{"step": "status_decision", "rule_id": "mission.status.capability_gap.v1"}]
        bindings = create_mission_action_runtime_bindings(
            normalize_string_list=lambda value: [str(item) for item in value] if isinstance(value, list) else [],
            task_priority_cls=object,
        )
        state = bindings["build_mission_actions"](
            task_queue=object(),
            tenant_id="tenant-a",
            mission_run_id="run-a",
            plan={"nodes": [
                {"id": "node-a", "title": "A", "task_type": "design", "status": "planned", "decision_trace": trace_a, "blockers": [], "recommended_skill_ids": [], "validation_checks": []},
                {"id": "node-b", "title": "B", "task_type": "design", "status": "planned", "decision_trace": trace_b, "blockers": [], "recommended_skill_ids": [], "validation_checks": []},
            ]},
            context={},
            work_type={},
            work_type_summary={},
        )
        actions = {action["node_id"]: action for action in state["actions"]}
        self.assertEqual(actions["node-a"]["decision_trace"], trace_a)
        self.assertEqual(actions["node-b"]["decision_trace"], trace_b)

    def test_dependency_gate_blocks_until_prerequisite_completes_then_resumes_only_released_node(self):
        submitted_nodes = []

        def submit_handler(**kwargs):
            node = kwargs["node"]
            node_id = node["id"]
            submitted_nodes.append(node_id)
            task_id = f"task-{node_id}"
            kwargs["actions"].append({
                "node_id": node_id, "title": node.get("title"), "action_type": "task_submitted",
                "status": "submitted", "task_id": task_id, "task_type": node["task_type"],
                "detail": "test task submitted",
            })
            kwargs["submitted_task_ids"].append(task_id)
            kwargs["counts"]["submitted"] += 1
            return True

        bindings = create_mission_action_runtime_bindings(
            normalize_string_list=lambda value: [str(item) for item in value] if isinstance(value, list) else [],
            task_priority_cls=object, mission_action_handlers={"worker-a": submit_handler},
        )
        plan = self._dependency_plan()
        initial = bindings["build_mission_actions"](
            task_queue=object(), tenant_id="tenant-a", mission_run_id="run-a", plan=plan,
            context={"runtime_primary_worker_id": "worker-a"}, work_type={}, work_type_summary={},
        )
        blocked = next(item for item in initial["actions"] if item["node_id"] == "node-b")
        self.assertEqual(submitted_nodes, ["node-a"])
        self.assertEqual(blocked["action_type"], "dependency_blocked")
        self.assertEqual(blocked["dependency_state"], "waiting")
        self.assertFalse(blocked["mission_runtime_authorization"]["authorized"])
        self.assertEqual(blocked["mission_runtime_authorization"]["reason_code"], "dependency_not_completed")

        resumed = bindings["resume_dependency_nodes"](
            task_queue=object(),
            mission_run={
                "mission_run_id": "run-a", "tenant_id": "tenant-a", "plan": plan,
                "context": {"runtime_primary_worker_id": "worker-a"},
                "runtime_route": {"primary_worker_id": "worker-a"},
                "work_type": {}, "work_type_summary": {},
            },
            node_ids=["node-b"], completed_node_ids=["node-a"],
        )
        self.assertEqual(submitted_nodes, ["node-a", "node-b"])
        self.assertEqual(len(resumed["actions"]), 1)
        self.assertEqual(resumed["actions"][0]["node_id"], "node-b")
        self.assertEqual(resumed["actions"][0]["action_type"], "task_submitted")

    def test_refresh_returns_completed_prerequisite_result_and_resumes_dependent_node(self):
        completed_task = SimpleNamespace(
            id="task-node-a", type="analyze", status=SimpleNamespace(value="completed"),
            result={"summary": "prerequisite passed"}, error=None, payload={},
        )
        task_queue = SimpleNamespace(get_task=lambda task_id: completed_task if task_id == completed_task.id else None)
        resume = mock.Mock(return_value={
            "actions": [{"node_id": "node-b", "action_type": "task_submitted", "status": "submitted", "task_id": "task-node-b", "task_type": "execute"}],
            "submitted_task_ids": ["task-node-b"],
            "counts": {"submitted": 1, "needs_learning": 0, "needs_input": 0, "planned_only": 0},
        })
        bindings = self._execution_bindings(resume)
        mission_run = {
            "mission_run_id": "run-a", "tenant_id": "tenant-a", "goal": "dependency test",
            "context": {}, "runtime_route": {}, "work_type": {}, "work_type_summary": {},
            "submitted_task_ids": ["task-node-a"],
            "plan": {"nodes": [
                {"id": "node-a", "depends_on": [], "role_reflection_context": {}},
                {"id": "node-b", "depends_on": ["node-a"], "role_reflection_context": {}},
            ]},
            "actions": [
                {"node_id": "node-a", "action_type": "task_submitted", "status": "submitted", "task_id": "task-node-a", "task_type": "analyze", "decision_trace": []},
                {"node_id": "node-b", "action_type": "dependency_blocked", "status": "blocked", "depends_on": ["node-a"], "dependency_state": "waiting", "decision_trace": []},
            ],
        }
        refreshed = bindings["refresh_mission_run"](
            workspace=Path("."), task_queue=task_queue,
            tenant_manager=SimpleNamespace(get_knowledge_policy=lambda tenant_id: {}),
            mission_run=mission_run,
            build_mission_next_cycle_plan=lambda run, actions: {"status": "pending", "next_steps": [], "focus_points": []},
            build_mission_growth_timeline=lambda actions: [],
        )

        resume.assert_called_once()
        self.assertEqual(resume.call_args.kwargs["node_ids"], ["node-b"])
        self.assertEqual(resume.call_args.kwargs["completed_node_ids"], ["node-a"])
        node_a = next(item for item in refreshed["actions"] if item.get("node_id") == "node-a" and item.get("action_type") == "task_submitted")
        self.assertEqual(node_a["status"], "completed")
        self.assertEqual(node_a["task_result"]["summary"], "prerequisite passed")
        old_block = next(item for item in refreshed["actions"] if item.get("node_id") == "node-b" and item.get("action_type") == "dependency_blocked")
        self.assertEqual(old_block["status"], "superseded")
        self.assertIn("task-node-b", refreshed["submitted_task_ids"])
        self.assertEqual(refreshed["dependency_runtime"]["schema_version"], "mission.dependency.runtime.v1")

    def test_failed_prerequisite_blocks_dependents_and_marks_mission_replan_required(self):
        failed_task = SimpleNamespace(
            id="task-node-a", type="analyze", status=SimpleNamespace(value="failed"),
            result={}, error="executor failed", payload={},
        )
        task_queue = SimpleNamespace(get_task=lambda task_id: failed_task if task_id == failed_task.id else None)
        resume = mock.Mock()
        bindings = self._execution_bindings(resume)
        mission_run = {
            "mission_run_id": "run-failed", "tenant_id": "tenant-a", "goal": "dependency failure test",
            "context": {}, "runtime_route": {}, "work_type": {}, "work_type_summary": {},
            "submitted_task_ids": ["task-node-a"],
            "plan": {"nodes": [
                {"id": "node-a", "depends_on": [], "role_reflection_context": {}},
                {"id": "node-b", "depends_on": ["node-a"], "role_reflection_context": {}},
            ]},
            "actions": [
                {"node_id": "node-a", "action_type": "task_submitted", "status": "submitted", "task_id": "task-node-a", "task_type": "analyze", "decision_trace": []},
                {"node_id": "node-b", "action_type": "dependency_blocked", "status": "blocked", "depends_on": ["node-a"], "dependency_state": "waiting", "decision_trace": []},
            ],
        }
        refreshed = bindings["refresh_mission_run"](
            workspace=Path("."), task_queue=task_queue,
            tenant_manager=SimpleNamespace(get_knowledge_policy=lambda tenant_id: {}),
            mission_run=mission_run,
            build_mission_next_cycle_plan=lambda run, actions: {"status": "pending", "next_steps": [], "focus_points": []},
            build_mission_growth_timeline=lambda actions: [],
        )

        resume.assert_not_called()
        dependent = next(item for item in refreshed["actions"] if item.get("node_id") == "node-b" and item.get("action_type") == "dependency_blocked")
        self.assertEqual(dependent["dependency_state"], "failed")
        self.assertTrue(dependent["replan_required"])
        self.assertEqual(dependent["replan_reason_code"], "dependency_failed")
        self.assertEqual(refreshed["summary"]["next_cycle_plan"]["status"], "ready")
        self.assertTrue(refreshed["summary"]["next_cycle_plan"]["dependency_replan"]["required"])
        self.assertFalse(refreshed["summary"]["next_cycle_plan"]["dependency_replan"]["automatic_dispatch"])

    def test_follow_up_context_preserves_run_lineage_without_mutating_source(self):
        source_context = {
            "autonomy_cycle": 1,
            "nested": {"keep": True},
            "runtime_primary_worker_id": "worker-a",
        }
        source = {
            "mission_run_id": "run-previous",
            "root_mission_run_id": "run-root",
            "autonomy_session_id": "session-1",
            "context": source_context,
            "runtime_route": {"primary_worker_id": "worker-a"},
            "summary": {"next_cycle_plan": {
                "next_steps": ["inspect failed step", "retry with evidence"],
                "focus_points": ["dispatch trace"],
            }},
        }

        context = mission_runtime.derive_follow_up_context(source)

        self.assertEqual(context["previous_mission_run_id"], "run-previous")
        self.assertEqual(context["root_mission_run_id"], "run-root")
        self.assertEqual(context["autonomy_session_id"], "session-1")
        self.assertEqual(context["autonomy_cycle"], 2)
        self.assertEqual(context["deliverable_goal"], "inspect failed step；retry with evidence")
        self.assertEqual(context["goal_hint"], "dispatch trace")
        self.assertNotIn("previous_mission_run_id", source_context)
        context["nested"]["keep"] = False
        self.assertTrue(source_context["nested"]["keep"])

    def test_auto_continue_is_blocked_after_a_source_run_has_triggered_follow_up(self):
        base = {
            "status": "completed",
            "context": {"auto_continue": True, "autonomy_cycle": 1, "max_autonomy_cycles": 3},
            "summary": {"next_cycle_plan": {"status": "ready"}},
        }
        self.assertTrue(mission_runtime.should_auto_continue_mission(base))
        self.assertFalse(mission_runtime.should_auto_continue_mission({
            **base, "auto_continue_source_mission_run_id": "run-source"
        }))
        self.assertFalse(mission_runtime.should_auto_continue_mission({
            **base, "auto_continue_triggered_run_id": "run-next"
        }))

    def test_refresh_records_source_and_target_ids_for_auto_continue(self):
        current = {
            "mission_run_id": "run-source",
            "tenant_id": "tenant-a",
            "status": "completed",
            "context": {
                "auto_continue": True,
                "autonomy_cycle": 1,
                "max_autonomy_cycles": 3,
                "runtime_primary_worker_id": "worker-a",
            },
            "runtime_route": {"primary_worker_id": "worker-a"},
            "summary": {"next_cycle_plan": {
                "status": "ready",
                "next_steps": ["verify failed output"],
                "focus_points": ["retry safely"],
            }},
        }
        spawned = {"mission_run_id": "run-next", "context": {"previous_mission_run_id": "run-source"}}
        captured = {}

        def starter(payload, *, refresh_runs):
            captured["payload"] = payload
            captured["refresh_runs"] = refresh_runs
            return spawned, None

        persisted = {"items": [current]}
        def load_state(workspace):
            return persisted
        def save_state(workspace, payload):
            persisted.update(payload)

        with (
            mock.patch.object(mission_runtime, "load_mission_runs", side_effect=load_state),
            mock.patch.object(mission_runtime, "save_mission_runs", side_effect=save_state) as save,
        ):
            state = mission_runtime.refresh_mission_runs(
                workspace=Path("."),
                task_queue=object(),
                tenant_manager=object(),
                refresh_runtime_learning_tasks=lambda **kwargs: None,
                refresh_mission_run=lambda **kwargs: kwargs["mission_run"],
                mission_starter=starter,
            )

        self.assertEqual(captured["refresh_runs"], False)
        self.assertEqual(captured["payload"]["context"]["previous_mission_run_id"], "run-source")
        self.assertEqual(state["items"][0]["mission_run_id"], "run-next")
        self.assertEqual(state["items"][0]["auto_continue_source_mission_run_id"], "run-source")
        source_after = next(item for item in state["items"] if item["mission_run_id"] == "run-source")
        self.assertEqual(source_after["auto_continue_triggered_run_id"], "run-next")
        self.assertEqual(source_after["auto_continue_status"], "triggered")
        save.assert_called_once()

    def test_refresh_records_auto_continue_start_failure(self):
        current = {
            "mission_run_id": "run-source",
            "status": "completed",
            "context": {"auto_continue": True, "autonomy_cycle": 1, "max_autonomy_cycles": 3},
            "summary": {"next_cycle_plan": {"status": "ready"}},
        }
        persisted = {"items": [current]}
        def load_state(workspace):
            return persisted
        def save_state(workspace, payload):
            persisted.update(payload)

        with (
            mock.patch.object(mission_runtime, "load_mission_runs", side_effect=load_state),
            mock.patch.object(mission_runtime, "save_mission_runs", side_effect=save_state),
        ):
            state = mission_runtime.refresh_mission_runs(
                workspace=Path("."),
                task_queue=object(),
                tenant_manager=object(),
                refresh_runtime_learning_tasks=lambda **kwargs: None,
                refresh_mission_run=lambda **kwargs: kwargs["mission_run"],
                mission_starter=lambda payload, refresh_runs: (None, {"error": "boom"}),
            )

        source = state["items"][0]
        self.assertEqual(source["auto_continue_status"], "failed")
        self.assertEqual(source["auto_continue_error"], "自动续跑启动失败")
        self.assertEqual(source["auto_continue_error_detail"], "boom")

    def test_repeated_refresh_does_not_spawn_duplicate_follow_up(self):
        source = {
            "mission_run_id": "run-source",
            "tenant_id": "tenant-a",
            "status": "completed",
            "context": {"auto_continue": True, "autonomy_cycle": 1, "max_autonomy_cycles": 3},
            "summary": {"next_cycle_plan": {"status": "ready", "next_steps": ["continue"]}},
        }
        persisted = {"items": [source]}
        calls = []

        def load_state(workspace):
            return {"items": list(persisted["items"])}

        def save_state(workspace, payload):
            persisted["items"] = payload["items"]

        def starter(payload, *, refresh_runs):
            calls.append(payload)
            return {
                "mission_run_id": "run-next",
                "context": payload["context"],
                "status": "planning_only",
            }, None

        def refresh(**kwargs):
            return kwargs["mission_run"]

        with (
            mock.patch.object(mission_runtime, "load_mission_runs", side_effect=load_state),
            mock.patch.object(mission_runtime, "save_mission_runs", side_effect=save_state),
        ):
            first = mission_runtime.refresh_mission_runs(
                workspace=Path("."),
                task_queue=object(),
                tenant_manager=object(),
                refresh_runtime_learning_tasks=lambda **kwargs: None,
                refresh_mission_run=refresh,
                mission_starter=starter,
            )
            second = mission_runtime.refresh_mission_runs(
                workspace=Path("."),
                task_queue=object(),
                tenant_manager=object(),
                refresh_runtime_learning_tasks=lambda **kwargs: None,
                refresh_mission_run=refresh,
                mission_starter=starter,
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(first["items"][0]["mission_run_id"], "run-next")
        source_after = next(item for item in second["items"] if item["mission_run_id"] == "run-source")
        self.assertEqual(source_after["auto_continue_triggered_run_id"], "run-next")
        self.assertEqual(source_after["auto_continue_status"], "triggered")

    def test_growth_timeline_keeps_node_decision_trace_and_experience_link(self):
        trace = [{
            "step": "capability_match",
            "rule_id": "mission.capability.match.v1",
            "result": "matched",
        }]
        bindings = create_mission_app_runtime_bindings(
            extract_feedback_entries_from_result=lambda result: [],
            trim_candidate_text=lambda value, limit: value[:limit],
            normalize_string_list=lambda value: value if isinstance(value, list) else [],
        )
        timeline = bindings["build_mission_growth_timeline"]([{
            "node_id": "promote_knowledge",
            "task_type": "mission_delivery",
            "status": "completed",
            "decision_trace": trace,
            "growth_update": {
                "recorded_at": "2026-10-11T10:00:00",
                "experience_id": "experience-42",
            },
            "task_result": {"insight_summary": "verified delivery"},
        }])
        self.assertEqual(len(timeline), 1)
        self.assertEqual(timeline[0]["node_id"], "promote_knowledge")
        self.assertEqual(timeline[0]["decision_trace"], trace)
        self.assertEqual(timeline[0]["experience_id"], "experience-42")


    def test_mission_delivery_skill_and_growth_event_share_exact_validation_lineage(self):
        import json

        trace = [{
            "step": "validation",
            "rule_id": "mission.delivery.quality_gate.v1",
            "result": "passed",
            "evidence": {"evaluation_score": 0.94},
        }]
        growth_events = []
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(knowledge_runtime, "maybe_auto_verify_skill_candidate", return_value=None):
            result = knowledge_runtime.create_mission_delivery_skill_candidate(
                workspace=Path(tmp),
                tenant_id="tenant-a",
                mission_run={
                    "mission_run_id": "run-42",
                    "mission_kind": "javascript_reverse",
                    "plan": {"nodes": [{"id": "promote_knowledge", "decision_trace": trace}]},
                },
                analyze_snapshot={"task_id": "analyze-17", "summary": "Vue application"},
                reconstruct_snapshot={
                    "task_id": "reconstruct-29",
                    "summary": "Vue reconstructed project",
                    "evaluation_verdict": "pass",
                    "evaluation_score": 0.94,
                    "evaluation_metrics": {"components": 8, "has_target_dir": True},
                    "strategy_id": "strategy-5",
                },
                safe_float=lambda value, default: float(value) if value is not None else default,
                build_snapshot_signature=lambda snapshot: {"signature": "snapshot-29"},
                record_growth_event=lambda *args, **kwargs: growth_events.append(kwargs),
            )
            self.assertEqual(result["skill_id"], "skill_javascript_reverse_vue_delivery")
            skill = json.loads(Path(result["visible_path"]).read_text(encoding="utf-8"))

        self.assertEqual(result["skill_id"], "skill_javascript_reverse_vue_delivery")
        expected_evidence = {
            "verdict": "pass",
            "evaluation_score": 0.94,
            "analyze_task_id": "analyze-17",
            "reconstruct_task_id": "reconstruct-29",
        }
        self.assertEqual(skill["parameters"]["mission_run_id"], "run-42")
        self.assertEqual(skill["parameters"]["mission_node_id"], "promote_knowledge")
        self.assertEqual(skill["parameters"]["decision_trace"], trace)
        self.assertEqual(skill["parameters"]["validation_evidence"], expected_evidence)
        self.assertEqual(len(growth_events), 1)
        metadata = growth_events[0]["metadata"]
        self.assertEqual(metadata["mission_run_id"], skill["parameters"]["mission_run_id"])
        self.assertEqual(metadata["mission_node_id"], skill["parameters"]["mission_node_id"])
        self.assertEqual(metadata["decision_trace"], skill["parameters"]["decision_trace"])
        self.assertEqual(metadata["validation_evidence"], expected_evidence)


    def test_runtime_authorizes_matching_ready_worker_and_binds_evidence_to_real_task(self):
        from types import SimpleNamespace
        from workers.javascript_reverse.runtime import handle_javascript_reverse_mission_node

        class Queue:
            def __init__(self):
                self.submissions = []

            def submit(self, **kwargs):
                self.submissions.append(kwargs)
                return SimpleNamespace(id=f"task-{len(self.submissions)}")

        class Priority:
            HIGH = 1
            NORMAL = 2

        trace = [{"step": "status_decision", "rule_id": "mission.status.ready.v1", "result": "ready"}]
        workforce = {
            "decision": "assign_existing_worker_recommended",
            "recommended_worker_id": "worker-a",
            "dispatch_state": "recommendation_only",
            "dispatch_authorized": False,
        }
        plan = {
            "goal": "analyze local JavaScript bundle",
            "mission_kind": "javascript_reverse",
            "runtime_route": {"primary_worker_id": "worker-a"},
            "nodes": [{
                "id": "analyze_bundle",
                "title": "Analyze bundle",
                "task_type": "analyze",
                "status": "ready",
                "blockers": [],
                "decision_trace": trace,
                "recommended_skill_ids": [],
                "recommended_skills": [],
                "validation_checks": ["verify-output"],
                "role_reflection_context": {},
            }],
            "orchestration": {
                "dispatch_mode": "centralized",
                "node_decisions": [{
                    "node_id": "analyze_bundle",
                    "decision": "run_minimal_validating_experiment",
                    "decision_trace": trace,
                    "validation_checks": ["verify-output"],
                    "verified_skill_ids": [],
                    "workforce_decision": workforce,
                }],
                "coordination_plan": {
                    "schema_version": "mission.coordination.v1",
                    "decision_owner": "mission",
                    "dispatch_authorized": False,
                    "actions": [{
                        "node_id": "analyze_bundle",
                        "action": "await_dispatch_authorization",
                        "reason_code": "workforce_selection_is_recommendation_only",
                        "dispatch_authorized": False,
                    }],
                },
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir) / "main.js"
            bundle.write_text("window.app = {};\n", encoding="utf-8")
            queue = Queue()
            bindings = create_mission_action_runtime_bindings(
                normalize_string_list=lambda value: [str(item) for item in value] if isinstance(value, list) else [],
                task_priority_cls=Priority,
                mission_action_handlers={"worker-a": handle_javascript_reverse_mission_node},
            )
            state = bindings["build_mission_actions"](
                task_queue=queue,
                tenant_id="tenant-a",
                mission_run_id="run-a",
                plan=plan,
                context={"source_path": str(bundle)},
                work_type={"work_type_id": "javascript_reverse"},
                work_type_summary={},
            )

        self.assertEqual(len(queue.submissions), 1)
        payload = queue.submissions[0]["payload"]
        authorization = payload["_mission_dispatch_authorization"]
        self.assertTrue(authorization["authorized"])
        self.assertEqual(authorization["decision_owner"], "mission_runtime")
        self.assertEqual(authorization["policy_rule_id"], "mission.dispatch.ready_route_gate.v1")
        self.assertEqual(authorization["evidence"]["recommended_worker_id"], "worker-a")
        self.assertEqual(state["submitted_task_ids"], ["task-1"])
        action = state["actions"][0]
        self.assertEqual(action["status"], "submitted")
        self.assertEqual(action["task_id"], "task-1")
        self.assertTrue(action["mission_runtime_authorization"]["authorized"])
        self.assertFalse(action["workforce_dispatch_authorized"])

    def test_verified_skill_reuse_can_pass_runtime_authorization(self):
        from types import SimpleNamespace
        from workers.javascript_reverse.runtime import handle_javascript_reverse_mission_node

        class Queue:
            def __init__(self):
                self.submissions = []

            def submit(self, **kwargs):
                self.submissions.append(kwargs)
                return SimpleNamespace(id=f"task-{len(self.submissions)}")

        class Priority:
            HIGH = 1
            NORMAL = 2

        trace = [{"step": "knowledge_check", "rule_id": "mission.knowledge_signals.v1", "result": "available"}]
        workforce = {
            "decision": "assign_existing_worker_recommended",
            "recommended_worker_id": "worker-a",
            "dispatch_state": "recommendation_only",
            "dispatch_authorized": False,
        }
        plan = {
            "goal": "reuse verified JavaScript analysis skill",
            "mission_kind": "javascript_reverse",
            "runtime_route": {"primary_worker_id": "worker-a"},
            "nodes": [{
                "id": "analyze_bundle",
                "title": "Analyze bundle",
                "task_type": "analyze",
                "status": "reuse_existing",
                "blockers": [],
                "decision_trace": trace,
                "recommended_skill_ids": ["skill-verified"],
                "recommended_skills": [{"skill_id": "skill-verified", "status": "local_verified"}],
                "validation_checks": ["verify-output"],
                "role_reflection_context": {},
            }],
            "orchestration": {
                "dispatch_mode": "centralized",
                "node_decisions": [{
                    "node_id": "analyze_bundle",
                    "decision": "reuse_verified_knowledge_first",
                    "decision_trace": trace,
                    "validation_checks": ["verify-output"],
                    "verified_skill_ids": ["skill-verified"],
                    "workforce_decision": workforce,
                }],
                "coordination_plan": {
                    "schema_version": "mission.coordination.v1",
                    "decision_owner": "mission",
                    "dispatch_authorized": False,
                    "actions": [{
                        "node_id": "analyze_bundle",
                        "action": "reuse_verified_knowledge_then_validate",
                        "reason_code": "verified_reuse_precedes_new_research",
                        "dispatch_authorized": False,
                    }],
                },
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir) / "main.js"
            bundle.write_text("window.app = {};\n", encoding="utf-8")
            queue = Queue()
            bindings = create_mission_action_runtime_bindings(
                normalize_string_list=lambda value: [str(item) for item in value] if isinstance(value, list) else [],
                task_priority_cls=Priority,
                mission_action_handlers={"worker-a": handle_javascript_reverse_mission_node},
            )
            state = bindings["build_mission_actions"](
                task_queue=queue,
                tenant_id="tenant-a",
                mission_run_id="run-reuse",
                plan=plan,
                context={"source_path": str(bundle)},
                work_type={"work_type_id": "javascript_reverse"},
                work_type_summary={},
            )

        self.assertEqual(len(queue.submissions), 1)
        self.assertEqual(queue.submissions[0]["payload"]["_mission_decision_trace"], trace)
        authorization = queue.submissions[0]["payload"]["_mission_dispatch_authorization"]
        self.assertTrue(authorization["authorized"])
        self.assertEqual(authorization["reason_code"], "authorized")
        self.assertEqual(state["actions"][0]["status"], "submitted")
        self.assertEqual(state["actions"][0]["verified_skill_ids"], ["skill-verified"])

    def test_missing_input_is_blocked_before_worker_handler_can_submit(self):
        from workers.javascript_reverse.runtime import handle_javascript_reverse_mission_node

        class Queue:
            def __init__(self):
                self.submissions = []

            def submit(self, **kwargs):
                self.submissions.append(kwargs)
                raise AssertionError("blocked Mission node must not reach task_queue.submit")

        class Priority:
            HIGH = 1
            NORMAL = 2

        trace = [{"step": "input_validation", "rule_id": "mission.required_inputs.v1", "result": "blocked"}]
        plan = {
            "runtime_route": {"primary_worker_id": "worker-a"},
            "nodes": [{
                "id": "analyze_bundle",
                "title": "Analyze bundle",
                "task_type": "analyze",
                "status": "needs_input",
                "blockers": ["source_path_or_source_dir"],
                "decision_trace": trace,
                "recommended_skill_ids": [],
                "recommended_skills": [],
                "validation_checks": [],
            }],
            "orchestration": {
                "dispatch_mode": "centralized",
                "node_decisions": [{
                    "node_id": "analyze_bundle",
                    "decision": "request_missing_input",
                    "decision_trace": trace,
                    "validation_checks": [],
                    "verified_skill_ids": [],
                }],
                "coordination_plan": {
                    "schema_version": "mission.coordination.v1",
                    "decision_owner": "mission",
                    "dispatch_authorized": False,
                    "actions": [{
                        "node_id": "analyze_bundle",
                        "action": "request_missing_input",
                        "reason_code": "required_inputs_missing",
                        "dispatch_authorized": False,
                    }],
                },
            },
        }
        queue = Queue()
        bindings = create_mission_action_runtime_bindings(
            normalize_string_list=lambda value: [str(item) for item in value] if isinstance(value, list) else [],
            task_priority_cls=Priority,
            mission_action_handlers={"worker-a": handle_javascript_reverse_mission_node},
        )
        state = bindings["build_mission_actions"](
            task_queue=queue,
            tenant_id="tenant-a",
            mission_run_id="run-blocked",
            plan=plan,
            context={},
            work_type={"work_type_id": "javascript_reverse"},
            work_type_summary={},
        )

        self.assertEqual(queue.submissions, [])
        self.assertEqual(state["counts"]["needs_input"], 1)
        self.assertEqual(state["status"], "blocked")
        action = state["actions"][0]
        self.assertEqual(action["action_type"], "needs_input")
        self.assertFalse(action["mission_runtime_authorization"]["authorized"])
        self.assertEqual(action["mission_runtime_authorization"]["reason_code"], "coordination_action_not_dispatchable")


    def test_runtime_rejects_workforce_route_mismatch_without_calling_worker(self):
        calls = []

        def worker_handler(**kwargs):
            calls.append(kwargs)
            return True

        trace = [{"step": "status_decision", "rule_id": "mission.status.ready.v1", "result": "ready"}]
        plan = {
            "runtime_route": {"primary_worker_id": "worker-a"},
            "nodes": [{
                "id": "execute",
                "title": "Execute",
                "task_type": "analyze",
                "status": "ready",
                "blockers": [],
                "recommended_skill_ids": [],
                "recommended_skills": [],
                "validation_checks": ["verify-output"],
                "decision_trace": trace,
            }],
            "orchestration": {
                "dispatch_mode": "centralized",
                "node_decisions": [{
                    "node_id": "execute",
                    "decision": "run_minimal_validating_experiment",
                    "decision_trace": trace,
                    "validation_checks": ["verify-output"],
                    "verified_skill_ids": [],
                    "workforce_decision": {
                        "decision": "assign_existing_worker_recommended",
                        "recommended_worker_id": "worker-b",
                        "dispatch_state": "recommendation_only",
                        "dispatch_authorized": False,
                    },
                }],
                "coordination_plan": {
                    "schema_version": "mission.coordination.v1",
                    "decision_owner": "mission",
                    "dispatch_authorized": False,
                    "actions": [{
                        "node_id": "execute",
                        "action": "await_dispatch_authorization",
                        "reason_code": "workforce_selection_is_recommendation_only",
                        "dispatch_authorized": False,
                    }],
                },
            },
        }
        bindings = create_mission_action_runtime_bindings(
            normalize_string_list=lambda value: value if isinstance(value, list) else [],
            task_priority_cls=object,
            mission_action_handlers={"worker-a": worker_handler},
        )

        state = bindings["build_mission_actions"](
            task_queue=object(),
            tenant_id="tenant-a",
            mission_run_id="run-mismatch",
            plan=plan,
            context={},
            work_type={},
            work_type_summary={},
        )

        self.assertEqual(calls, [])
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(state["actions"][0]["action_type"], "dispatch_denied")
        authorization = state["actions"][0]["mission_runtime_authorization"]
        self.assertFalse(authorization["authorized"])
        self.assertEqual(authorization["reason_code"], "runtime_worker_does_not_match_recommendation")
        self.assertEqual(authorization["evidence"]["recommended_worker_id"], "worker-b")


if __name__ == "__main__":
    unittest.main()
