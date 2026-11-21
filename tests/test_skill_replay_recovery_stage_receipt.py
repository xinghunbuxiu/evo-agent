"""Recovery verification of the signed Broker candidate-stage receipt."""
import base64
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from admin.skill_replay_runtime import SkillReplayRuntime
from core.sandbox_broker_protocol import (
    SKILL_CANDIDATE_ARTIFACT_SCHEMA,
    SKILL_CANDIDATE_STAGE_RESPONSE_SCHEMA,
)


class SkillReplayStageReceiptRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.runtime = SkillReplayRuntime.__new__(SkillReplayRuntime)
        self.runtime.workspace_id = "workspace-a"
        self.runtime.broker_public_key = self.private_key.public_key().public_bytes_raw()
        self.runtime.broker_key_id = "broker-key-a"
        self.context = {
            "tenant_id": "tenant-a",
            "mission_run_id": "mission-a",
            "node_id": "node-a",
            "task_id": "task-a",
        }
        self.binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill-a",
            "skill_version": "1.2.3",
            "content_sha256": "a" * 64,
            "trust_level": "draft",
            "mission_context": self.context,
        }
        self.stage_request_id = "11111111-1111-4111-8111-111111111111"

    def _signed_stage_receipt(self):
        payload = {
            "schema_version": SKILL_CANDIDATE_STAGE_RESPONSE_SCHEMA,
            "request_id": self.stage_request_id,
            "workspace_id": self.runtime.workspace_id,
            "mission_context": self.context,
            "candidate_artifact": {
                "schema_version": SKILL_CANDIDATE_ARTIFACT_SCHEMA,
                "tenant_id": self.context["tenant_id"],
                "skill_id": self.binding["skill_id"],
                "skill_version": self.binding["skill_version"],
                "content_sha256": self.binding["content_sha256"],
                "trust_level": "draft",
            },
        }
        signature = self.private_key.sign(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8"))
        return {
            **payload,
            "signature": {
                "algorithm": "ed25519",
                "key_id": self.runtime.broker_key_id,
                "value": base64.b64encode(signature).decode("ascii"),
            },
        }

    def _verify(self, receipt):
        return self.runtime.verify_recovery_responses(
            mission_context=self.context,
            skill_binding=self.binding,
            execution_request_id="22222222-2222-4222-8222-222222222222",
            validation_request_id=None,
            promotion_request_id=None,
            stage_request_id=self.stage_request_id,
            broker_outcomes={
                "stage": {"status": "completed", "response": receipt},
            },
            validator_outcome={},
        )

    def test_valid_stage_receipt_is_cryptographically_verified(self):
        result = self._verify(self._signed_stage_receipt())
        self.assertEqual(result["broker_stage"], "verified")

    def test_stage_receipt_with_changed_candidate_digest_is_invalid(self):
        receipt = self._signed_stage_receipt()
        receipt["candidate_artifact"]["content_sha256"] = "b" * 64
        result = self._verify(receipt)
        self.assertEqual(result["broker_stage"], "invalid")

    def test_stage_receipt_signed_by_untrusted_key_is_invalid(self):
        receipt = self._signed_stage_receipt()
        other_key = Ed25519PrivateKey.generate()
        payload = {key: value for key, value in receipt.items() if key != "signature"}
        signature = other_key.sign(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8"))
        receipt["signature"]["value"] = base64.b64encode(signature).decode("ascii")
        result = self._verify(receipt)
        self.assertEqual(result["broker_stage"], "invalid")

    def test_completed_stage_without_pinned_request_id_is_invalid(self):
        receipt = self._signed_stage_receipt()
        result = self.runtime.verify_recovery_responses(
            mission_context=self.context,
            skill_binding=self.binding,
            execution_request_id="22222222-2222-4222-8222-222222222222",
            validation_request_id=None,
            broker_outcomes={"stage": {"status": "completed", "response": receipt}},
            validator_outcome={},
        )
        self.assertEqual(result["broker_stage"], "invalid")


if __name__ == "__main__":
    unittest.main()
