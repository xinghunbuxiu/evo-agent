"""Regression tests for fail-closed Skill execution."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.skill_system import Skill, SkillExecutor, SkillTrustLevel


class SkillExecutorFailClosedTests(unittest.TestCase):
    def test_unavailable_replay_runtime_is_reported_as_failure(self):
        skill = Skill(
            id="candidate-skill",
            name="candidate",
            domain="python",
            description="",
            code="",
            trust_level=SkillTrustLevel.DRAFT,
        )
        executor = SkillExecutor.__new__(SkillExecutor)
        executor.registry = mock.Mock()
        executor.registry.find_skill.return_value = skill
        executor.execution_log = []

        result = executor.execute("python", "unit_test", {})

        self.assertFalse(result["success"])
        self.assertIn("no trusted isolated executor", result["error"])
        self.assertEqual(executor.execution_log, [])


if __name__ == "__main__":
    unittest.main()
