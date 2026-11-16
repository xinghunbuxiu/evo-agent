"""SkillRegistry must consume only tenant-scoped, pinned Broker artifacts."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.skill_system import Skill, SkillExecutor, SkillRegistry, SkillTrustLevel  # noqa: E402


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

    def _executor(self):
        executor = SkillExecutor.__new__(SkillExecutor)
        executor.workspace = Path(".")
        executor.tenant_id = "tenant-a"
        executor.registry = mock.Mock()
        executor.execution_log = []
        return executor

    def test_executor_uses_only_explicit_pinned_artifact_when_binding_is_supplied(self):
        executor = self._executor()
        skill = Skill(
            id="skill-a",
            name="skill-a",
            domain="mission",
            description="published",
            code="isolated payload",
            trust_level=SkillTrustLevel.VERIFIED,
            source="broker_artifact",
            version="2.1.0",
        )
        executor.registry.load_published_artifact.return_value = skill
        executor._execute_skill_code = mock.Mock(
            return_value={"success": True, "data": {"accepted": True}, "message": "ok"}
        )

        result = executor.execute(
            "dev", "build", {"input": "x"}, artifact_binding=self.binding
        )

        executor.registry.load_published_artifact.assert_called_once_with(self.binding)
        executor.registry.find_skill.assert_not_called()
        executor._execute_skill_code.assert_called_once_with(skill, {"input": "x"})
        self.assertTrue(result["success"])
        self.assertEqual(result["skill_id"], "skill-a")

    def test_executor_fails_closed_on_invalid_binding_without_lookup_fallback(self):
        executor = self._executor()
        executor.registry.load_published_artifact.side_effect = ValueError("another tenant")
        executor._execute_skill_code = mock.Mock()

        result = executor.execute(
            "dev", "build", {}, artifact_binding=self.binding
        )

        self.assertFalse(result["success"])
        self.assertIn("another tenant", result["error"])
        executor.registry.find_skill.assert_not_called()
        executor._execute_skill_code.assert_not_called()

    def test_executor_keeps_legacy_lookup_when_no_artifact_binding_is_supplied(self):
        executor = self._executor()
        skill = Skill(
            id="local-skill",
            name="local-skill",
            domain="dev",
            description="local",
            code="",
            trust_level=SkillTrustLevel.DRAFT,
        )
        executor.registry.find_skill.return_value = skill
        executor._execute_skill_code = mock.Mock(
            return_value={"success": True, "data": None, "message": "ok"}
        )

        result = executor.execute("dev", "build", {})

        executor.registry.find_skill.assert_called_once_with("dev", "build", False)
        executor.registry.load_published_artifact.assert_not_called()
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
