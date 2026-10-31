"""Tests for the path-free sandbox broker request and attestation contract."""
import base64
from dataclasses import replace
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.execution_profiles import resolve_execution_profile
from core.sandbox_broker_protocol import (
    BROKER_RESPONSE_SCHEMA,
    build_broker_request,
    verify_broker_response,
)


class SandboxBrokerProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        (self.workspace / "tests").mkdir()
        (self.workspace / "tests" / "test_sample.py").write_text(
            "def test_sample():\n    assert True\n", encoding="utf-8"
        )
        self.spec = resolve_execution_profile(self.workspace, {
            "profile_id": "python.pytest",
            "target": "tests/test_sample.py",
        })
        self.request_id = str(uuid.uuid4())
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def tearDown(self):
        self.temp.cleanup()

    def _signed_response(self, result=None):
        result = result or {
            "schema_version": "mission.execution-result.v1",
            "runner": {"id": "root-broker", "version": "1"},
            "profile_id": "python.pytest",
            "target": "tests/test_sample.py",
            "exit_code": 0,
            "timed_out": False,
            "execution_succeeded": True,
            "stdout": {"bytes": 0, "sha256": "0" * 64},
            "stderr": {"bytes": 0, "sha256": "0" * 64},
        }
        payload = {
            "schema_version": BROKER_RESPONSE_SCHEMA,
            "request_id": self.request_id,
            "workspace_id": "project-evo-os",
            "result": result,
        }
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        return {
            **payload,
            "signature": {
                "algorithm": "ed25519",
                "key_id": "broker-key-2026-01",
                "value": base64.b64encode(self.private_key.sign(canonical)).decode("ascii"),
            },
        }

    def test_request_contains_only_opaque_workspace_and_allowlisted_intent(self):
        request = build_broker_request(
            "project-evo-os", self.spec, request_id=self.request_id,
        )
        self.assertEqual(request["workspace_id"], "project-evo-os")
        self.assertEqual(request["profile_id"], "python.pytest")
        self.assertEqual(request["target"], "tests/test_sample.py")
        self.assertNotIn("cwd", request)
        self.assertNotIn("argv", request)
        self.assertNotIn("workspace_path", request)
        self.assertEqual(
            set(request),
            {"schema_version", "request_id", "workspace_id", "profile_id", "target", "timeout_seconds"},
        )

    def test_rejects_unsafe_profile_targets_even_if_spec_is_forged(self):
        for target in ("../escape.py", "/etc/passwd", "tests\\\\escape.py", "tests/../escape.py"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                build_broker_request("project-evo-os", replace(self.spec, target=target))

    def test_rejects_path_like_or_invalid_workspace_identifiers(self):
        for value in ("../workspace", "/tmp/workspace", "a/b", "", " "):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_broker_request(value, self.spec)

    def test_verifies_ed25519_attestation(self):
        response = self._signed_response()
        result = verify_broker_response(
            response,
            public_key=self.public_key,
            expected_key_id="broker-key-2026-01",
            expected_request_id=self.request_id,
            expected_workspace_id="project-evo-os",
            expected_profile_id="python.pytest",
            expected_target="tests/test_sample.py",
        )
        self.assertTrue(result["execution_succeeded"])

    def test_rejects_tampering_wrong_key_and_wrong_request(self):
        response = self._signed_response()
        changed = dict(response)
        changed["result"] = dict(response["result"], execution_succeeded=False)
        for candidate, key, request_id in (
            (changed, self.public_key, self.request_id),
            (response, self.public_key, str(uuid.uuid4())),
            (response, Ed25519PrivateKey.generate().public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            ), self.request_id),
        ):
            with self.subTest(candidate=candidate, request_id=request_id), self.assertRaises(ValueError):
                verify_broker_response(
                    candidate, public_key=key,
                    expected_key_id="broker-key-2026-01",
                    expected_request_id=request_id,
                    expected_workspace_id="project-evo-os",
                    expected_profile_id="python.pytest",
                    expected_target="tests/test_sample.py",
                )

    def test_rejects_unknown_signature_key_id_and_extra_fields(self):
        response = self._signed_response()
        response["signature"] = dict(response["signature"], key_id="attacker-key")
        with self.assertRaisesRegex(ValueError, "key ID"):
            verify_broker_response(
                response, public_key=self.public_key,
                expected_key_id="broker-key-2026-01",
                expected_request_id=self.request_id,
                expected_workspace_id="project-evo-os",
                expected_profile_id="python.pytest",
                expected_target="tests/test_sample.py",
            )
        response = self._signed_response()
        response["caller_command"] = "rm -rf /"
        with self.assertRaisesRegex(ValueError, "unsupported or missing"):
            verify_broker_response(
                response, public_key=self.public_key,
                expected_key_id="broker-key-2026-01",
                expected_request_id=self.request_id,
                expected_workspace_id="project-evo-os",
                expected_profile_id="python.pytest",
                expected_target="tests/test_sample.py",
            )

    def test_rejects_response_from_another_workspace(self):
        response = self._signed_response()
        response["workspace_id"] = "other-workspace"
        with self.assertRaisesRegex(ValueError, "workspace_id"):
            verify_broker_response(
                response, public_key=self.public_key,
                expected_key_id="broker-key-2026-01",
                expected_request_id=self.request_id,
                expected_workspace_id="project-evo-os",
                expected_profile_id="python.pytest",
                expected_target="tests/test_sample.py",
            )

    def test_rejects_signed_result_for_different_target(self):
        result = self._signed_response()["result"]
        result["target"] = "tests/other.py"
        response = self._signed_response(result=result)
        with self.assertRaisesRegex(ValueError, "does not match"):
            verify_broker_response(
                response, public_key=self.public_key,
                expected_key_id="broker-key-2026-01",
                expected_request_id=self.request_id,
                expected_workspace_id="project-evo-os",
                expected_profile_id="python.pytest",
                expected_target="tests/test_sample.py",
            )


if __name__ == "__main__":
    unittest.main()
