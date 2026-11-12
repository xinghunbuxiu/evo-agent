"""Tests for independent Skill Validator policy and signature boundaries."""
import base64
import hashlib
import json
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.execution_results import EXECUTION_RESULT_SCHEMA
from core.sandbox_broker_protocol import (
    BROKER_RESPONSE_SCHEMA, SKILL_REPLAY_OUTPUT_SCHEMA, SKILL_REPLAY_PROFILE_ID,
    broker_response_sha256,
)
from core.skill_artifact_store import SkillArtifactStore, VALIDATION_ATTESTATION_SCHEMA
from core.skill_validator import (
    VALIDATION_REQUEST_SCHEMA, SkillValidatorError, SkillValidatorRequestStore,
    SkillValidatorService, verify_validation_response,
)
from core.skill_validator_transport import (
    request_skill_validation, request_skill_validator_status,
    serve_validator_listener, SkillValidatorTransportError,
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
        self.source_code = "def run(context): return {'ok': True, 'count': 3}"
        self.binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill-demo", "skill_version": "1.0.0",
            "content_sha256": hashlib.sha256(self.source_code.encode("utf-8")).hexdigest(),
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
        self.request_store_path = self.root / "validator-state" / "requests.sqlite3"
        self.request_store_path.parent.mkdir(mode=0o700)
        self.request_store = SkillValidatorRequestStore(self.request_store_path)
        self.service = SkillValidatorService(
            validator_id="validator-independent", key_id="validator-key-1",
            signing_key=self.validator_key,
            broker_public_key=self.broker_key.public_key().public_bytes_raw(),
            broker_key_id="broker-key-1", workspace_ids=[self.workspace_id],
            policies=[self.policy], request_store=self.request_store,
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

    def _expected_identity(self):
        return {
            "workspace_id": self.workspace_id,
            "tenant_id": self.context["tenant_id"],
            "mission_run_id": self.context["mission_run_id"],
            "node_id": self.context["node_id"],
            "task_id": self.context["task_id"],
            "broker_request_id": self.broker_attestation["request_id"],
            "broker_attestation_sha256": broker_response_sha256(self.broker_attestation),
            "skill_id": self.binding["skill_id"],
            "skill_version": self.binding["skill_version"],
            "content_sha256": self.binding["content_sha256"],
            "trust_level": "verified",
        }

    def test_issues_attestation_only_after_broker_signature_and_policy_pass(self):
        response = self.service.validate(self.request)
        self.assertEqual(response["schema_version"], "mission.skill-validation-response.v1")
        self.assertEqual(response["policy_id"], "accept-demo-v1")
        self.assertTrue(all(item["passed"] for item in response["checks"]))
        attestation = verify_validation_response(
            response, public_key=self.validator_key.public_key().public_bytes_raw(),
            expected_key_id="validator-key-1", expected_request_id=self.request["request_id"],
            expected_identity=self._expected_identity(),
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
                "code": self.source_code,
                "trust_level": "verified",
            })(),
            validation_attestation=attestation,
            workspace_id=self.workspace_id,
            mission_context=self.context,
            broker_request_id=self.broker_attestation["request_id"],
            broker_attestation_sha256=broker_response_sha256(self.broker_attestation),
        )
        self.assertEqual(identity["trust_level"], "verified")

    def test_validator_attestation_binds_exact_broker_envelope_and_check_results(self):
        response = self.service.validate(self.request)
        attestation = response["attestation"]
        self.assertEqual(attestation["broker_request_id"], self.broker_attestation["request_id"])
        self.assertEqual(attestation["broker_attestation_sha256"], broker_response_sha256(self.broker_attestation))
        tampered = dict(response)
        tampered["checks"] = [dict(item) for item in response["checks"]]
        tampered["checks"][0]["type"] = "json_value_type"
        with self.assertRaisesRegex(SkillValidatorError, "check results"):
            verify_validation_response(
                tampered, public_key=self.validator_key.public_key().public_bytes_raw(),
                expected_key_id="validator-key-1", expected_request_id=self.request["request_id"],
                expected_identity=self._expected_identity(),
            )

    def test_unix_socket_transport_returns_a_client_verified_attestation(self):
        socket_path = self.root / "validator.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(4)
        stop = threading.Event()
        thread = threading.Thread(
            target=serve_validator_listener,
            kwargs={
                "listener": listener,
                "service": self.service,
                "allowed_uids": [os.getuid()],
                "stop_event": stop,
                "max_workers": 1,
            },
            daemon=True,
        )
        thread.start()
        try:
            attestation = request_skill_validation(
                str(socket_path),
                request=self.request,
                validator_public_key=self.validator_key.public_key().public_bytes_raw(),
                expected_key_id="validator-key-1",
                expected_identity=self._expected_identity(),
            )
            self.assertEqual(attestation["validator_id"], "validator-independent")
            self.assertTrue(attestation["passed"])
        finally:
            stop.set()
            thread.join(timeout=2)
            listener.close()
            socket_path.unlink(missing_ok=True)



    def test_validator_replay_database_and_wal_files_are_private(self):
        self.assertEqual(self.request_store_path.stat().st_mode & 0o777, 0o600)
        connection = sqlite3.connect(self.request_store_path)
        try:
            connection.execute("INSERT INTO validator_requests(request_id, request_digest) VALUES (?, ?)",
                               (str(uuid.uuid4()), "a" * 64))
        finally:
            connection.close()
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.request_store_path) + suffix)
            if path.exists():
                self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_same_validation_request_returns_exact_signed_attestation(self):
        first = self.service.validate(self.request)
        second = self.service.validate(self.request)
        self.assertEqual(second, first)
        self.assertEqual(second["attestation"]["validation_id"], first["attestation"]["validation_id"])
        self.assertEqual(second["attestation"]["signature"], first["attestation"]["signature"])

    def test_completed_validation_response_survives_validator_restart(self):
        first = self.service.validate(self.request)
        restarted_store = SkillValidatorRequestStore(self.request_store_path)
        restarted = SkillValidatorService(
            validator_id="validator-independent", key_id="validator-key-1",
            signing_key=self.validator_key,
            broker_public_key=self.broker_key.public_key().public_bytes_raw(),
            broker_key_id="broker-key-1", workspace_ids=[self.workspace_id],
            policies=[self.policy], request_store=restarted_store,
        )
        self.assertEqual(restarted.validate(self.request), first)

    def test_incomplete_validation_claim_is_indeterminate_and_not_reexecuted(self):
        request_id = str(uuid.uuid4())
        request = dict(self.request, request_id=request_id)
        self.request_store.claim(request_id, request)
        with self.assertRaisesRegex(SkillValidatorError, "indeterminate"):
            self.service.validate(request)

    def test_validation_request_id_cannot_be_reused_for_different_digest(self):
        self.request_store.claim(self.request["request_id"], self.request)
        changed = dict(self.request, trust_level="cloud")
        with self.assertRaisesRegex(SkillValidatorError, "different digest"):
            self.request_store.claim(self.request["request_id"], changed)

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
        # A changed validation payload is a new immutable request and needs a new ID.
        request = dict(
            self.request, request_id=str(uuid.uuid4()),
            mission_context={**self.context, "tenant_id": "tenant-b"},
        )
        with self.assertRaisesRegex(SkillValidatorError, "Mission context"):
            self.service.validate(request)
        request = dict(
            self.request, request_id=str(uuid.uuid4()),
            skill_binding={**self.binding, "skill_id": "other-skill"},
        )
        with self.assertRaisesRegex(SkillValidatorError, "policy"):
            self.service.validate(request)

    def test_rejects_unconfigured_workspace_and_missing_policy(self):
        # Keep distinct negative cases separate in the durable idempotency ledger.
        request = dict(
            self.request, request_id=str(uuid.uuid4()),
            workspace_id="other-workspace",
        )
        with self.assertRaisesRegex(SkillValidatorError, "workspace_id"):
            self.service.validate(request)
        request = dict(
            self.request, request_id=str(uuid.uuid4()), trust_level="cloud",
        )
        with self.assertRaisesRegex(SkillValidatorError, "policy"):
            self.service.validate(request)

    def test_rejects_failed_broker_execution(self):
        failed = self._broker_attestation({"ok": True, "count": 3})
        failed["result"]["execution_succeeded"] = False
        failed["result"]["exit_code"] = 1
        failed["skill_replay_output"]["success"] = False
        failed["skill_replay_output"]["value"] = None
        failed["skill_replay_output"]["error"] = {"type": "RuntimeError", "message": "replay failed"}
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


    def test_validator_replay_lookup_is_scoped_to_mission_identity(self):
        request_id=self.request["request_id"]
        self.request_store.claim(request_id,self.request)
        self.assertEqual(self.request_store.lookup(request_id,workspace_id=self.workspace_id,mission_context=self.context),{"status":"indeterminate"})
        with self.assertRaisesRegex(SkillValidatorError,"not available"):
            self.request_store.lookup(request_id,workspace_id=self.workspace_id,mission_context={**self.context,"tenant_id":"tenant-other"})
        self.assertEqual(self.request_store.lookup(str(uuid.uuid4()),workspace_id=self.workspace_id,mission_context=self.context),{"status":"not_found"})

    def test_completed_validator_lookup_returns_exact_cached_response(self):
        response=self.service.validate(self.request)
        self.assertEqual(self.request_store.lookup(self.request["request_id"],workspace_id=self.workspace_id,mission_context=self.context),{"status":"completed","response":response})


    def test_validator_status_round_trips_over_authenticated_unix_socket(self):
        completed = self.service.validate(self.request)
        pending_id = str(uuid.uuid4())
        self.request_store.claim(pending_id, {**self.request, "request_id": pending_id})
        socket_path = self.root / "validator-status.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(8)
        stop = threading.Event()
        thread = threading.Thread(target=serve_validator_listener, kwargs={
            "listener": listener, "service": self.service,
            "allowed_uids": [os.getuid()], "stop_event": stop, "max_workers": 1,
        }, daemon=True)
        thread.start()
        try:
            status = request_skill_validator_status(
                str(socket_path), request_id=self.request["request_id"],
                workspace_id=self.workspace_id, mission_context=self.context,
            )
            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["response"], completed)
            pending = request_skill_validator_status(
                str(socket_path), request_id=pending_id,
                workspace_id=self.workspace_id, mission_context=self.context,
            )
            self.assertEqual(pending["status"], "indeterminate")
            missing = request_skill_validator_status(
                str(socket_path), request_id=str(uuid.uuid4()),
                workspace_id=self.workspace_id, mission_context=self.context,
            )
            self.assertEqual(missing["status"], "not_found")
            with self.assertRaises(SkillValidatorTransportError):
                request_skill_validator_status(
                    str(socket_path), request_id=self.request["request_id"],
                    workspace_id=self.workspace_id,
                    mission_context={**self.context, "tenant_id": "tenant-other"},
                )
        finally:
            stop.set()
            thread.join(timeout=2)
            listener.close()
            socket_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
