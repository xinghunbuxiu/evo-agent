"""Tests for signed Skill Replay evidence persistence and Experience linkage."""
import base64
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.sandbox_broker_protocol import (
    BROKER_RESPONSE_SCHEMA, SKILL_ARTIFACT_RESOLUTION_SCHEMA,
    SKILL_REPLAY_OUTPUT_SCHEMA, SKILL_REPLAY_PROFILE_ID,
)
from core.skill_replay_evidence_store import SkillReplayEvidenceError, SkillReplayEvidenceStore


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class SkillReplayEvidenceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "evidence"
        self.root.mkdir(mode=0o700)
        self.key = Ed25519PrivateKey.generate()
        self.store = SkillReplayEvidenceStore(
            self.root, broker_public_key=self.key.public_key().public_bytes_raw(),
            broker_key_id="broker-test-key",
        )
        self.context = {
            "tenant_id": "tenant-a", "mission_run_id": "mission-1",
            "node_id": "node-1", "task_id": "task-1",
        }
        self.binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill-demo", "skill_version": "1.0.0",
            "content_sha256": "a" * 64, "trust_level": "verified",
            "mission_context": self.context,
        }

    def tearDown(self):
        self.temp.cleanup()

    def _attested(self, *, success=True, request_id=None):
        request_id = request_id or str(uuid.uuid4())
        target = f"{self.binding['skill_id']}@{self.binding['skill_version']}"
        result = {
            "schema_version": "mission.execution-result.v2",
            "runner": {"id": "evo-sandbox-broker", "version": "1"},
            "profile_id": SKILL_REPLAY_PROFILE_ID, "target": target,
            "exit_code": 0 if success else 1, "timed_out": False,
            "execution_succeeded": success,
            "stdout": {"bytes": 0, "available_bytes": 0, "capture_truncated": False, "sha256": "0" * 64},
            "stderr": {"bytes": 0, "available_bytes": 0, "capture_truncated": False, "sha256": "0" * 64},
        }
        output = {
            "schema_version": SKILL_REPLAY_OUTPUT_SCHEMA, "success": success,
            "value": {"ok": True} if success else None,
            "error": None if success else {"type": "AssertionError", "message": "expected value"},
            "logs": "",
        }
        payload = {
            "schema_version": BROKER_RESPONSE_SCHEMA, "request_id": request_id,
            "workspace_id": "workspace-a", "mission_context": self.context,
            "skill_binding": self.binding,
            "skill_artifact": {
                "schema_version": SKILL_ARTIFACT_RESOLUTION_SCHEMA,
                "skill_id": self.binding["skill_id"], "skill_version": self.binding["skill_version"],
                "content_sha256": self.binding["content_sha256"], "trust_level": self.binding["trust_level"],
            },
            "skill_replay_output": output, "result": result,
        }
        envelope = {
            **payload,
            "signature": {
                "algorithm": "ed25519", "key_id": "broker-test-key",
                "value": base64.b64encode(self.key.sign(_canonical(payload))).decode("ascii"),
            },
        }
        return {
            "schema_version": "mission.sandbox-broker-attestation.v1",
            "attestation": envelope, "result": result, "skill_replay_output": output,
        }

    def test_persists_verifies_and_links_experience(self):
        attested = self._attested()
        ref = self.store.record(
            attested, tenant_id="tenant-a", workspace_id="workspace-a",
            mission_context=self.context, skill_binding=self.binding,
        )
        loaded = self.store.load_verified(tenant_id="tenant-a", evidence_id=ref["evidence_id"])
        self.assertEqual(loaded["broker_attestation"]["request_id"], ref["evidence_id"])
        self.assertEqual(loaded["skill_replay_output"]["value"], {"ok": True})
        experience = self.store.record_experience(
            Path(self.temp.name) / "workspace", tenant_id="tenant-a",
            evidence_id=ref["evidence_id"], domain="python",
            task_type="skill_replay", input_summary="Replay skill-demo@1.0.0",
        )
        replay = experience.metadata["skill_replay"]
        self.assertEqual(replay["skill_version"], "1.0.0")
        self.assertTrue(replay["execution_success"])
        self.assertEqual(replay["reflection"]["status"], "pending")
        self.assertIsNone(replay["reflection"]["reusable_experience"])
        repeated = self.store.record_experience(
            Path(self.temp.name) / "workspace", tenant_id="tenant-a",
            evidence_id=ref["evidence_id"], domain="python",
            task_type="skill_replay", input_summary="Replay skill-demo@1.0.0",
        )
        self.assertEqual(repeated.created_at, experience.created_at)

    def test_failed_replay_records_actual_error_and_pending_reflection(self):
        attested = self._attested(success=False)
        ref = self.store.record(
            attested, tenant_id="tenant-a", workspace_id="workspace-a",
            mission_context=self.context, skill_binding=self.binding,
        )
        exp = self.store.record_experience(
            Path(self.temp.name) / "workspace", tenant_id="tenant-a",
            evidence_id=ref["evidence_id"], domain="python",
            task_type="skill_replay", input_summary="failed replay",
        )
        replay = exp.metadata["skill_replay"]
        self.assertFalse(replay["execution_success"])
        self.assertEqual(replay["execution_status"], "failed")
        self.assertEqual(replay["failure"]["type"], "AssertionError")
        self.assertEqual(replay["reflection"]["error_reason"]["message"], "expected value")

    def test_rejects_tampering_wrong_tenant_and_unbound_projection(self):
        attested = self._attested()
        tampered = dict(attested, attestation=dict(attested["attestation"]))
        tampered["attestation"]["skill_replay_output"] = {**attested["skill_replay_output"], "value": {"ok": False}}
        with self.assertRaisesRegex(SkillReplayEvidenceError, "signature or binding"):
            self.store.record(
                tampered, tenant_id="tenant-a", workspace_id="workspace-a",
                mission_context=self.context, skill_binding=self.binding,
            )
        with self.assertRaisesRegex(SkillReplayEvidenceError, "tenant"):
            self.store.record(
                attested, tenant_id="tenant-b", workspace_id="workspace-a",
                mission_context=self.context, skill_binding=self.binding,
            )
        changed = dict(attested, result={**attested["result"], "execution_succeeded": False})
        with self.assertRaisesRegex(SkillReplayEvidenceError, "projection"):
            self.store.record(
                changed, tenant_id="tenant-a", workspace_id="workspace-a",
                mission_context=self.context, skill_binding=self.binding,
            )

    def test_evidence_id_is_immutable_and_duplicate_write_is_idempotent(self):
        request_id = str(uuid.uuid4())
        attested = self._attested(request_id=request_id)
        first = self.store.record(
            attested, tenant_id="tenant-a", workspace_id="workspace-a",
            mission_context=self.context, skill_binding=self.binding,
        )
        second = self.store.record(
            attested, tenant_id="tenant-a", workspace_id="workspace-a",
            mission_context=self.context, skill_binding=self.binding,
        )
        self.assertEqual(first, second)
        changed = self._attested(success=False, request_id=request_id)
        with self.assertRaisesRegex(SkillReplayEvidenceError, "different signed content"):
            self.store.record(
                changed, tenant_id="tenant-a", workspace_id="workspace-a",
                mission_context=self.context, skill_binding=self.binding,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
