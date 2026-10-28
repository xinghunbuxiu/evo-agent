"""The central skill registry must reject untrusted success dictionaries."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.skill_system import Skill, SkillRegistry, SkillTrustLevel  # noqa: E402


class SkillRegistryPromotionGuardTests(unittest.TestCase):
    def test_local_verified_json_cannot_publish_without_trusted_replay_record(self):
        registry = SkillRegistry.__new__(SkillRegistry)
        registry._load_local_verified = lambda _skill_id: Skill(
            id="candidate-skill",
            name="candidate",
            domain="python",
            description="",
            code="",
            trust_level=SkillTrustLevel.VERIFIED,
        )
        registry.cloud_store = mock.Mock()

        published = registry.publish_to_cloud("candidate-skill")

        self.assertFalse(published)
        registry.cloud_store.save_knowledge.assert_not_called()

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
