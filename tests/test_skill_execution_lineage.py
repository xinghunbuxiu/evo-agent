"""Regression tests for skill-version-bound execution feedback."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.decision import CandidateScore, DecisionEngine, DecisionRecord  # noqa: E402
from core.learning import ExperienceStore  # noqa: E402


class SkillExecutionLineageTests(unittest.TestCase):
    def _record_execution(self, workspace: Path, *, success: bool):
        engine = DecisionEngine.__new__(DecisionEngine)
        decision = DecisionRecord(
            task_type="reconstruct",
            selected_capability_id="builtin.javascript",
            scores=[CandidateScore("builtin.javascript", 1.0, ["explicit"])],
        )
        result = SimpleNamespace(
            success=success,
            confidence=0.91 if success else 0.2,
            summary="reconstruction completed" if success else "reconstruction failed",
            feedback={
                "matched_verified_skills": [{
                    "id": "skill_vue_reconstruct",
                    "name": "Vue reconstruction",
                    "version": "2.4.1",
                    "trust_level": "verified",
                }],
                "skill_execution_template": {
                    "skill_id": "skill_vue_reconstruct",
                    "skill_name": "Vue reconstruction",
                    "skill_version": "2.4.1",
                    "skill_trust_level": "verified",
                },
            },
        )
        evaluation = SimpleNamespace(
            score=0.93 if success else 0.18,
            to_dict=lambda: {
                "score": 0.93 if success else 0.18,
                "verdict": "pass" if success else "fail",
            },
        )
        engine._record_execution_experience(
            workspace=workspace,
            tenant_id="tenant-skill",
            task_type="reconstruct",
            input_path=None,
            source_dir=workspace / "input",
            preferred_tags=["javascript"],
            domain_hint="javascript",
            decision=decision,
            result=result,
            evaluation=evaluation,
            parameters={
                "task_id": "task-42",
                "mission_run_id": "mission-7",
                "mission_node_id": "node-reconstruct",
                "worker_id": "worker-vue",
            },
            signals={"framework_hint": "vue"},
        )

    def test_experience_persists_skill_id_version_and_real_execution_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._record_execution(workspace, success=True)

            experiences = ExperienceStore(workspace, "tenant-skill").load_by_domain("javascript")
            self.assertEqual(len(experiences), 1)
            evidence = experiences[0].metadata["skill_execution"]
            self.assertEqual(evidence["schema_version"], "skill.execution.feedback.v1")
            self.assertEqual(evidence["skill_id"], "skill_vue_reconstruct")
            self.assertEqual(evidence["skill_version"], "2.4.1")
            self.assertEqual(evidence["skill_trust_level"], "verified")
            self.assertEqual(evidence["application_mode"], "provider_execution_template")
            self.assertTrue(evidence["execution_success"])
            self.assertEqual(evidence["execution_status"], "succeeded")
            self.assertEqual(evidence["task_id"], "task-42")
            self.assertEqual(evidence["mission_run_id"], "mission-7")
            self.assertEqual(evidence["mission_node_id"], "node-reconstruct")
            self.assertEqual(evidence["worker_id"], "worker-vue")
            self.assertEqual(evidence["matched_skills"][0]["version"], "2.4.1")
            self.assertEqual(evidence["evaluation"]["verdict"], "pass")

    def test_failed_skill_application_is_recorded_as_failed_not_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self._record_execution(workspace, success=False)

            experiences = ExperienceStore(workspace, "tenant-skill").load_by_domain("javascript")
            evidence = experiences[0].metadata["skill_execution"]
            self.assertFalse(evidence["execution_success"])
            self.assertEqual(evidence["execution_status"], "failed")
            self.assertEqual(evidence["evaluation"]["verdict"], "fail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
