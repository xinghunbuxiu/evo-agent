"""Validator v2 policies and signed attestations pin the Manifest digest."""
from __future__ import annotations

import base64
import hashlib
import unittest
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.execution_profiles import ExecutionProfileSpec, MAX_OUTPUT_BYTES
from core.execution_results import build_execution_result
from core.sandbox_broker_protocol import (
    BROKER_MANIFEST_RESPONSE_SCHEMA,
    SKILL_MANIFEST_ARTIFACT_RESOLUTION_SCHEMA,
    SKILL_REPLAY_MANIFEST_BINDING_SCHEMA,
    SKILL_REPLAY_OUTPUT_SCHEMA,
    _canonical_json,
)
from core.skill_validator import (
    VALIDATION_ATTESTATION_SCHEMA_V2,
    VALIDATION_REQUEST_SCHEMA_V2,
    SkillValidatorError,
    SkillValidatorService,
    verify_validation_response,
)


class ValidatorManifestV2Tests(unittest.TestCase):
    def _broker_receipt(self, broker_key, context, binding, request_id):
        spec = ExecutionProfileSpec(
            profile_id="skill.replay.python.v1",
            target=f"{binding['skill_id']}@{binding['skill_version']}",
            argv=(), cwd=Path("/tmp"), timeout_seconds=30,
            max_output_bytes=MAX_OUTPUT_BYTES, network_access=False,
        )
        result = build_execution_result(
            spec, runner_id="test-broker", runner_version="1",
            exit_code=0, stdout=b"", stderr=b"", timed_out=False,
            stdout_available_bytes=0, stderr_available_bytes=0,
        )
        replay_output = {
            "schema_version": SKILL_REPLAY_OUTPUT_SCHEMA,
            "success": True, "value": {"ok": True}, "error": None, "logs": "",
        }
        artifact = {
            "schema_version": SKILL_MANIFEST_ARTIFACT_RESOLUTION_SCHEMA,
            "skill_id": binding["skill_id"],
            "skill_version": binding["skill_version"],
            "content_sha256": binding["content_sha256"],
            "manifest_sha256": binding["manifest_sha256"],
            "trust_level": "draft",
        }
        payload = {
            "schema_version": BROKER_MANIFEST_RESPONSE_SCHEMA,
            "request_id": request_id,
            "workspace_id": "validator-workspace",
            "mission_context": context,
            "skill_binding": binding,
            "skill_artifact": artifact,
            "skill_replay_output": replay_output,
            "result": result,
        }
        signature = broker_key.sign(_canonical_json(payload))
        return {
            **payload,
            "signature": {
                "algorithm": "ed25519", "key_id": "broker-v2-key",
                "value": base64.b64encode(signature).decode("ascii"),
            },
        }

    def test_manifest_v2_policy_and_attestation_bind_both_digests(self):
        broker_key = Ed25519PrivateKey.generate()
        validator_key = Ed25519PrivateKey.generate()
        context = {
            "tenant_id": "tenant-v2", "mission_run_id": "mission-v2",
            "node_id": "node-v2", "task_id": "task-v2",
        }
        binding = {
            "schema_version": SKILL_REPLAY_MANIFEST_BINDING_SCHEMA,
            "skill_id": "skill-v2", "skill_version": "2.0.0",
            "content_sha256": hashlib.sha256(b"source").hexdigest(),
            "manifest_sha256": hashlib.sha256(b"canonical-manifest").hexdigest(),
            "trust_level": "draft", "mission_context": context,
        }
        broker_request_id = "11111111-1111-4111-8111-111111111111"
        validation_request_id = "22222222-2222-4222-8222-222222222222"
        receipt = self._broker_receipt(broker_key, context, binding, broker_request_id)
        service = SkillValidatorService(
            validator_id="independent-validator-v2",
            key_id="validator-v2-key", signing_key=validator_key,
            broker_public_key=broker_key.public_key().public_bytes_raw(),
            broker_key_id="broker-v2-key", workspace_ids=["validator-workspace"],
            manifest_policies=[{
                "policy_id": "skill-v2-acceptance",
                "tenant_id": context["tenant_id"],
                "skill_id": binding["skill_id"],
                "skill_version": binding["skill_version"],
                "content_sha256": binding["content_sha256"],
                "manifest_sha256": binding["manifest_sha256"],
                "trust_level": "verified",
                "checks": [{
                    "type": "json_value_equals", "key_path": ["ok"], "expected": True,
                }],
            }],
        )
        request = {
            "schema_version": VALIDATION_REQUEST_SCHEMA_V2,
            "request_id": validation_request_id,
            "workspace_id": "validator-workspace",
            "mission_context": context,
            "skill_binding": binding,
            "trust_level": "verified",
            "broker_attestation": receipt,
        }
        response = service.validate(request)
        self.assertEqual(response["schema_version"], "mission.skill-validation-response.v2")
        attestation = response["attestation"]
        self.assertEqual(attestation["schema_version"], VALIDATION_ATTESTATION_SCHEMA_V2)
        self.assertEqual(attestation["content_sha256"], binding["content_sha256"])
        self.assertEqual(attestation["manifest_sha256"], binding["manifest_sha256"])
        self.assertTrue(attestation["passed"])
        verified = verify_validation_response(
            response,
            public_key=validator_key.public_key().public_bytes_raw(),
            expected_key_id="validator-v2-key",
            expected_request_id=validation_request_id,
            expected_identity={
                "workspace_id": "validator-workspace",
                **context,
                "broker_request_id": broker_request_id,
                "broker_attestation_sha256": hashlib.sha256(
                    _canonical_json(receipt)
                ).hexdigest(),
                "skill_id": binding["skill_id"],
                "skill_version": binding["skill_version"],
                "content_sha256": binding["content_sha256"],
                "manifest_sha256": binding["manifest_sha256"],
                "trust_level": "verified",
            },
        )
        self.assertEqual(verified["validation_id"], attestation["validation_id"])

    def test_v1_policy_cannot_authorize_manifest_v2_binding(self):
        broker_key = Ed25519PrivateKey.generate()
        validator_key = Ed25519PrivateKey.generate()
        context = {
            "tenant_id": "tenant-v2", "mission_run_id": "mission-v2",
            "node_id": "node-v2", "task_id": "task-v2",
        }
        binding = {
            "schema_version": SKILL_REPLAY_MANIFEST_BINDING_SCHEMA,
            "skill_id": "skill-v2", "skill_version": "2.0.0",
            "content_sha256": "a" * 64, "manifest_sha256": "b" * 64,
            "trust_level": "draft", "mission_context": context,
        }
        broker_request_id = "33333333-3333-4333-8333-333333333333"
        receipt = self._broker_receipt(broker_key, context, binding, broker_request_id)
        service = SkillValidatorService(
            validator_id="independent-validator-v1",
            key_id="validator-v1-key", signing_key=validator_key,
            broker_public_key=broker_key.public_key().public_bytes_raw(),
            broker_key_id="broker-v2-key", workspace_ids=["validator-workspace"],
            policies=[{
                "policy_id": "legacy-policy", "tenant_id": context["tenant_id"],
                "skill_id": binding["skill_id"], "skill_version": binding["skill_version"],
                "content_sha256": binding["content_sha256"], "trust_level": "verified",
                "checks": [{"type": "json_key_exists", "key_path": ["ok"]}],
            }],
        )
        with self.assertRaises(SkillValidatorError):
            service.validate({
                "schema_version": VALIDATION_REQUEST_SCHEMA_V2,
                "request_id": str(uuid.uuid4()),
                "workspace_id": "validator-workspace",
                "mission_context": context,
                "skill_binding": binding, "trust_level": "verified",
                "broker_attestation": receipt,
            })


if __name__ == "__main__":
    unittest.main()
