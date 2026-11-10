"""Tests for independent Skill Validator policy and signature boundaries."""
import base64
import hashlib
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.execution_results import EXECUTION_RESULT_SCHEMA
from core.sandbox_broker_protocol import BROKER_RESPONSE_SCHEMA, SKILL_REPLAY_OUTPUT_SCHEMA, SKILL_REPLAY_PROFILE_ID
from core.skill_artifact_store import SkillArtifactStore, VALIDATION_ATTESTATION_SCHEMA
from core.skill_validator import (
    VALIDATION_REQUEST_SCHEMA, SkillValidatorError, SkillValidatorService,
    verify_validation_response,
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class SkillValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.broker_key = Ed25519PrivateKey.generate()
        self.validator_key = Ed25519PrivateKey.generate()
        self.context = {
            "tenant_id": "tenant-a", "mission_run_id": "mission-a",
            "node_id": "node-a", "task_id": "task-a",
        }
        self.binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill-demo", "skill_version": "1.0.0",
            "content_sha256": hashlib.sha256(b"skill-source").hexdigest(),
            "trust_level": "draft", "mission_context": self.context,
        }
        self.workspace_id = "workspace-a"
        self.policy = {
            "policy_id": "accept-demo-v1", "tenant_id": "tenant-a",
            "skill_id": "skill-demo", "skill_version": "1.0.0",
            "content_sha256": self.binding["content_sha256"], "trust_level": "verified",
            "checks": [
                {"type": "json_key_exists", "key_path": ["ok"]},
                {"type": "json_value_equals", "key_path": ["ok"], "expected": True},
                {"type": "json_value_type", "key_path": ["count"], "expected_type": "number"},
            ],
        }
        self.service = SkillValidatorService(
            validator_id="validator-independent", key_id="validator-key-1",
            signing_key=self.validator_key,
            broker_public_key=self.broker_key.public_key().public_bytes_raw(),
            broker_key_id="broker-key-1", workspace_ids=[self.workspace_id],
            policies=[self.policy],
        )
        self.broker_attestation = self._broker_attestation({"ok": True, "count": 3})
        self.request = {
            "schema_version": VALIDATION_REQUEST_SCHEMA, "request_id": str(uuid.uuid4()),
            "workspace_id": self.workspace_id, "mission_context": self.context,
            "skill_binding": self.binding, "trust_level": "verified",
            "broker_attestation": self.broker_attestation,
        }

    def tearDown(self):
        self.temp.cleanup()

    def _broker_attestation(self, output):
        request_id = str(uuid.uuid4())
        empty_hash = hashlib.sha256(b"").hexdigest()
        result = {
            "schema_version": EXECUTION_RESULT_SCHEMA,
            "runner": {"id": "test-runner", "version": "1.0"},
            "profile_id": SKILL_REPLAY_PROFILE_ID,
            "target": f"{self.binding['skill_id']}@{self.binding['skill_version']}",
            "exit_code": 0, "timed_out": False, "execution_succeeded": True,
            "stdout": {"bytes": 0, "available_bytes": 0, "capture_truncated": False, "sha256": empty_hash},
            "stderr": {"bytes": 0, "available_bytes": 0, "capture_truncated": False, "sha256": empty_hash},
        }
        replay_output = {
            "schema_version": SKILL_REPLAY_OUTPUT_SCHEMA,
            "success": True, "value": output, "error": None, "logs": "",
        }
        artifact = {
            "schema_version": "mission.skill-artifact-resolution.v1",
            "skill_id": self.binding["skill_id"],
            "skill_version": self.binding["skill_version"],
            "content_sha256": self.binding["content_sha256"],
            "trust_level": "draft",
        }
        signed = {
            "schema_version": BROKER_RESPONSE_SCHEMA, "request_id": request_id,
            "workspace_id": self.workspace_id, "mission_context": self.context,
            "skill_binding": self.binding, "skill_artifact": artifact,
            "skill_replay_output": replay_output, "result": result,
        }
        return {
            **signed,
            "signature": {
                "algorithm": "ed25519", "key_id": "broker-key-1",
                "value": base64.b64encode(self.broker_key.sign(_canonical(signed))).decode("ascii"),
            },
        }

    def test_issues_attestation_only_after_broker_signature_and_policy_pass(self):
        response = self.service.validate(self.request)
        self.assertEqual(response["schema_version"], "mission.skill-validation-response.v1")
        self.assertEqual(response["policy_id"], "accept-demo-v1")
        self.assertTrue(all(item["passed"] for item in response["checks"]))
        attestation = verify_validation_response(
            response, public_key=self.validator_key.public_key().public_bytes_raw(),
            expected_key_id="validator-key-1", expected_request_id=self.request["request_id"],
            expected_identity={
                "tenant_id": "tenant-a", "skill_id": "skill-demo",
                "skill_version": "1.0.0", "content_sha256": self.binding["content_sha256"],
                "trust_level": "verified",
            },
        )
        self.assertEqual(attestation["schema_version"], VALIDATION_ATTESTATION_SCHEMA)
        self.assertTrue(attestation["passed"])
        artifact_root = self.root / "artifacts"
        artifact_root.mkdir(mode=0o700)
        store = SkillArtifactStore(
            artifact_root,
            validator_public_key=self.validator_key.public_key().public_bytes_raw(),
            validator_key_id="validator-key-1",
        )
        identity = store.publish(
            tenant_id="tenant-a",
            skill=type("Skill", (), {
                "id": "skill-demo", "version": "1.0.0",
                "code": "def run(context): return {'ok': True, 'count': 3}",
                "trust_level": "verified",
            })(),
            validation_attestation=attestation,
        )
        self.assertEqual(identity["trust_level"], "verified")

    def test_rejects_forged_broker_signature(self):
        forged = dict(self.request, broker_attestation=dict(self.broker_attestation))
        forged["broker_attestation"]["signature"] = dict(forged["broker_attestation"]["signature"])
        forged["broker_attestation"]["signature"]["value"] = base64.b64encode(
            Ed25519PrivateKey.generate().sign(b"forged")
        ).decode("ascii")
        with self.assertRaisesRegex(SkillValidatorError, "Broker replay attestation"):
            self.service.validate(forged)

    def test_rejects_policy_failure_without_signing(self):
        request = dict(self.request, broker_attestation=self._broker_attestation({"ok": False, "count": 3}))
        with self.assertRaisesRegex(SkillValidatorError, "acceptance policy"):
            self.service.validate(request)

    def test_rejects_execution_success_without_required_business_output(self):
        request = dict(self.request, broker_attestation=self._broker_attestation({"count": 3}))
        with self.assertRaisesRegex(SkillValidatorError, "acceptance policy"):
            self.service.validate(request)

    def test_rejects_mismatched_tenant_or_skill_binding(self):
        request = dict(self.request, mission_context={**self.context, "tenant_id": "tenant-b"})
        with self.assertRaisesRegex(SkillValidatorError, "Mission context"):
            self.service.validate(request)
        request = dict(self.request, skill_binding={**self.binding, "skill_id": "other-skill"})
        with self.assertRaisesRegex(SkillValidatorError, "policy"):
            self.service.validate(request)

    def test_rejects_unconfigured_workspace_and_missing_policy(self):
        request = dict(self.request, workspace_id="other-workspace")
        with self.assertRaisesRegex(SkillValidatorError, "workspace_id"):
            self.service.validate(request)
        request = dict(self.request, trust_level="cloud")
        with self.assertRaisesRegex(SkillValidatorError, "policy"):
            self.service.validate(request)

    def test_rejects_failed_broker_execution(self):
        failed = self._broker_attestation({"ok": True, "count": 3})
        failed["result"]["execution_succeeded"] = False
        failed["result"]["exit_code"] = 1
        signed = {key: value for key, value in failed.items() if key != "signature"}
        failed["signature"]["value"] = base64.b64encode(self.broker_key.sign(_canonical(signed))).decode("ascii")
        request = dict(self.request, broker_attestation=failed)
        with self.assertRaisesRegex(SkillValidatorError, "did not succeed"):
            self.service.validate(request)

    def test_rejects_duplicate_policies_and_non_json_expected_values(self):
        with self.assertRaisesRegex(SkillValidatorError, "duplicate"):
            SkillValidatorService(
                validator_id="validator-independent", key_id="validator-key-1",
                signing_key=self.validator_key,
                broker_public_key=self.broker_key.public_key().public_bytes_raw(),
                broker_key_id="broker-key-1", workspace_ids=[self.workspace_id],
                policies=[self.policy, self.policy],
            )
        bad = dict(self.policy, checks=[{
            "type": "json_value_equals", "key_path": ["ok"], "expected": float("nan"),
        }])
        with self.assertRaisesRegex(SkillValidatorError, "strict JSON"):
            SkillValidatorService(
                validator_id="validator-independent", key_id="validator-key-1",
                signing_key=self.validator_key,
                broker_public_key=self.broker_key.public_key().public_bytes_raw(),
                broker_key_id="broker-key-1", workspace_ids=[self.workspace_id],
                policies=[bad],
            )


if __name__ == "__main__":
    unittest.main()
