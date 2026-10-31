"""Tests for root-configured broker daemon bootstrap policy."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.sandbox_broker_daemon import BrokerDaemonConfigurationError, build_service


IMAGE = "registry.example/evo/python-runner@sha256:" + ("b" * 64)


class SandboxBrokerDaemonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()
        self.key_path = Path(self.temp.name) / "signing-key.pem"
        key = Ed25519PrivateKey.generate()
        self.key_path.write_bytes(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        self.key_path.chmod(0o400)
        self.config = {
            "workspace_roots": {"workspace-one": str(self.root)},
            "replay_database": str(Path(self.temp.name) / "state" / "replay.sqlite3"),
            "signing_key": str(self.key_path),
            "key_id": "broker-test",
            "image": IMAGE,
            "allowed_uids": [os.getuid()],
            "max_workers": 2,
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_builds_service_from_explicit_workspace_and_peer_allowlists(self):
        with patch(
            "core.sandbox_broker_daemon.DockerSandboxExecutor.connect_docker_socket",
            return_value=object(),
        ):
            service, allowed_uids, workers = build_service(self.config)
        self.assertEqual(allowed_uids, (os.getuid(),))
        self.assertEqual(workers, 2)
        self.assertIn("workspace-one", service.workspace_roots)

    def test_rejects_symlink_workspace_root(self):
        link = Path(self.temp.name) / "workspace-link"
        link.symlink_to(self.root, target_is_directory=True)
        bad = dict(self.config, workspace_roots={"workspace-one": str(link)})
        with patch(
            "core.sandbox_broker_daemon.DockerSandboxExecutor.connect_docker_socket",
            return_value=object(),
        ), self.assertRaises(BrokerDaemonConfigurationError):
            build_service(bad)

    def test_rejects_duplicate_or_invalid_peer_uids(self):
        for uids in ([1, 1], [-1], [True], []):
            with self.subTest(uids=uids):
                bad = dict(self.config, allowed_uids=uids)
                with patch(
                    "core.sandbox_broker_daemon.DockerSandboxExecutor.connect_docker_socket",
                    return_value=object(),
                ), self.assertRaises(BrokerDaemonConfigurationError):
                    build_service(bad)


if __name__ == "__main__":
    unittest.main()
