"""Cross-component Mission -> Broker -> Validator -> Artifact Store integration."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from admin.knowledge_runtime import write_skill_candidate
from admin.skill_replay_runtime import SkillReplayRuntime
from core import Skill, SkillTrustLevel
from core.sandbox_broker import BrokerReplayStore, SandboxBrokerService
from core.sandbox_broker_protocol import (
    SKILL_CANDIDATE_PROMOTION_REQUEST_SCHEMA,
    SKILL_CANDIDATE_STAGE_REQUEST_SCHEMA,
    SKILL_REPLAY_OUTPUT_SCHEMA,
)
from core.sandbox_runner import RunnerProcessOutput
from core.skill_artifact_store import SkillArtifactStore
from core.skill_replay_evidence_store import SkillReplayEvidenceStore
from core.skill_validator import SkillValidatorService, verify_validation_response
from core.sandbox_broker_protocol import broker_response_sha256


class MissionBrokerArtifactIntegrationTests(unittest.TestCase):
    def test_mission_replay_persists_experience_and_publishes_validator_attested_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir(mode=0o700)
            evidence_root = root / "evidence"
            evidence_root.mkdir(mode=0o700)
            artifact_root = root / "broker-artifacts"
            artifact_root.mkdir(mode=0o700)

            broker_key = Ed25519PrivateKey.generate()
            validator_key = Ed25519PrivateKey.generate()
            broker_public_key = broker_key.public_key().public_bytes_raw()
            validator_public_key = validator_key.public_key().public_bytes_raw()
            broker_key_id = "broker-integration-key"
            validator_key_id = "validator-integration-key"
            workspace_id = "workspace-integration"
            tenant_id = "tenant-integration"
            mission_context = {
                "tenant_id": tenant_id,
                "mission_run_id": "mission-integration",
                "node_id": "node-delivery",
                "task_id": "task-replay",
            }

            code = "def run(context):\\n    return {'ok': True}\\n"
            skill = Skill(
                id="skill-integration",
                name="Integration Skill",
                domain="python",
                description="Exercises the real Broker and Validator service logic",
                code=code,
                parameters={
                    "execution_contract": {
                        "kind": "python_run_context",
                        "replay_eligible": True,
                    },
                    "mission_run_id": mission_context["mission_run_id"],
                    "mission_node_id": mission_context["node_id"],
                },
                trust_level=SkillTrustLevel.DRAFT,
                version="1.0.0",
            )
            write_skill_candidate(workspace, tenant_id, skill)

            digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
            validator = SkillValidatorService(
                validator_id="independent-validator",
                key_id=validator_key_id,
                signing_key=validator_key,
                broker_public_key=broker_public_key,
                broker_key_id=broker_key_id,
                workspace_ids=[workspace_id],
                policies=[{
                    "policy_id": "integration-policy",
                    "tenant_id": tenant_id,
                    "skill_id": skill.id,
                    "skill_version": skill.version,
                    "content_sha256": digest,
                    "trust_level": "verified",
                    "checks": [{
                        "type": "json_value_equals",
                        "key_path": ["ok"],
                        "expected": True,
                    }],
                }],
            )
            artifact_store = SkillArtifactStore(
                artifact_root,
                validator_public_key=validator_public_key,
                validator_key_id=validator_key_id,
            )
            output_envelope = {
                "schema_version": SKILL_REPLAY_OUTPUT_SCHEMA,
                "success": True,
                "value": {"ok": True},
                "error": None,
                "logs": "",
            }
            output_bytes = json.dumps(
                output_envelope, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")

            def isolated_skill_executor(_skill, _context, *, timeout_seconds):
                self.assertGreater(timeout_seconds, 0)
                return RunnerProcessOutput(
                    exit_code=0,
                    stdout=output_bytes,
                    stderr=b"",
                    stdout_available_bytes=len(output_bytes),
                    stderr_available_bytes=0,
                )

            broker = SandboxBrokerService(
                workspace_roots={workspace_id: workspace},
                workspace_tenants={workspace_id: [tenant_id]},
                replay_store=BrokerReplayStore(root / "broker-state" / "replay.sqlite3"),
                executor=lambda _spec: RunnerProcessOutput(0, b"", b""),
                signing_key=broker_key,
                key_id=broker_key_id,
                skill_artifact_store=artifact_store,
                skill_replay_executor=isolated_skill_executor,
            )
            evidence_store = SkillReplayEvidenceStore(
                evidence_root,
                broker_public_key=broker_public_key,
                broker_key_id=broker_key_id,
            )
            runtime = SkillReplayRuntime(
                workspace=workspace,
                socket_path="/run/test-broker.sock",
                workspace_id=workspace_id,
                broker_public_key=broker_public_key,
                broker_key_id=broker_key_id,
                evidence_store=evidence_store,
                validator_socket_path="/run/test-validator.sock",
                validator_public_key=validator_public_key,
                validator_key_id=validator_key_id,
            )

            def broker_dispatch(_socket_path, request, *, timeout_seconds):
                self.assertGreater(timeout_seconds, 0)
                schema = request.get("schema_version")
                if schema == SKILL_CANDIDATE_STAGE_REQUEST_SCHEMA:
                    return broker.stage_skill_candidate(request)
                if schema == SKILL_CANDIDATE_PROMOTION_REQUEST_SCHEMA:
                    return broker.promote_skill_candidate(request)
                return broker.handle_request(request)

            def validate_request(
                _socket, *, request, validator_public_key, expected_key_id,
                expected_identity, **_kwargs,
            ):
                response = validator.validate(request)
                return verify_validation_response(
                    response,
                    public_key=validator_public_key,
                    expected_key_id=expected_key_id,
                    expected_request_id=request["request_id"],
                    expected_identity=expected_identity,
                )

            with patch(
                "core.sandbox_broker_transport.request_broker",
                side_effect=broker_dispatch,
            ), patch(
                "admin.skill_replay_runtime.request_skill_validation",
                side_effect=validate_request,
            ):
                operation = runtime.replay_candidate(
                    tenant_id=tenant_id,
                    mission_run={
                        "mission_run_id": mission_context["mission_run_id"],
                        "tenant_id": tenant_id,
                        "plan": {"nodes": [{"id": mission_context["node_id"]}]},
                    },
                    node_id=mission_context["node_id"],
                    task_id=mission_context["task_id"],
                    skill_id=skill.id,
                )

            self.assertEqual(operation["replay"]["result"]["execution_succeeded"], True)
            self.assertEqual(operation["replay"]["experience"]["execution_status"], "succeeded")
            self.assertEqual(operation["validation"]["status"], "passed")
            self.assertEqual(operation["promotion"]["status"], "published")

            evidence_id = operation["replay"]["evidence"]["evidence_id"]
            evidence = evidence_store.load_verified(
                tenant_id=tenant_id,
                evidence_id=evidence_id,
            )
            self.assertEqual(evidence["mission_context"], mission_context)
            self.assertEqual(evidence["broker_attestation"]["request_id"], evidence_id)

            published_binding = dict(operation["skill_binding"])
            published_binding["trust_level"] = "verified"
            published = artifact_store.load_for_binding(published_binding)
            self.assertEqual(published.id, skill.id)
            self.assertEqual(published.version, skill.version)
            self.assertEqual(published.code, code)
            self.assertEqual(published.trust_level, "verified")


if __name__ == "__main__":
    unittest.main()
