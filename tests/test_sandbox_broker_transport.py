"""Tests for bounded Unix socket framing and kernel peer authorization."""
import json
import socket
import struct
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.execution_profiles import resolve_execution_profile
from core.sandbox_broker import BrokerReplayStore, SandboxBrokerService
from core.skill_artifact_store import SkillArtifactStore
from core.sandbox_broker_protocol import build_broker_request
from core.sandbox_broker_transport import (
    execute_via_broker,
    execute_via_broker_attested,
    BrokerTransportError,
    handle_broker_connection,
    request_broker,
    request_broker_replay_status,
    serve_listener,
    stage_skill_candidate_via_broker,
)
from core.sandbox_runner import RunnerProcessOutput


@unittest.skipUnless(hasattr(socket, "AF_UNIX") and hasattr(socket, "SO_PEERCRED"),
                     "requires Unix sockets and SO_PEERCRED")
class SandboxBrokerTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name) / "workspace"
        (root / "tests").mkdir(parents=True)
        (root / "tests" / "test_sample.py").write_text(
            "def test_sample():\n    assert True\n", encoding="utf-8"
        )
        self.spec = resolve_execution_profile(root, {
            "profile_id": "python.pytest", "target": "tests/test_sample.py",
        })
        self.request_id = str(uuid.uuid4())
        request = build_broker_request("test-workspace", self.spec, mission_context={"tenant_id": "tenant-test", "mission_run_id": "mission-test", "node_id": "node-test", "task_id": "task-test"}, request_id=self.request_id)
        self.key = Ed25519PrivateKey.generate()
        self.service = SandboxBrokerService(
            workspace_roots={"test-workspace": root},
            workspace_tenants={"test-workspace": ["tenant-test"]},
            replay_store=BrokerReplayStore(Path(self.temp.name) / "broker" / "replay.sqlite3"),
            executor=lambda _spec: RunnerProcessOutput(0, b"ok", b""),
            signing_key=self.key,
            key_id="test-key",
        )
        self.request = request

    def tearDown(self):
        self.temp.cleanup()

    def _exchange(self, allowed_uids):
        client, server = socket.socketpair()
        errors = []
        def serve():
            try:
                handle_broker_connection(server, service=self.service, allowed_uids=allowed_uids)
            except Exception as exc:
                errors.append(exc)
            finally:
                server.close()
        thread = threading.Thread(target=serve)
        thread.start()
        payload = json.dumps(self.request, separators=(",", ":")).encode()
        try:
            client.sendall(struct.pack("!I", len(payload)) + payload)
        except (BrokenPipeError, ConnectionResetError):
            # Unauthorized peers are closed before the server reads request bytes.
            pass
        try:
            header = client.recv(4)
            if len(header) != 4:
                return None, errors, thread
            size = struct.unpack("!I", header)[0]
            chunks = []
            while sum(map(len, chunks)) < size:
                chunks.append(client.recv(size - sum(map(len, chunks))))
            return json.loads(b"".join(chunks)), errors, thread
        except (ConnectionResetError, OSError):
            return None, errors, thread
        finally:
            client.close()

    def test_listener_rejects_boolean_or_duplicate_uid_configuration(self):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            for uids in ([True], [-1], [1, 1]):
                with self.subTest(uids=uids), self.assertRaises(ValueError):
                    serve_listener(
                        listener, service=self.service, allowed_uids=uids,
                        stop_event=threading.Event(), max_workers=1,
                    )
        finally:
            listener.close()

    def test_authorized_peer_receives_signed_broker_response(self):
        import os
        response, errors, thread = self._exchange([os.getuid()])
        thread.join(timeout=3)
        self.assertFalse(errors)
        self.assertEqual(response["request_id"], self.request_id)
        self.assertEqual(response["signature"]["key_id"], "test-key")

    def test_unauthorized_peer_is_rejected_before_execution(self):
        import os
        response, errors, thread = self._exchange([os.getuid() + 1])
        thread.join(timeout=3)
        self.assertIsNone(response)
        self.assertTrue(errors)
        self.assertIsInstance(errors[0], BrokerTransportError)

    def test_execute_via_broker_verifies_signed_result(self):
        import os
        path = str(Path(self.temp.name) / "broker-verified.sock")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        listener.listen(8)
        stop = threading.Event()
        server_thread = threading.Thread(
            target=serve_listener,
            kwargs={
                "listener": listener,
                "service": self.service,
                "allowed_uids": [os.getuid()],
                "stop_event": stop,
                "max_workers": 2,
            },
        )
        server_thread.start()
        public_key = self.key.public_key().public_bytes_raw()
        result = execute_via_broker(
            path, "test-workspace", self.spec,
            mission_context={"tenant_id": "tenant-test", "mission_run_id": "mission-test", "node_id": "node-test", "task_id": "task-test"},
            public_key=public_key, expected_key_id="test-key",
        )
        stop.set()
        server_thread.join(timeout=3)
        listener.close()
        self.assertFalse(server_thread.is_alive())
        self.assertTrue(result["execution_succeeded"])
        self.assertEqual(result["target"], "tests/test_sample.py")

    def test_execute_via_broker_attested_preserves_signed_envelope_for_durable_evidence(self):
        import os
        path = str(Path(self.temp.name) / "broker-attested.sock")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        listener.listen(8)
        stop = threading.Event()
        server_thread = threading.Thread(
            target=serve_listener,
            kwargs={
                "listener": listener,
                "service": self.service,
                "allowed_uids": [os.getuid()],
                "stop_event": stop,
                "max_workers": 2,
            },
        )
        server_thread.start()
        try:
            evidence = execute_via_broker_attested(
                path, "test-workspace", self.spec,
                mission_context={
                    "tenant_id": "tenant-test",
                    "mission_run_id": "mission-test",
                    "node_id": "node-test",
                    "task_id": "task-test",
                },
                public_key=self.key.public_key().public_bytes_raw(),
                expected_key_id="test-key",
            )
        finally:
            stop.set()
            server_thread.join(timeout=3)
            listener.close()
        self.assertFalse(server_thread.is_alive())
        self.assertEqual(evidence["schema_version"], "mission.sandbox-broker-attestation.v1")
        self.assertEqual(evidence["attestation"]["mission_context"]["task_id"], "task-test")
        self.assertEqual(evidence["attestation"]["signature"]["key_id"], "test-key")
        self.assertTrue(evidence["result"]["execution_succeeded"])
        self.assertEqual(evidence["result"]["target"], "tests/test_sample.py")
        self.assertIsNone(evidence["skill_replay_output"])


    def test_stage_skill_candidate_uses_broker_socket_and_verifies_signed_receipt(self):
        import os
        root = Path(self.temp.name) / "workspace"
        artifact_root = Path(self.temp.name) / "broker-candidates"
        artifact_root.mkdir(mode=0o700)
        validator_key = Ed25519PrivateKey.generate()
        artifact_store = SkillArtifactStore(
            artifact_root,
            validator_public_key=validator_key.public_key().public_bytes_raw(),
            validator_key_id="validator-test-key",
        )
        service = SandboxBrokerService(
            workspace_roots={"test-workspace": root},
            workspace_tenants={"test-workspace": ["tenant-transport"]},
            replay_store=self.service.replay_store,
            executor=lambda _spec: RunnerProcessOutput(0, b"ok", b""),
            signing_key=self.key,
            key_id="test-key",
            skill_artifact_store=artifact_store,
            skill_replay_executor=lambda *_args, **_kwargs: RunnerProcessOutput(0, b"", b""),
        )
        path = str(Path(self.temp.name) / "broker-stage.sock")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        listener.listen(8)
        stop = threading.Event()
        server_thread = threading.Thread(
            target=serve_listener,
            kwargs={
                "listener": listener,
                "service": service,
                "allowed_uids": [os.getuid()],
                "stop_event": stop,
                "max_workers": 2,
            },
        )
        server_thread.start()
        context = {
            "tenant_id": "tenant-transport",
            "mission_run_id": "mission-stage",
            "node_id": "node-stage",
            "task_id": "task-stage",
        }
        code = "def run(context):\n    return {'task_id': context['task_id']}\n"
        try:
            receipt = stage_skill_candidate_via_broker(
                path,
                "test-workspace",
                tenant_id="tenant-transport",
                mission_context=context,
                skill_id="skill-transport-demo",
                skill_version="1.0.0",
                code=code,
                public_key=self.key.public_key().public_bytes_raw(),
                expected_key_id="test-key",
            )
        finally:
            stop.set()
            server_thread.join(timeout=3)
            listener.close()
        self.assertFalse(server_thread.is_alive())
        artifact = receipt["candidate_artifact"]
        self.assertEqual(artifact["trust_level"], "draft")
        self.assertEqual(artifact["tenant_id"], "tenant-transport")
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": artifact["skill_id"],
            "skill_version": artifact["skill_version"],
            "content_sha256": artifact["content_sha256"],
            "trust_level": "draft",
            "mission_context": context,
        }
        self.assertEqual(artifact_store.load_for_binding(binding).code, code)

    def test_socket_client_sends_framed_request(self):
        path = str(Path(self.temp.name) / "broker.sock")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        listener.listen(1)
        def serve():
            conn, _ = listener.accept()
            with conn:
                handle_broker_connection(
                    conn, service=self.service, allowed_uids=[__import__("os").getuid()],
                )
        thread = threading.Thread(target=serve)
        thread.start()
        response = request_broker(path, self.request)
        thread.join(timeout=3)
        listener.close()
        self.assertEqual(response["request_id"], self.request_id)


    def test_replay_status_round_trips_over_authenticated_unix_socket(self):
        import os
        completed = self.service.handle_request(self.request)
        socket_path = str(Path(self.temp.name) / "broker-status.sock")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(socket_path)
        listener.listen(8)
        stop = threading.Event()
        thread = threading.Thread(target=serve_listener, kwargs={
            "listener": listener, "service": self.service,
            "allowed_uids": [os.getuid()], "stop_event": stop, "max_workers": 1,
        }, daemon=True)
        thread.start()
        try:
            status = request_broker_replay_status(
                socket_path, request_id=self.request_id, workspace_id="test-workspace",
                mission_context=self.request["mission_context"],
            )
            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["response"], completed)
            missing = request_broker_replay_status(
                socket_path, request_id=str(uuid.uuid4()), workspace_id="test-workspace",
                mission_context=self.request["mission_context"],
            )
            self.assertEqual(missing["status"], "not_found")
            with self.assertRaises(BrokerTransportError):
                request_broker_replay_status(
                    socket_path, request_id=self.request_id, workspace_id="test-workspace",
                    mission_context={**self.request["mission_context"], "tenant_id": "tenant-other"},
                )
        finally:
            stop.set()
            thread.join(timeout=2)
            listener.close()
            Path(socket_path).unlink(missing_ok=True)


    def test_client_timeout_fails_closed_when_broker_does_not_respond(self):
        socket_path = Path(self.temp.name) / "broker-stall.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(1)
        accepted = threading.Event()
        release = threading.Event()

        def stall_peer():
            connection, _ = listener.accept()
            with connection:
                accepted.set()
                release.wait(timeout=1)

        thread = threading.Thread(target=stall_peer, daemon=True)
        thread.start()
        try:
            with self.assertRaisesRegex(BrokerTransportError, "receive deadline exceeded"):
                request_broker(str(socket_path), self.request, timeout_seconds=0.05)
        finally:
            release.set()
            thread.join(timeout=2)
            listener.close()
            socket_path.unlink(missing_ok=True)
        self.assertTrue(accepted.is_set())
        self.assertFalse(thread.is_alive())



if __name__ == "__main__":
    unittest.main()
