"""Manifest v2 Broker execution must resolve and attest both immutable digests."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.execution_profiles import ExecutionProfileSpec, MAX_OUTPUT_BYTES
from core.sandbox_broker import BrokerReplayStore, BrokerRequestRejected, SandboxBrokerService
from core.sandbox_broker_protocol import (
    BROKER_MANIFEST_REQUEST_SCHEMA,
    BROKER_MANIFEST_RESPONSE_SCHEMA,
    SKILL_MANIFEST_ARTIFACT_RESOLUTION_SCHEMA,
    SKILL_REPLAY_MANIFEST_BINDING_SCHEMA,
    SKILL_REPLAY_OUTPUT_SCHEMA,
    build_broker_request,
    verify_broker_response,
)
from core.sandbox_broker_transport import (
    execute_via_broker_attested,
    serve_listener,
    stage_skill_candidate_via_broker,
)
from core.skill_artifact_store import SkillArtifactStore
from core.skill_manifest import manifest_sha256
from core.sandbox_runner import RunnerProcessOutput


class BrokerManifestExecutionTests(unittest.TestCase):
    def _manifest(self):
        return {
            "schema_version": "mission.skill-manifest.v1",
            "skill_id": "manifest-skill",
            "skill_version": "1.0.0",
            "name": "Manifest Skill",
            "domain": "python",
            "capability_type": "automation",
            "description": "A bounded test candidate",
            "task_types": ["automation"],
            "input_schema": {
                "type": "object", "properties": {}, "required": [],
                "additionalProperties": False,
            },
            "output_schema": {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
            "runtime_contract": {
                "id": "python.run_context.v1",
                "entrypoint": "run",
                "call_signature": "run(context)",
            },
            "compatibility": {
                "runtime": "python", "min_version": "3.10", "max_version": "3.13",
            },
        }

    def test_manifest_v2_execution_uses_real_socket_and_binds_both_digests(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir(mode=0o700)
            artifact_root = root / "artifacts"
            artifact_root.mkdir(mode=0o700)
            broker_key = Ed25519PrivateKey.generate()
            validator_key = Ed25519PrivateKey.generate()
            broker_public = broker_key.public_key().public_bytes_raw()
            validator_public = validator_key.public_key().public_bytes_raw()
            workspace_id = "manifest-workspace"
            tenant_id = "manifest-tenant"
            context = {
                "tenant_id": tenant_id, "mission_run_id": "mission-1",
                "node_id": "node-1", "task_id": "task-1",
            }
            code = "def run(context):\n    return {'ok': True}\n"
            manifest = self._manifest()
            manifest_digest = manifest_sha256(manifest)
            code_digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
            output = {
                "schema_version": SKILL_REPLAY_OUTPUT_SCHEMA,
                "success": True, "value": {"ok": True}, "error": None, "logs": "",
            }
            output_bytes = json.dumps(
                output, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
            executions = []

            def isolated_executor(skill, mission_context, *, timeout_seconds):
                executions.append((skill, dict(mission_context), timeout_seconds))
                self.assertEqual(skill.code, code)
                self.assertEqual(skill.manifest_sha256, manifest_digest)
                return RunnerProcessOutput(
                    exit_code=0, stdout=output_bytes, stderr=b"",
                    stdout_available_bytes=len(output_bytes), stderr_available_bytes=0,
                )

            store = SkillArtifactStore(
                artifact_root, validator_public_key=validator_public,
                validator_key_id="validator-key",
            )
            broker = SandboxBrokerService(
                workspace_roots={workspace_id: workspace},
                workspace_tenants={workspace_id: [tenant_id]},
                replay_store=BrokerReplayStore(root / "broker-state" / "replay.sqlite3"),
                executor=lambda _spec: RunnerProcessOutput(0, b"", b""),
                signing_key=broker_key, key_id="broker-key",
                skill_artifact_store=store, skill_replay_executor=isolated_executor,
            )
            socket_path = root / "broker.sock"
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(socket_path))
            listener.listen(8)
            stop = threading.Event()
            server = threading.Thread(
                target=serve_listener,
                kwargs={
                    "listener": listener, "service": broker,
                    "allowed_uids": [os.getuid()], "stop_event": stop,
                },
                daemon=True,
            )
            server.start()
            try:
                stage_skill_candidate_via_broker(
                    str(socket_path), workspace_id, tenant_id=tenant_id,
                    mission_context=context, skill_id="manifest-skill",
                    skill_version="1.0.0", code=code, manifest=manifest,
                    expected_manifest_sha256=manifest_digest,
                    public_key=broker_public, expected_key_id="broker-key",
                    request_id="11111111-1111-4111-8111-111111111111",
                )
                verified_binding = {
                    "schema_version": SKILL_REPLAY_MANIFEST_BINDING_SCHEMA,
                    "skill_id": "manifest-skill", "skill_version": "1.0.0",
                    "content_sha256": code_digest, "manifest_sha256": manifest_digest,
                    "trust_level": "verified", "mission_context": context,
                }
                with self.assertRaises(BrokerRequestRejected):
                    broker.handle_request(build_broker_request(
                        workspace_id,
                        ExecutionProfileSpec(
                            profile_id="skill.replay.python.v1", target="manifest-skill@1.0.0",
                            argv=(), cwd=workspace, timeout_seconds=30,
                            max_output_bytes=MAX_OUTPUT_BYTES, network_access=False,
                        ),
                        mission_context=context,
                        request_id="22222222-2222-4222-8222-222222222223",
                        skill_binding=verified_binding,
                    ))
                self.assertEqual(executions, [])

                binding = {
                    "schema_version": SKILL_REPLAY_MANIFEST_BINDING_SCHEMA,
                    "skill_id": "manifest-skill", "skill_version": "1.0.0",
                    "content_sha256": code_digest, "manifest_sha256": manifest_digest,
                    "trust_level": "draft", "mission_context": context,
                }
                result = execute_via_broker_attested(
                    str(socket_path), workspace_id,
                    ExecutionProfileSpec(
                        profile_id="skill.replay.python.v1",
                        target="manifest-skill@1.0.0", argv=(), cwd=workspace,
                        timeout_seconds=30, max_output_bytes=MAX_OUTPUT_BYTES,
                        network_access=False,
                    ),
                    mission_context=context, public_key=broker_public,
                    expected_key_id="broker-key", skill_binding=binding,
                    request_id="22222222-2222-4222-8222-222222222222",
                )
                envelope = result["attestation"]
                self.assertEqual(envelope["schema_version"], BROKER_MANIFEST_RESPONSE_SCHEMA)
                self.assertEqual(envelope["skill_binding"], binding)
                self.assertEqual(envelope["skill_artifact"], {
                    "schema_version": SKILL_MANIFEST_ARTIFACT_RESOLUTION_SCHEMA,
                    "skill_id": "manifest-skill", "skill_version": "1.0.0",
                    "content_sha256": code_digest, "manifest_sha256": manifest_digest,
                    "trust_level": "draft",
                })
                self.assertTrue(result["result"]["execution_succeeded"])
                self.assertEqual(len(executions), 1)
                self.assertEqual(executions[0][1], context)
            finally:
                stop.set()
                server.join(timeout=3)
                listener.close()
                socket_path.unlink(missing_ok=True)
            self.assertFalse(server.is_alive())

    def test_manifest_v2_execution_rejects_tampered_manifest_digest_before_runner(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir(mode=0o700)
            artifact_root = root / "artifacts"
            artifact_root.mkdir(mode=0o700)
            broker_key = Ed25519PrivateKey.generate()
            validator_key = Ed25519PrivateKey.generate()
            workspace_id = "manifest-workspace"
            tenant_id = "manifest-tenant"
            context = {
                "tenant_id": tenant_id, "mission_run_id": "mission-2",
                "node_id": "node-2", "task_id": "task-2",
            }
            code = "def run(context):\n    return {'ok': True}\n"
            manifest = self._manifest()
            digest = manifest_sha256(manifest)
            store = SkillArtifactStore(
                artifact_root,
                validator_public_key=validator_key.public_key().public_bytes_raw(),
                validator_key_id="validator-key",
            )
            store.stage_candidate(
                tenant_id=tenant_id,
                skill=type("Candidate", (), {
                    "id": "manifest-skill", "version": "1.0.0",
                    "code": code, "trust_level": "draft",
                })(),
                manifest=manifest, expected_manifest_sha256=digest,
            )
            executions = []
            broker = SandboxBrokerService(
                workspace_roots={workspace_id: workspace},
                workspace_tenants={workspace_id: [tenant_id]},
                replay_store=BrokerReplayStore(root / "broker-state" / "replay.sqlite3"),
                executor=lambda _spec: RunnerProcessOutput(0, b"", b""),
                signing_key=broker_key, key_id="broker-key",
                skill_artifact_store=store,
                skill_replay_executor=lambda *args, **kwargs: executions.append(args),
            )
            request = {
                "schema_version": BROKER_MANIFEST_REQUEST_SCHEMA,
                "request_id": "33333333-3333-4333-8333-333333333333",
                "workspace_id": workspace_id, "mission_context": context,
                "skill_binding": {
                    "schema_version": SKILL_REPLAY_MANIFEST_BINDING_SCHEMA,
                    "skill_id": "manifest-skill", "skill_version": "1.0.0",
                    "content_sha256": hashlib.sha256(code.encode()).hexdigest(),
                    "manifest_sha256": "0" * 64, "trust_level": "draft",
                    "mission_context": context,
                },
                "profile_id": "skill.replay.python.v1",
                "target": "manifest-skill@1.0.0", "timeout_seconds": 30,
            }
            with self.assertRaises(BrokerRequestRejected):
                broker.handle_request(request)
            self.assertEqual(executions, [])


if __name__ == "__main__":
    unittest.main()
