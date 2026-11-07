"""The placeholder skill executor must not promote or publish skills."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.skill_system import SkillExecutor  # noqa: E402


class SkillExecutorPromotionGuardTests(unittest.TestCase):
    def test_placeholder_executor_cannot_verify_or_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            executor = SkillExecutor.__new__(SkillExecutor)
            executor.workspace = Path(tmp)
            executor.tenant_id = "tenant-a"
            executor.registry = mock.Mock()
            executor.execution_log = [
                {"skill_id": "candidate", "success": True},
                {"skill_id": "candidate", "success": True},
                {"skill_id": "candidate", "success": True},
            ]

            result = executor.verify_and_publish("candidate")

            self.assertFalse(result["success"])
            self.assertFalse(result["verified"])
            self.assertFalse(result["published"])
            self.assertIn("placeholder", result["message"])
            executor.registry.verify_skill.assert_not_called()
            executor.registry.publish_to_cloud.assert_not_called()


if __name__ == "__main__":
    unittest.main()
