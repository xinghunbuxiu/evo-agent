"""Tests for the broker-owned immutable Skill artifact store."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.skill_artifact_store import SkillArtifactStore, SkillArtifactStoreError


class SkillArtifactStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "trusted-artifacts"
        self.root.mkdir(mode=0o700)
        self.store = SkillArtifactStore(self.root)
        self.skill = SimpleNamespace(
            id="skill_android_login",
            version="1.2.0",
            code="def run():\n    return True\n",
            trust_level="verified",
        )
        self.context = {
            "tenant_id": "tenant-one",
            "mission_run_id": "mission-1",
            "node_id": "node-1",
            "task_id": "task-1",
        }

    def tearDown(self):
        self.temp.cleanup()

    def _publish_binding(self):
        identity = self.store.publish(tenant_id="tenant-one", skill=self.skill)
        return {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": identity["skill_id"],
            "skill_version": identity["skill_version"],
            "content_sha256": identity["content_sha256"],
            "trust_level": identity["trust_level"],
            "mission_context": self.context,
        }

    def test_publishes_and_loads_exact_verified_artifact(self):
        binding = self._publish_binding()
        loaded = self.store.load_for_binding(binding)
        self.assertEqual(loaded.id, self.skill.id)
        self.assertEqual(loaded.version, self.skill.version)
        self.assertEqual(loaded.code, self.skill.code)
        self.assertEqual(loaded.tenant_id, "tenant-one")
        artifact = self.root / "tenant-one" / self.skill.id / "1.2.0.json"
        self.assertEqual(artifact.stat().st_mode & 0o777, 0o400)

    def test_rejects_draft_and_empty_code(self):
        for trust, code in (("draft", self.skill.code), ("verified", "  ")):
            candidate = SimpleNamespace(
                id=self.skill.id, version=self.skill.version,
                code=code, trust_level=trust,
            )
            with self.subTest(trust=trust, code=code), self.assertRaises(SkillArtifactStoreError):
                self.store.publish(tenant_id="tenant-one", skill=candidate)

    def test_rejects_duplicate_version_instead_of_overwriting(self):
        self._publish_binding()
        changed = SimpleNamespace(
            id=self.skill.id, version=self.skill.version,
            code="def run():\n    return False\n", trust_level="verified",
        )
        with self.assertRaisesRegex(SkillArtifactStoreError, "already exists"):
            self.store.publish(tenant_id="tenant-one", skill=changed)

    def test_rejects_tampered_digest_and_artifact_content(self):
        binding = self._publish_binding()
        changed_binding = dict(binding, content_sha256="0" * 64)
        with self.assertRaisesRegex(SkillArtifactStoreError, "identity"):
            self.store.load_for_binding(changed_binding)

        path = self.root / "tenant-one" / self.skill.id / "1.2.0.json"
        os.chmod(path, 0o600)
        artifact = json.loads(path.read_text(encoding="utf-8"))
        artifact["code"] = "def run():\n    return False\n"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        os.chmod(path, 0o400)
        with self.assertRaisesRegex(SkillArtifactStoreError, "read-only"):
            self.store.load_for_binding(binding)

    def test_rejects_cross_tenant_and_cross_skill_bindings(self):
        binding = self._publish_binding()
        other_tenant = dict(binding, mission_context={**self.context, "tenant_id": "tenant-two"})
        with self.assertRaisesRegex(SkillArtifactStoreError, "unavailable"):
            self.store.load_for_binding(other_tenant)
        other_skill = dict(binding, skill_id="skill_other")
        with self.assertRaisesRegex(SkillArtifactStoreError, "unavailable"):
            self.store.load_for_binding(other_skill)

    def test_read_does_not_create_missing_artifact_directories(self):
        missing = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill_missing",
            "skill_version": "1.0.0",
            "content_sha256": "a" * 64,
            "trust_level": "verified",
            "mission_context": self.context,
        }
        with self.assertRaises(SkillArtifactStoreError):
            self.store.load_for_binding(missing)
        self.assertFalse((self.root / "tenant-one").exists())

    def test_rejects_symlink_artifact_directory(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir(mode=0o700)
        (self.root / "tenant-one").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(SkillArtifactStoreError, "symlink"):
            self.store.publish(tenant_id="tenant-one", skill=self.skill)


if __name__ == "__main__":
    unittest.main()
