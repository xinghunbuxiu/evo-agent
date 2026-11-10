
"""End-to-end Mission adapter tests for signed Skill Replay evidence projection."""
import base64
import hashlib
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.sandbox_broker_protocol import (
    BROKER_RESPONSE_SCHEMA, SKILL_ARTIFACT_RESOLUTION_SCHEMA,
    SKILL_REPLAY_OUTPUT_SCHEMA, SKILL_REPLAY_PROFILE_ID,
)
from core.skill_replay_evidence_store import SkillReplayEvidenceStore
from core.skill_replay_mission import SkillReplayMissionAdapter
from core.learning import ExperienceStore


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class SkillReplayMissionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.broker_key = Ed25519PrivateKey.generate()
        self.context = {
            "tenant_id": "tenant-a", "mission_run_id": "mission-1",
            "node_id": "node-1", "task_id": "task-1",
        }
        self.binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill-demo", "skill_version": "1.0.0",
            "content_sha256": hashlib.sha256(b"def run(context): return {}").hexdigest(),
            "trust_level": "verified", "mission_context": self.context,
        }
        evidence_root = self.root / "evidence"
        evidence_root.mkdir(mode=0o700)
        self.evidence_store = SkillReplayEvidenceStore(
            evidence_root, broker_public_key=self.broker_key.public_key().public_bytes_raw(),
            broker_key_id="broker-test-key",
        )
        self.adapter = SkillReplayMissionAdapter(
            socket_path="/run/evo-sandbox-broker.sock", workspace_id="workspace-a",
            broker_public_key=self.broker_key.public_key().public_bytes_raw(),
            broker_key_id="broker-test-key", evidence_store=self.evidence_store,
            experience_workspace=self.root / "workspace",
        )
        self.spec = SimpleNamespace(
            profile_id=SKILL_REPLAY_PROFILE_ID, target="skill-demo@1.0.0",
            timeout_seconds=30,
        )

    def tearDown(self):
        self.temp.cleanup()

    def _attested(self, *, success=True):
        request_id = str(uuid.uuid4())
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
            "value": {"task_id": "task-1"} if success else None,
            "error": None if success else {"type": "AssertionError", "message": "expected true"},
            "logs": "",
        }
        payload = {
            "schema_version": BROKER_RESPONSE_SCHEMA, "request_id": request_id,
            "workspace_id": "workspace-a", "mission_context": self.context,
            "skill_binding": self.binding,
            "skill_artifact": {
                "schema_version": SKILL_ARTIFACT_RESOLUTION_SCHEMA,
                "skill_id": self.binding["skill_id"],
                "skill_version": self.binding["skill_version"],
                "content_sha256": self.binding["content_sha256"],
                "trust_level": self.binding["trust_level"],
            },
            "skill_replay_output": output, "result": result,
        }
        envelope = {
            **payload,
            "signature": {
                "algorithm": "ed25519", "key_id": "broker-test-key",
                "value": base64.b64encode(self.broker_key.sign(_canonical(payload))).decode("ascii"),
            },
        }
        return {
            "schema_version": "mission.sandbox-broker-attestation.v1",
            "attestation": envelope, "result": result, "skill_replay_output": output,
        }

    @mock.patch("core.skill_replay_mission.execute_via_broker_attested")
    def test_persists_broker_attestation_then_projects_pending_experience(self, execute):
        execute.return_value = self._attested()
        result = self.adapter.execute(
            self.spec, tenant_id="tenant-a", mission_context=self.context,
            skill_binding=self.binding, domain="python", task_type="skill_replay",
            input_summary="Replay skill-demo@1.0.0",
        )
        execute.assert_called_once()
        self.assertEqual(result["schema_version"], "mission.skill-replay-result.v1")
        self.assertEqual(result["experience"]["reflection_status"], "pending")
        self.assertEqual(result["experience"]["execution_status"], "succeeded")
        stored = self.evidence_store.load_verified(
            tenant_id="tenant-a", evidence_id=result["evidence"]["evidence_id"],
        )
        self.assertEqual(stored["mission_context"], self.context)
        experiences = ExperienceStore(self.root / "workspace", "tenant-a").load_by_domain("python")
        self.assertEqual(len(experiences), 1)
        self.assertEqual(experiences[0].metadata["skill_replay"]["evidence_sha256"], result["evidence"]["sha256"])
        self.assertIsNone(experiences[0].metadata["skill_replay"]["reflection"]["reusable_experience"])

    @mock.patch("core.skill_replay_mission.execute_via_broker_attested")
    def test_signed_failed_replay_is_recorded_with_real_error_not_success(self, execute):
        execute.return_value = self._attested(success=False)
        result = self.adapter.execute(
            self.spec, tenant_id="tenant-a", mission_context=self.context,
            skill_binding=self.binding, domain="python", task_type="skill_replay",
            input_summary="Failing replay",
        )
        self.assertFalse(result["result"]["execution_succeeded"])
        self.assertEqual(result["experience"]["execution_status"], "failed")
        exp = ExperienceStore(self.root / "workspace", "tenant-a").load_by_domain("python")[0]
        replay = exp.metadata["skill_replay"]
        self.assertEqual(replay["failure"]["type"], "AssertionError")
        self.assertEqual(replay["reflection"]["error_reason"]["message"], "expected true")
        self.assertEqual(replay["reflection"]["status"], "pending")

    @mock.patch("core.skill_replay_mission.execute_via_broker_attested")
    def test_tenant_mismatch_is_rejected_before_broker_call(self, execute):
        with self.assertRaisesRegex(ValueError, "does not match Mission context"):
            self.adapter.execute(
                self.spec, tenant_id="tenant-other", mission_context=self.context,
                skill_binding=self.binding, domain="python", task_type="skill_replay",
                input_summary="must not execute",
            )
        execute.assert_not_called()

    @mock.patch("core.skill_replay_mission.execute_via_broker_attested")
    def test_generic_test_runner_profile_cannot_be_used_for_skill_replay(self, execute):
        generic = SimpleNamespace(profile_id="python.pytest", target="tests/test_demo.py", timeout_seconds=30)
        with self.assertRaisesRegex(ValueError, "dedicated replay profile"):
            self.adapter.execute(
                generic, tenant_id="tenant-a", mission_context=self.context,
                skill_binding=self.binding, domain="python", task_type="skill_replay",
                input_summary="must not execute",
            )
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
