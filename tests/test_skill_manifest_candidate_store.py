"""Regression tests for immutable Manifest-bearing Skill candidates."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.skill_artifact_store import SkillArtifactStore, SkillArtifactStoreError
from core.skill_manifest import manifest_sha256, normalize_skill_manifest


class ManifestCandidateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "broker-artifacts"
        self.root.mkdir(mode=0o700)
        self.store = SkillArtifactStore(
            self.root,
            validator_public_key=bytes.fromhex("11" * 32),
            validator_key_id="validator-key",
        )
        self.manifest = {
            "schema_version": "mission.skill-manifest.v1",
            "skill_id": "skill-manifest-test",
            "skill_version": "1.0.0",
            "name": "Manifest test",
            "domain": "testing",
            "capability_type": "test",
            "description": "A test candidate with an immutable Manifest",
            "task_types": ["test.run"],
            "input_schema": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
            "runtime_contract": {
                "id": "python.run_context.v1",
                "entrypoint": "run",
                "call_signature": "run(context)",
            },
            "compatibility": {
                "runtime": "python",
                "min_version": "3.11",
                "max_version": "3.13",
            },
        }
        self.skill = SimpleNamespace(
            id="skill-manifest-test",
            version="1.0.0",
            code="def run(context):\n    return {'ok': bool(context['value'])}\n",
            trust_level="draft",
        )

    def tearDown(self):
        self.temp.cleanup()

    def _stage(self):
        return self.store.stage_candidate(
            tenant_id="tenant-a",
            skill=self.skill,
            manifest=self.manifest,
            expected_manifest_sha256=manifest_sha256(self.manifest),
        )

    def test_loads_manifest_candidate_only_when_both_digests_match(self):
        identity = self._stage()
        loaded = self.store.load_candidate_manifest(
            tenant_id="tenant-a",
            skill_id=identity["skill_id"],
            skill_version=identity["skill_version"],
            content_sha256=identity["content_sha256"],
            manifest_sha256=identity["manifest_sha256"],
        )
        self.assertEqual(loaded.code, self.skill.code)
        self.assertEqual(loaded.manifest, normalize_skill_manifest(self.manifest))
        self.assertEqual(loaded.content_sha256, identity["content_sha256"])
        self.assertEqual(loaded.manifest_sha256, identity["manifest_sha256"])
        self.assertEqual(loaded.tenant_id, "tenant-a")

    def test_rejects_wrong_code_or_manifest_digest(self):
        identity = self._stage()
        with self.assertRaisesRegex(SkillArtifactStoreError, "digest or Manifest identity"):
            self.store.load_candidate_manifest(
                tenant_id="tenant-a",
                skill_id=identity["skill_id"],
                skill_version=identity["skill_version"],
                content_sha256="0" * 64,
                manifest_sha256=identity["manifest_sha256"],
            )
        with self.assertRaisesRegex(SkillArtifactStoreError, "digest or Manifest identity"):
            self.store.load_candidate_manifest(
                tenant_id="tenant-a",
                skill_id=identity["skill_id"],
                skill_version=identity["skill_version"],
                content_sha256=identity["content_sha256"],
                manifest_sha256="0" * 64,
            )

    def test_rejects_cross_tenant_candidate_resolution(self):
        identity = self._stage()
        with self.assertRaisesRegex(SkillArtifactStoreError, "unavailable"):
            self.store.load_candidate_manifest(
                tenant_id="tenant-b",
                skill_id=identity["skill_id"],
                skill_version=identity["skill_version"],
                content_sha256=identity["content_sha256"],
                manifest_sha256=identity["manifest_sha256"],
            )

    def test_rechecks_persisted_manifest_and_code_bytes_on_every_load(self):
        identity = self._stage()
        path = self.root / "tenant-a" / self.skill.id / "1.0.0.candidate.v2.json"
        path.chmod(0o600)
        artifact = json.loads(path.read_text(encoding="utf-8"))
        artifact["manifest"]["description"] = "substituted Manifest"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        path.chmod(0o400)
        with self.assertRaisesRegex(SkillArtifactStoreError, "digest or Manifest identity"):
            self.store.load_candidate_manifest(
                tenant_id="tenant-a",
                skill_id=identity["skill_id"],
                skill_version=identity["skill_version"],
                content_sha256=identity["content_sha256"],
                manifest_sha256=identity["manifest_sha256"],
            )

    def test_v2_candidate_retry_is_create_once(self):
        first = self._stage()
        second = self._stage()
        self.assertEqual(second, first)
        changed = SimpleNamespace(
            id=self.skill.id,
            version=self.skill.version,
            code="def run(context):\n    return {'ok': False}\n",
            trust_level="draft",
        )
        with self.assertRaisesRegex(SkillArtifactStoreError, "different content"):
            self.store.stage_candidate(
                tenant_id="tenant-a",
                skill=changed,
                manifest=self.manifest,
                expected_manifest_sha256=manifest_sha256(self.manifest),
            )


if __name__ == "__main__":
    unittest.main()
