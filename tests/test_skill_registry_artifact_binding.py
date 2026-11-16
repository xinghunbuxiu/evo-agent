"""SkillRegistry must consume only tenant-scoped, pinned Broker artifacts."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.skill_system import SkillRegistry, SkillTrustLevel  # noqa: E402


class SkillRegistryArtifactBindingTests(unittest.TestCase):
    def setUp(self):
        self.registry = SkillRegistry.__new__(SkillRegistry)
        self.registry.tenant_id = "tenant-a"
        self.registry.artifact_store = mock.Mock()
        self.binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill-a",
            "skill_version": "2.1.0",
            "content_sha256": "a" * 64,
            "trust_level": "verified",
            "mission_context": {
                "tenant_id": "tenant-a",
                "mission_run_id": "mission-1",
                "node_id": "node-1",
                "task_id": "task-1",
            },
        }
        self.artifact_store_result = SimpleNamespace(
            id="skill-a",
            version="2.1.0",
            code="def run(context):\n    return {'ok': True}\n",
            trust_level="verified",
            tenant_id="tenant-a",
            content_sha256="a" * 64,
        )
        self.registry.artifact_store.load_for_binding.return_value = self.artifact_store_result

    def test_loads_exact_verified_artifact_and_preserves_binding(self):
        skill = self.registry.load_published_artifact(self.binding)

        self.registry.artifact_store.load_for_binding.assert_called_once_with(self.binding)
        self.assertEqual(skill.id, "skill-a")
        self.assertEqual(skill.version, "2.1.0")
        self.assertEqual(skill.code, self.artifact_store_result.code)
        self.assertEqual(skill.trust_level, SkillTrustLevel.VERIFIED)
        self.assertEqual(skill.source, "broker_artifact")
        self.assertEqual(skill.parameters["mission_context"], self.binding["mission_context"])
        self.assertEqual(skill.parameters["content_sha256"], "a" * 64)

    def test_rejects_cross_tenant_binding_before_store_access(self):
        binding = {
            **self.binding,
            "mission_context": {**self.binding["mission_context"], "tenant_id": "tenant-b"},
        }
        with self.assertRaisesRegex(ValueError, "another tenant"):
            self.registry.load_published_artifact(binding)
        self.registry.artifact_store.load_for_binding.assert_not_called()

    def test_rejects_draft_binding_before_store_access(self):
        binding = {**self.binding, "trust_level": "draft"}
        with self.assertRaisesRegex(ValueError, "independently validated"):
            self.registry.load_published_artifact(binding)
        self.registry.artifact_store.load_for_binding.assert_not_called()

    def test_rejects_artifact_metadata_that_does_not_match_pinned_binding(self):
        self.registry.artifact_store.load_for_binding.return_value = SimpleNamespace(
            **{**self.artifact_store_result.__dict__, "content_sha256": "b" * 64}
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.registry.load_published_artifact(self.binding)


if __name__ == "__main__":
    unittest.main()
