"""Tests for root-configured broker daemon bootstrap policy."""
import json
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
from core.sandbox_docker_executor import DockerSandboxConfigurationError


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
            "workspace_tenants": {"workspace-one": ["tenant-one"]},
            "replay_database": str(Path(self.temp.name) / "state" / "replay.sqlite3"),
            "signing_key": str(self.key_path),
            "key_id": "broker-test",
            "image": IMAGE,
            "allowed_uids": [os.getuid()],
            "max_workers": 2,
            "artifact_store_root": str(Path(self.temp.name) / "trusted-artifacts"),
            "validator_public_key": str(Path(self.temp.name) / "validator.pub"),
            "validator_key_id": "validator-test-key",
        }
        Path(self.config["artifact_store_root"]).mkdir(mode=0o700)
        validator = Ed25519PrivateKey.generate()
        Path(self.config["validator_public_key"]).write_bytes(validator.public_key().public_bytes_raw())
        Path(self.config["validator_public_key"]).chmod(0o400)

    def tearDown(self):
        self.temp.cleanup()

    def test_deployment_example_matches_required_broker_configuration(self):
        example_path = Path(__file__).resolve().parents[1] / "deploy" / "sandbox-broker.config.example.json"
        example = json.loads(example_path.read_text(encoding="utf-8"))
        required_fields = {
            "workspace_roots", "workspace_tenants", "replay_database",
            "signing_key", "key_id", "image", "allowed_uids", "max_workers",
            "artifact_store_root", "validator_public_key", "validator_key_id",
        }
        self.assertEqual(set(example), required_fields)
        self.assertEqual(set(example["workspace_tenants"]), set(example["workspace_roots"]))
        self.assertTrue(all(
            isinstance(tenants, list) and tenants
            for tenants in example["workspace_tenants"].values()
        ))

    def test_builds_service_from_explicit_workspace_and_peer_allowlists(self):
        with patch(
            "core.sandbox_broker_daemon.DockerSandboxExecutor.connect_docker_socket",
            return_value=object(),
        ), patch(
            "core.sandbox_broker_daemon.DockerSandboxExecutor.verify_runtime_ready",
            return_value=True,
        ) as preflight:
            service, allowed_uids, workers = build_service(self.config)
        preflight.assert_called_once()
        self.assertEqual(allowed_uids, (os.getuid(),))
        self.assertEqual(workers, 2)
        self.assertIn("workspace-one", service.workspace_roots)
        self.assertEqual(service.workspace_tenants["workspace-one"], frozenset({"tenant-one"}))
        self.assertIsNotNone(service.skill_artifact_store)

    def test_docker_isolation_preflight_failure_blocks_broker_startup(self):
        with patch(
            "core.sandbox_broker_daemon.DockerSandboxExecutor.connect_docker_socket",
            return_value=object(),
        ), patch(
            "core.sandbox_broker_daemon.DockerSandboxExecutor.verify_runtime_ready",
            side_effect=DockerSandboxConfigurationError("seccomp is unavailable"),
        ):
            with self.assertRaisesRegex(BrokerDaemonConfigurationError, "isolation preflight failed"):
                build_service(self.config)

    def test_rejects_missing_or_ambiguous_workspace_tenant_allowlist(self):
        invalid_configs = (
            {key: value for key, value in self.config.items() if key != "workspace_tenants"},
            {**self.config, "workspace_tenants": {}},
            {**self.config, "workspace_tenants": {"workspace-one": []}},
            {**self.config, "workspace_tenants": {"workspace-one": ["tenant-one", "tenant-one"]}},
            {**self.config, "workspace_tenants": {"workspace-one": ["../tenant"]}},
        )
        for config in invalid_configs:
            with self.subTest(config=config), self.assertRaises(BrokerDaemonConfigurationError):
                with patch("core.sandbox_broker_daemon.DockerSandboxExecutor.connect_docker_socket", return_value=object()):
                    build_service(config)

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
