"""Tests for the broker-owned immutable Skill artifact store."""
import base64
import json
import os
import sys
import tempfile
import unittest
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.skill_artifact_store import (
    SkillArtifactStore, SkillArtifactStoreError, VALIDATION_ATTESTATION_SCHEMA,
)


class SkillArtifactStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "trusted-artifacts"
        self.root.mkdir(mode=0o700)
        self.validator_key = Ed25519PrivateKey.generate()
        self.store = SkillArtifactStore(
            self.root,
            validator_public_key=self.validator_key.public_key().public_bytes_raw(),
            validator_key_id="validator-test-key",
        )
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

    def _attestation(
        self, skill=None, *, tenant_id="tenant-one", mission_context=None,
        workspace_id="workspace-one", broker_request_id="00000000-0000-4000-8000-000000000001",
    ):
        candidate = skill or self.skill
        import hashlib
        context = dict(mission_context or self.context)
        payload = {
            "schema_version": VALIDATION_ATTESTATION_SCHEMA,
            "validation_id": "validation-001",
            "validator_id": "independent-validator",
            "policy_id": "test-policy-v1",
            "policy_sha256": "a" * 64,
            "workspace_id": workspace_id,
            "tenant_id": tenant_id,
            "mission_run_id": context["mission_run_id"],
            "node_id": context["node_id"],
            "task_id": context["task_id"],
            "broker_request_id": broker_request_id,
            "broker_attestation_sha256": "b" * 64,
            "checks_sha256": "c" * 64,
            "skill_id": candidate.id,
            "skill_version": candidate.version,
            "content_sha256": hashlib.sha256(candidate.code.encode("utf-8")).hexdigest(),
            "trust_level": candidate.trust_level,
            "passed": True,
        }
        signature = self.validator_key.sign(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8"))
        return {
            **payload,
            "signature": {
                "algorithm": "ed25519",
                "key_id": "validator-test-key",
                "value": base64.b64encode(signature).decode("ascii"),
            },
        }

    def _publish(
        self, *, tenant_id="tenant-one", skill=None, validation_attestation=None,
        workspace_id="workspace-one", mission_context=None,
        broker_request_id=None, broker_attestation_sha256=None,
    ):
        candidate = skill or self.skill
        attestation = (
            self._attestation(candidate, tenant_id=tenant_id)
            if validation_attestation is None else validation_attestation
        )
        return self.store.publish(
            tenant_id=tenant_id,
            skill=candidate,
            validation_attestation=attestation,
            workspace_id=workspace_id,
            mission_context=dict(mission_context or self.context),
            broker_request_id=broker_request_id or attestation.get(
                "broker_request_id", "00000000-0000-4000-8000-000000000001",
            ),
            broker_attestation_sha256=broker_attestation_sha256 or attestation.get(
                "broker_attestation_sha256", "b" * 64,
            ),
        )

    def _publish_binding(self):
        identity = self._publish(
            tenant_id="tenant-one", skill=self.skill,
            validation_attestation=self._attestation(),
        )
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

    def test_publish_verifies_final_artifact_readback_before_returning_success(self):
        original_load = self.store.load_for_binding
        with patch.object(self.store, "load_for_binding", wraps=original_load) as readback:
            identity = self._publish()

        readback.assert_called_once()
        binding = readback.call_args.args[0]
        self.assertEqual(binding["tenant_id"] if "tenant_id" in binding else binding["mission_context"]["tenant_id"], "tenant-one")
        self.assertEqual(binding["skill_id"], identity["skill_id"])
        self.assertEqual(binding["skill_version"], identity["skill_version"])
        self.assertEqual(binding["content_sha256"], identity["content_sha256"])
        self.assertEqual(binding["trust_level"], "verified")

    def test_publish_fails_closed_when_final_artifact_readback_fails(self):
        with patch.object(
            self.store,
            "load_for_binding",
            side_effect=SkillArtifactStoreError("simulated readback failure"),
        ):
            with self.assertRaisesRegex(
                SkillArtifactStoreError,
                "failed readback verification",
            ):
                self._publish()

        # The immutable file may already exist, but no success identity/receipt
        # can be returned until a later exact retry verifies the persisted bytes.
        artifact = self.root / "tenant-one" / self.skill.id / "1.2.0.json"
        self.assertTrue(artifact.is_file())

    def test_stages_draft_candidate_for_isolated_replay_without_trust_promotion(self):
        candidate = SimpleNamespace(
            id=self.skill.id,
            version=self.skill.version,
            code=self.skill.code,
            trust_level="draft",
        )
        identity = self.store.stage_candidate(tenant_id="tenant-one", skill=candidate)
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": identity["skill_id"],
            "skill_version": identity["skill_version"],
            "content_sha256": identity["content_sha256"],
            "trust_level": "draft",
            "mission_context": self.context,
        }

        loaded = self.store.load_for_binding(binding)
        self.assertEqual(loaded.code, candidate.code)
        self.assertEqual(loaded.trust_level, "draft")
        self.assertEqual(loaded.tenant_id, "tenant-one")
        candidate_path = self.root / "tenant-one" / candidate.id / "1.2.0.candidate.json"
        self.assertEqual(candidate_path.stat().st_mode & 0o777, 0o400)
        self.assertNotIn("validation_attestation", json.loads(candidate_path.read_text(encoding="utf-8")))

        with self.assertRaisesRegex(SkillArtifactStoreError, "only verified or cloud"):
            self._publish(
                tenant_id="tenant-one", skill=candidate,
                validation_attestation=self._attestation(candidate),
            )
        repeated = self.store.stage_candidate(tenant_id="tenant-one", skill=candidate)
        self.assertEqual(repeated, identity)
        changed_candidate = SimpleNamespace(
            id=candidate.id,
            version=candidate.version,
            code="different source",
            trust_level="draft",
        )
        with self.assertRaisesRegex(SkillArtifactStoreError, "different content"):
            self.store.stage_candidate(tenant_id="tenant-one", skill=changed_candidate)

    def test_draft_candidate_is_tenant_scoped_and_digest_pinned(self):
        candidate = SimpleNamespace(
            id=self.skill.id, version=self.skill.version,
            code=self.skill.code, trust_level="draft",
        )
        identity = self.store.stage_candidate(tenant_id="tenant-one", skill=candidate)
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": identity["skill_id"],
            "skill_version": identity["skill_version"],
            "content_sha256": identity["content_sha256"],
            "trust_level": "draft",
            "mission_context": self.context,
        }
        wrong_tenant = {**binding, "mission_context": {**self.context, "tenant_id": "tenant-other"}}
        with self.assertRaisesRegex(SkillArtifactStoreError, "unavailable"):
            self.store.load_for_binding(wrong_tenant)
        changed = dict(binding, content_sha256="0" * 64)
        with self.assertRaisesRegex(SkillArtifactStoreError, "identity"):
            self.store.load_for_binding(changed)

    def test_validator_attestation_cannot_be_replayed_for_another_mission(self):
        old_context = {**self.context, "mission_run_id": "mission-old"}
        old_attestation = self._attestation(mission_context=old_context)
        with self.assertRaisesRegex(SkillArtifactStoreError, "does not bind this Mission execution"):
            self._publish(validation_attestation=old_attestation, mission_context=self.context)

    def test_validator_attestation_must_bind_exact_broker_response(self):
        attestation = self._attestation()
        with self.assertRaisesRegex(SkillArtifactStoreError, "does not bind this signed Broker response"):
            self._publish(validation_attestation=attestation, broker_attestation_sha256="d" * 64)

    def test_rejects_draft_and_empty_code(self):
        for trust, code in (("draft", self.skill.code), ("verified", "  ")):
            candidate = SimpleNamespace(
                id=self.skill.id, version=self.skill.version,
                code=code, trust_level=trust,
            )
            with self.subTest(trust=trust, code=code), self.assertRaises(SkillArtifactStoreError):
                self._publish(
                    tenant_id="tenant-one", skill=candidate,
                    validation_attestation=self._attestation(candidate),
                )


    def test_final_path_is_invisible_until_complete_file_is_ready(self):
        import os

        binding_digest = __import__("hashlib").sha256(self.skill.code.encode("utf-8")).hexdigest()
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": self.skill.id,
            "skill_version": self.skill.version,
            "content_sha256": binding_digest,
            "trust_level": self.skill.trust_level,
            "mission_context": self.context,
        }
        artifact_path = self.root / "tenant-one" / self.skill.id / "1.2.0.json"
        entered_link = threading.Event()
        allow_link = threading.Event()
        real_link = os.link
        outcome = []

        def pause_before_atomic_link(source, destination, **kwargs):
            entered_link.set()
            if not allow_link.wait(5):
                raise TimeoutError("test did not release atomic publication")
            return real_link(source, destination, **kwargs)

        def publish():
            try:
                outcome.append(self._publish(
                    tenant_id="tenant-one",
                    skill=self.skill,
                    validation_attestation=self._attestation(),
                ))
            except Exception as exc:
                outcome.append(exc)

        with patch("core.skill_artifact_store.os.link", side_effect=pause_before_atomic_link):
            thread = threading.Thread(target=publish)
            thread.start()
            self.assertTrue(entered_link.wait(5), "publisher never reached atomic publication")
            self.assertFalse(artifact_path.exists(), "final artifact became visible before atomic publication")
            allow_link.set()
            thread.join(5)

        self.assertFalse(thread.is_alive(), "publisher did not finish")
        self.assertEqual(len(outcome), 1)
        self.assertIsInstance(outcome[0], dict)
        loaded = self.store.load_for_binding(binding)
        self.assertEqual(loaded.code, self.skill.code)
        self.assertEqual(json.loads(artifact_path.read_text(encoding="utf-8"))["code"], self.skill.code)

    def test_concurrent_identical_publishers_all_receive_the_same_create_once_result(self):
        barrier = threading.Barrier(8)

        def publish_same_version(_index):
            barrier.wait(timeout=5)
            try:
                return self._publish(
                    tenant_id="tenant-one",
                    skill=self.skill,
                    validation_attestation=self._attestation(),
                )
            except SkillArtifactStoreError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(publish_same_version, range(8)))

        successes = [result for result in results if isinstance(result, dict)]
        failures = [result for result in results if isinstance(result, Exception)]
        self.assertEqual(len(successes), 8)
        self.assertEqual(failures, [])
        self.assertTrue(all(result == successes[0] for result in successes))
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": self.skill.id,
            "skill_version": self.skill.version,
            "content_sha256": successes[0]["content_sha256"],
            "trust_level": self.skill.trust_level,
            "mission_context": self.context,
        }
        self.assertEqual(self.store.load_for_binding(binding).code, self.skill.code)

    def test_exact_repeat_publication_is_idempotent(self):
        attestation = self._attestation()
        first = self._publish(validation_attestation=attestation)
        second = self._publish(validation_attestation=attestation)
        self.assertEqual(second, first)
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": first["skill_id"],
            "skill_version": first["skill_version"],
            "content_sha256": first["content_sha256"],
            "trust_level": first["trust_level"],
            "mission_context": self.context,
        }
        self.assertEqual(self.store.load_for_binding(binding).code, self.skill.code)

    def test_existing_artifact_with_different_signed_attestation_is_not_reused(self):
        self._publish()
        changed_attestation = self._attestation()
        signed_payload = {
            key: value for key, value in changed_attestation.items()
            if key != "signature"
        }
        signed_payload["validation_id"] = "validation-002"
        signature = self.validator_key.sign(json.dumps(
            signed_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8"))
        changed_attestation = {
            **signed_payload,
            "signature": {
                "algorithm": "ed25519",
                "key_id": "validator-test-key",
                "value": base64.b64encode(signature).decode("ascii"),
            },
        }
        with self.assertRaisesRegex(SkillArtifactStoreError, "already exists"):
            self._publish(validation_attestation=changed_attestation)

    def test_rejects_duplicate_version_instead_of_overwriting(self):
        self._publish_binding()
        changed = SimpleNamespace(
            id=self.skill.id, version=self.skill.version,
            code="def run():\n    return False\n", trust_level="verified",
        )
        with self.assertRaisesRegex(SkillArtifactStoreError, "already exists"):
            self._publish(
                tenant_id="tenant-one", skill=changed,
                validation_attestation=self._attestation(changed),
            )

    def test_rejects_unsigned_or_mismatched_validation_attestation(self):
        forged = self._attestation()
        forged["signature"] = dict(forged["signature"], value=base64.b64encode(b"invalid").decode("ascii"))
        with self.assertRaisesRegex(SkillArtifactStoreError, "signature verification failed"):
            self._publish(
                tenant_id="tenant-one", skill=self.skill,
                validation_attestation=forged,
            )
        wrong_skill = self._attestation()
        wrong_skill["skill_id"] = "skill_other"
        with self.assertRaisesRegex(SkillArtifactStoreError, "does not bind"):
            self._publish(
                tenant_id="tenant-one", skill=self.skill,
                validation_attestation=wrong_skill,
            )
        elevated = self._attestation()
        elevated["trust_level"] = "cloud"
        with self.assertRaisesRegex(SkillArtifactStoreError, "does not bind"):
            self._publish(
                tenant_id="tenant-one", skill=self.skill,
                validation_attestation=elevated,
            )

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
        with self.assertRaisesRegex(SkillArtifactStoreError, "content digest mismatch"):
            self.store.load_for_binding(binding)

    def test_reverifies_persisted_validator_attestation_on_every_load(self):
        binding = self._publish_binding()
        path = self.root / "tenant-one" / self.skill.id / "1.2.0.json"
        os.chmod(path, 0o600)
        artifact = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("validation_attestation", artifact)
        artifact["validation_attestation"]["passed"] = False
        path.write_text(json.dumps(artifact), encoding="utf-8")
        os.chmod(path, 0o400)
        with self.assertRaisesRegex(SkillArtifactStoreError, "did not pass"):
            self.store.load_for_binding(binding)

    def test_rejects_malformed_mission_lineage_values(self):
        binding = self._publish_binding()
        for field, value in (
            ("mission_run_id", "../mission"),
            ("node_id", ""),
            ("task_id", "task/other"),
        ):
            malformed = dict(
                binding,
                mission_context={**self.context, field: value},
            )
            with self.subTest(field=field), self.assertRaisesRegex(
                SkillArtifactStoreError, field
            ):
                self.store.load_for_binding(malformed)

    def test_rejects_surrogate_code_as_invalid_utf8(self):
        candidate = SimpleNamespace(
            id="skill_surrogate",
            version="1.0.0",
            code="bad\ud800code",
            trust_level="verified",
        )
        with self.assertRaisesRegex(SkillArtifactStoreError, "valid UTF-8"):
            self._publish(
                tenant_id="tenant-one",
                skill=candidate,
                validation_attestation={},
            )

    def test_rejects_cross_tenant_and_cross_skill_bindings(self):
        binding = self._publish_binding()
        other_tenant = dict(binding, mission_context={**self.context, "tenant_id": "tenant-two"})
        with self.assertRaisesRegex(SkillArtifactStoreError, "unavailable"):
            self.store.load_for_binding(other_tenant)
        other_skill = dict(binding, skill_id="skill_other")
        with self.assertRaisesRegex(SkillArtifactStoreError, "unavailable"):
            self.store.load_for_binding(other_skill)

    def test_created_directory_entries_are_fsynced_parent_first(self):
        tenant_dir = self.root / "tenant-one"
        skill_dir = tenant_dir / self.skill.id
        with patch("core.skill_artifact_store._fsync_directory") as fsync_directory:
            path = self.store._artifact_path(
                "tenant-one", self.skill.id, self.skill.version, create=True,
            )
        self.assertEqual(path.parent, skill_dir)
        self.assertEqual(
            [entry.args[0] for entry in fsync_directory.call_args_list],
            [self.root, tenant_dir],
        )

    def test_directory_fsync_failure_fails_closed_before_artifact_publication(self):
        with patch(
            "core.skill_artifact_store._fsync_directory",
            side_effect=SkillArtifactStoreError("artifact directory durability could not be confirmed"),
        ):
            with self.assertRaisesRegex(SkillArtifactStoreError, "directory durability"):
                self._publish()
        self.assertFalse(
            (self.root / "tenant-one" / self.skill.id / "1.2.0.json").exists()
        )

    def test_read_does_not_create_missing_artifact_directories(self):
        missing = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill_missing",
            "skill_version": "1.0.0",
            "content_sha256": "a" * 64,
            "trust_level": "verified",
            "mission_context": self.context,
        }
        malformed_trust = dict(missing, trust_level=[])
        with self.assertRaises(SkillArtifactStoreError):
            self.store.load_for_binding(malformed_trust)
        with self.assertRaises(SkillArtifactStoreError):
            self.store.load_for_binding(missing)
        self.assertFalse((self.root / "tenant-one").exists())

    def test_rejects_symlink_artifact_directory(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir(mode=0o700)
        (self.root / "tenant-one").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(SkillArtifactStoreError, "symlink"):
            self._publish(
                tenant_id="tenant-one", skill=self.skill,
                validation_attestation=self._attestation(),
            )


if __name__ == "__main__":
    unittest.main()
