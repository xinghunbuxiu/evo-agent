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

    def test_replay_results_must_include_task_and_verifier_evidence(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(knowledge_runtime.SkillRegistry, "verify_skill") as verify:
            result = knowledge_runtime.maybe_auto_verify_skill_candidate(
                Path(tmp), "tenant-a", self._skill(), "python",
                replay_results=[{"success": True, "task_id": "task-1"}],
            )
            self.assertIsNone(result)
            verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
