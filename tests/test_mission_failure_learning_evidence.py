"""Regression coverage for failure-learning evidence lineage."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_execution_runtime import create_mission_execution_bindings  # noqa: E402


class MissionFailureLearningEvidenceTests(unittest.TestCase):
    def test_failure_learning_task_preserves_required_mission_decision_trace(self):
        trace = [
            {
                "step": "capability_match",
                "rule_id": "mission.capability.match.v1",
                "result": "matched",
                "evidence": {"capability_id": "capability-a"},
            }
        ]
        saved = {}

        bindings = create_mission_execution_bindings(
            load_learning_tasks=lambda workspace: {"tasks": {}},
            save_learning_tasks=lambda workspace, payload: saved.update(payload),
            collect_task_verified_skills=lambda *args, **kwargs: [],
            skill_ids_from_items=lambda items: [],
            infer_framework_hint_from_delivery=lambda *args, **kwargs: "",
            create_mission_delivery_skill_candidate=lambda *args, **kwargs: {},
            safe_float=lambda value, default=0.0: default,
            trim_candidate_text=lambda value, limit=280: str(value or "")[:limit],
            record_growth_event=lambda *args, **kwargs: None,
            build_snapshot_signature=lambda *args, **kwargs: {},
            normalize_string_list=lambda value: value if isinstance(value, list) else [],
            build_external_learning_plan=lambda **kwargs: {"preferred_sources": []},
            execute_learning_task=lambda **kwargs: {"task_id": "learning-1", "status": "needs_learning"},
            make_learning_task_id=lambda tenant_id, sample: "learning-generated",
            extract_task_snapshot=lambda *args, **kwargs: {},
            resolve_effective_growth_policy=lambda **kwargs: {},
            growth_policy_decision_label=lambda *args, **kwargs: "",
            effective_platform_promotion_status=lambda *args, **kwargs: "",
        )

        failed_task = SimpleNamespace(
            id="source-task-1",
            type="analyze",
            status=SimpleNamespace(value="failed"),
            payload={"path": "/tmp/sample"},
            result={},
            error="execution failed",
        )
        mission_run = {
            "mission_run_id": "mission-run-1",
            "tenant_id": "tenant-a",
            "goal": "complete the task",
            "context": {"source_path": "/tmp/sample"},
        }
        action = {"node_id": "node-a", "task_type": "analyze", "decision_trace": trace}

        with tempfile.TemporaryDirectory() as tmp:
            task_id = bindings["upsert_mission_failure_learning_task"](
                workspace=Path(tmp),
                tenant_manager=object(),
                tenant_id="tenant-a",
                mission_run=mission_run,
                action=action,
                failed_task=failed_task,
            )

        learning_task = saved["tasks"][task_id]
        self.assertEqual(learning_task["mission_run_id"], "mission-run-1")
        self.assertEqual(learning_task["source_task_id"], "source-task-1")
        self.assertEqual(learning_task["mission_node_id"], "node-a")
        self.assertEqual(learning_task["decision_trace"], trace)


    def test_missing_required_lineage_fields_fail_instead_of_saving_incomplete_task(self):
        saved = {}
        bindings = create_mission_execution_bindings(
            load_learning_tasks=lambda workspace: {"tasks": {}},
            save_learning_tasks=lambda workspace, payload: saved.update(payload),
            collect_task_verified_skills=lambda *args, **kwargs: [],
            skill_ids_from_items=lambda items: [],
            infer_framework_hint_from_delivery=lambda *args, **kwargs: "",
            create_mission_delivery_skill_candidate=lambda *args, **kwargs: {},
            safe_float=lambda value, default=0.0: default,
            trim_candidate_text=lambda value, limit=280: str(value or "")[:limit],
            record_growth_event=lambda *args, **kwargs: None,
            build_snapshot_signature=lambda *args, **kwargs: {},
            normalize_string_list=lambda value: value if isinstance(value, list) else [],
            build_external_learning_plan=lambda **kwargs: {"preferred_sources": []},
            execute_learning_task=lambda **kwargs: {"task_id": "learning-1", "status": "needs_learning"},
            make_learning_task_id=lambda tenant_id, sample: "learning-generated",
            extract_task_snapshot=lambda *args, **kwargs: {},
            resolve_effective_growth_policy=lambda **kwargs: {},
            growth_policy_decision_label=lambda *args, **kwargs: "",
            effective_platform_promotion_status=lambda *args, **kwargs: "",
        )
        failed_task = SimpleNamespace(
            id="source-task-1",
            type="analyze",
            status=SimpleNamespace(value="failed"),
            payload={"path": "/tmp/sample"},
            result={},
            error="execution failed",
        )
        base_mission_run = {
            "mission_run_id": "mission-run-1",
            "tenant_id": "tenant-a",
            "goal": "complete the task",
            "context": {"source_path": "/tmp/sample"},
        }
        base_action = {
            "node_id": "node-a",
            "task_type": "analyze",
            "decision_trace": [{"step": "capability_match", "result": "matched"}],
        }

        cases = [
            ("mission_run_id", "mission_run"),
            ("node_id", "action"),
            ("decision_trace", "action"),
        ]
        for missing_key, target in cases:
            with self.subTest(missing_key=missing_key), tempfile.TemporaryDirectory() as tmp:
                mission_run = dict(base_mission_run)
                action = dict(base_action)
                del (mission_run if target == "mission_run" else action)[missing_key]
                with self.assertRaises(KeyError):
                    bindings["upsert_mission_failure_learning_task"](
                        workspace=Path(tmp),
                        tenant_manager=object(),
                        tenant_id="tenant-a",
                        mission_run=mission_run,
                        action=action,
                        failed_task=failed_task,
                    )

        self.assertEqual(saved, {})


if __name__ == "__main__":
    unittest.main()
