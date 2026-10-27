"""The central skill registry must reject untrusted success dictionaries."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.skill_system import SkillRegistry  # noqa: E402


class SkillRegistryPromotionGuardTests(unittest.TestCase):
    def test_untrusted_success_dicts_cannot_promote_skill(self):
        registry = SkillRegistry.__new__(SkillRegistry)

        verified = registry.verify_skill(
            "candidate-skill",
            [
                {"success": True, "task_id": "task-1"},
                {"success": True, "task_id": "task-2"},
                {"success": True, "task_id": "task-3"},
            ],
        )

        self.assertFalse(verified)


if __name__ == "__main__":
    unittest.main()
