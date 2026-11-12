"""Mission delivery Skill candidates require an accepted artifact."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin import knowledge_runtime
from workers.javascript_reverse.runtime import complete_javascript_reverse_promotion_action


class MissionDeliverySkillCandidateGateTests(unittest.TestCase):
    def test_candidate_writer_rejects_failed_or_missing_delivery_acceptance(self):
        mission_run = {
            "mission_run_id": "mission-a",
            "plan": {"nodes": [{"id": "promote_knowledge", "decision_trace": []}]},
        }
        growth_event = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(knowledge_runtime, "write_skill_candidate") as write_candidate:
                for verdict, has_target_dir in (("failed", True), ("pass", False), ("unknown", True)):
                    with self.subTest(verdict=verdict, has_target_dir=has_target_dir):
                        with self.assertRaisesRegex(ValueError, "acceptance must pass"):
                            knowledge_runtime.create_mission_delivery_skill_candidate(
                                workspace=Path(tmp),
                                tenant_id="tenant-a",
                                mission_run=mission_run,
                                analyze_snapshot={"task_id": "analyze-a"},
                                reconstruct_snapshot={
                                    "task_id": "reconstruct-a",
                                    "evaluation_verdict": verdict,
                                    "evaluation_score": 0.2,
                                    "evaluation_metrics": {
                                        "components": 1,
                                        "has_target_dir": has_target_dir,
                                    },
                                },
                                safe_float=lambda value, default=0.0: float(value) if value is not None else default,
                                build_snapshot_signature=lambda snapshot: {},
                                record_growth_event=growth_event,
                            )
                write_candidate.assert_not_called()
        growth_event.assert_not_called()

    def test_promotion_action_does_not_save_experience_or_candidate_without_acceptance(self):
        analyze_task = object()
        reconstruct_task = object()
        candidate = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("workers.javascript_reverse.runtime.ExperienceStore.save") as save_experience:
                action = complete_javascript_reverse_promotion_action(
                    workspace=Path(tmp),
                    tenant_id="tenant-a",
                    mission_run={
                        "mission_run_id": "mission-a",
                        "goal": "restore project",
                        "context": {},
                        "work_type_summary": {},
                        "plan": {"nodes": []},
                    },
                    action={"node_id": "promote_knowledge", "decision_trace": []},
                    analyze_task=analyze_task,
                    reconstruct_task=reconstruct_task,
                    inherited_skills=[],
                    skill_ids_from_items=lambda items: [],
                    extract_task_snapshot=lambda task: (
                        {"task_id": "analyze-a", "summary": "Vue project"}
                        if task is analyze_task
                        else {
                            "task_id": "reconstruct-a",
                            "summary": "incomplete output",
                            "evaluation_verdict": "failed",
                            "evaluation_score": 0.2,
                            "evaluation_metrics": {"components": 1, "has_target_dir": False},
                        }
                    ),
                    resolve_effective_growth_policy=lambda **kwargs: {},
                    infer_framework_hint_from_delivery=lambda payload: "vue",
                    safe_float=lambda value, default=0.0: float(value) if value is not None else default,
                    create_mission_delivery_skill_candidate=candidate,
                    build_snapshot_signature=lambda snapshot: {},
                    record_growth_event=lambda *args, **kwargs: None,
                    growth_policy_decision_label=lambda policy: "candidate",
                    effective_platform_promotion_status=lambda policy: "candidate",
                )
                self.assertEqual(action["status"], "blocked")
                self.assertEqual(action["promotion"]["reason"], "delivery_acceptance_not_passed")
                save_experience.assert_not_called()
                candidate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
