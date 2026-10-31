"""Tests for broker-side request policy, replay prevention, and signing."""
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.sandbox_broker import (
    BrokerReplayStore,
    BrokerRequestRejected,
    SandboxBrokerService,
    validate_broker_request,
)
from core.sandbox_broker_protocol import build_broker_request, verify_broker_response
from core.sandbox_runner import RunnerProcessOutput
from core.execution_profiles import resolve_execution_profile


class SandboxBrokerServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "workspace"
        (self.root / "tests").mkdir(parents=True)
        (self.root / "tests" / "test_sample.py").write_text(
            "def test_sample():\n    assert True\n", encoding="utf-8"
        )
        self.db = Path(self.temp.name) / "broker" / "replay.sqlite3"
        self.store = BrokerReplayStore(self.db)
        self.key = Ed25519PrivateKey.generate()
        self.calls = []
        self.service = SandboxBrokerService(
            workspace_roots={"project-test": self.root},
            replay_store=self.store,
            executor=self._execute,
            signing_key=self.key,
            key_id="broker-test-key",
        )
        self.spec = resolve_execution_profile(self.root, {
            "profile_id": "python.pytest", "target": "tests/test_sample.py",
        })
        self.request_id = str(uuid.uuid4())
        self.request = build_broker_request(
            "project-test", self.spec, request_id=self.request_id,
        )

    def tearDown(self):
        self.temp.cleanup()

    def _execute(self, spec):
        self.calls.append(spec)
        return RunnerProcessOutput(exit_code=0, stdout=b"ok", stderr=b"")

    def test_service_executes_allowlisted_workspace_and_returns_verifiable_signature(self):
        response = self.service.handle_request(self.request)
        public_key = self.key.public_key().public_bytes_raw()
        result = verify_broker_response(
            response,
            public_key=public_key,
            expected_key_id="broker-test-key",
            expected_request_id=self.request_id,
            expected_profile_id="python.pytest",
            expected_target="tests/test_sample.py",
        )
        self.assertTrue(result["execution_succeeded"])
        self.assertEqual(len(self.calls), 1)

    def test_replay_is_rejected_before_second_execution(self):
        self.service.handle_request(self.request)
        with self.assertRaisesRegex(BrokerRequestRejected, "already been used"):
            self.service.handle_request(self.request)
        self.assertEqual(len(self.calls), 1)

    def test_replay_store_survives_service_reconstruction(self):
        self.service.handle_request(self.request)
        restarted = SandboxBrokerService(
            workspace_roots={"project-test": self.root},
            replay_store=BrokerReplayStore(self.db),
            executor=self._execute,
            signing_key=self.key,
            key_id="broker-test-key",
        )
        with self.assertRaisesRegex(BrokerRequestRejected, "already been used"):
            restarted.handle_request(self.request)
        self.assertEqual(len(self.calls), 1)

    def test_rejects_unregistered_workspace_before_consuming_or_executing(self):
        bad = dict(self.request, workspace_id="unknown")
        with self.assertRaisesRegex(BrokerRequestRejected, "not registered"):
            self.service.handle_request(bad)
        self.assertEqual(self.calls, [])

    def test_rejects_extra_fields_and_invalid_targets(self):
        with self.assertRaisesRegex(BrokerRequestRejected, "unsupported or missing"):
            validate_broker_request(dict(self.request, command="whoami"))
        for target in ("../outside.py", "/etc/passwd", "tests\\outside.py"):
            bad = dict(self.request, target=target)
            with self.subTest(target=target), self.assertRaises(BrokerRequestRejected):
                validate_broker_request(bad)


if __name__ == "__main__":
    unittest.main()
