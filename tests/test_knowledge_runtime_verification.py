"""Skill promotion requires explicit replay evidence, not historical success alone."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin import knowledge_runtime  # noqa: E402
from core import Skill, SkillTrustLevel  # noqa: E402


class SkillReplayVerificationTests(unittest.TestCase):
    def _skill(self):
        return Skill(
            id="candidate-skill",
            name="Candidate",
            domain="python",
            capability_type="general_dev",
            description="candidate",
            code="run and verify",
            parameters={},
            trust_level=SkillTrustLevel.DRAFT,
            source="test",
            version="1.0.0",
        )

    def test_historical_success_does_not_count_as_candidate_replay(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(knowledge_runtime, "matching_mission_delivery_experiences") as history, \
             mock.patch.object(knowledge_runtime.SkillRegistry, "verify_skill") as verify:
            history.return_value = [
                mock.Mock(id="old-task-1", quality_score=1.0),
                mock.Mock(id="old-task-2", quality_score=1.0),
            ]
            result = knowledge_runtime.maybe_auto_verify_skill_candidate(
                Path(tmp), "tenant-a", self._skill(), "python"
            )
            self.assertIsNone(result)
            history.assert_not_called()
            verify.assert_not_called()

    def test_stable_historical_experience_cluster_cannot_verify_candidate(self):
        items = [
            mock.Mock(id="history-1", quality_score=0.99),
            mock.Mock(id="history-2", quality_score=0.98),
            mock.Mock(id="history-3", quality_score=0.97),
        ]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(knowledge_runtime.SkillRegistry, "verify_skill") as verify:
            result = knowledge_runtime.maybe_auto_verify_stable_experience_skill_candidate(
                Path(tmp), "tenant-a", self._skill(), items
            )
            self.assertIsNone(result)
            verify.assert_not_called()

    def test_stable_experience_skill_keeps_each_source_experience_mission_worker_and_task_evidence(self):
        import json
        from core import Experience, ExperienceStore

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            store = ExperienceStore(workspace, "tenant-a")
            experiences = [
                Experience(
                    id="experience-1",
                    domain="javascript",
                    task_type="mission_delivery",
                    input_summary="Vue source",
                    output_summary="Restored Vue app",
                    quality_score=0.94,
                    capability_type="frontend",
                    metadata={"mission_delivery": {
                        "mission_run_id": "run-1",
                        "mission_node_id": "node-1",
                        "primary_worker_id": "worker-vue",
                        "evidence_ids": ["analyze-1", "reconstruct-1"],
                        "validation_evidence": {"verdict": "pass", "evaluation_score": 0.94},
                        "decision_trace": [{"step": "validate", "result": "passed"}],
                    }},
                ),
                Experience(
                    id="experience-2",
                    domain="javascript",
                    task_type="mission_delivery",
                    input_summary="Vue source 2",
                    output_summary="Restored Vue app 2",
                    quality_score=0.92,
                    capability_type="frontend",
                    metadata={"mission_delivery": {
                        "mission_run_id": "run-2",
                        "mission_node_id": "node-2",
                        "primary_worker_id": "worker-vue-2",
                        "evidence_ids": ["analyze-2", "reconstruct-2"],
                        "validation_evidence": {"verdict": "pass", "evaluation_score": 0.92},
                        "decision_trace": [{"step": "validate", "result": "passed"}],
                    }},
                ),
            ]
            for experience in experiences:
                store.save(experience)

            with mock.patch.object(knowledge_runtime, "collect_stable_experience_skill_groups", return_value=[{
                "domain": "javascript",
                "task_type": "mission_delivery",
                "capability_type": "frontend",
                "items": experiences,
                "count": 2,
                "avg_quality": 0.93,
            }]):
                drafted = knowledge_runtime.auto_draft_stable_experience_skills(
                    workspace,
                    "tenant-a",
                    safe_float=lambda value, default=0.0: float(value) if value is not None else default,
                    record_growth_event=lambda *args, **kwargs: None,
                )

            self.assertEqual(len(drafted), 1)
            skill_path = workspace / ".tenants" / "tenant-a" / "skills" / "draft" / "skill_auto_javascript_mission_delivery.json"
            skill = json.loads(skill_path.read_text(encoding="utf-8"))
            parameters = skill["parameters"]
            self.assertEqual(parameters["source_experience_ids"], ["experience-1", "experience-2"])
            self.assertEqual(parameters["source_mission_run_ids"], ["run-1", "run-2"])
            self.assertEqual(parameters["source_worker_ids"], ["worker-vue", "worker-vue-2"])
            self.assertEqual(parameters["evidence_ids"], [
                "analyze-1", "reconstruct-1", "analyze-2", "reconstruct-2",
            ])
            self.assertEqual(
                [item["mission_run_id"] for item in parameters["source_experiences"]],
                ["run-1", "run-2"],
            )
            self.assertEqual(
                [item["experience_id"] for item in parameters["source_experiences"]],
                ["experience-1", "experience-2"],
            )

    def test_replay_results_must_be_bound_to_candidate_and_pass_all_checks(self):
        invalid_results = [
            [{"success": True, "task_id": "task-1", "verified_by": "pytest"}],
            [{
                "success": True, "task_id": "task-1", "verified_by": "pytest",
                "validation_type": "skill_replay", "skill_id": "another-skill",
                "checks": [{"name": "smoke", "passed": True}],
            }],
            [{
                "success": True, "task_id": "task-1", "verified_by": "pytest",
                "validation_type": "skill_replay", "skill_id": "candidate-skill",
                "checks": [{"name": "smoke", "passed": False}],
            }],
            [{
                "success": True, "task_id": "task-1", "verified_by": "pytest",
                "validation_type": "skill_replay", "skill_id": "candidate-skill",
                "checks": [],
            }],
        ]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(knowledge_runtime.SkillRegistry, "verify_skill") as verify:
            for evidence in invalid_results:
                result = knowledge_runtime.maybe_auto_verify_skill_candidate(
                    Path(tmp), "tenant-a", self._skill(), "python",
                    replay_results=evidence,
                )
                self.assertIsNone(result)
            verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
