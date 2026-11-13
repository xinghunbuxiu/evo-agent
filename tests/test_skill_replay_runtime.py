"""Regression tests for the opt-in Mission-to-Broker Skill Replay runtime."""
import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core import Skill, SkillTrustLevel
from core.sandbox_broker_protocol import (
    SKILL_CANDIDATE_PROMOTION_RESPONSE_SCHEMA,
    SKILL_VALIDATION_PROVENANCE_SCHEMA,
    broker_response_sha256,
)
from admin.skill_replay_runtime import (
    SkillReplayOutcomeIndeterminate,
    SkillReplayRuntimeConfigurationError,
    SkillReplayRuntime,
    create_skill_replay_runtime,
)


class SkillReplayRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(mode=0o700)
        self.evidence_root = self.root / "evidence"
        self.evidence_root.mkdir(mode=0o700)
        self.key_path = self.root / "broker.pub"
        key = Ed25519PrivateKey.generate()
        self.broker_private_key = key
        self.key_path.write_bytes(key.public_key().public_bytes_raw())
        self.key_path.chmod(0o400)
        self.validator_key_path = self.root / "validator.pub"
        validator_key = Ed25519PrivateKey.generate()
        self.validator_private_key = validator_key
        self.validator_key_path.write_bytes(validator_key.public_key().public_bytes_raw())
        self.validator_key_path.chmod(0o400)
        self.environ = {
            "EVO_SKILL_REPLAY_BROKER_SOCKET": "/run/evo-sandbox-broker.sock",
            "EVO_SKILL_REPLAY_WORKSPACE_ID": "workspace-a",
            "EVO_SKILL_REPLAY_BROKER_PUBLIC_KEY": str(self.key_path),
            "EVO_SKILL_REPLAY_BROKER_KEY_ID": "broker-test-key",
            "EVO_SKILL_REPLAY_EVIDENCE_ROOT": str(self.evidence_root),
        }

    def tearDown(self):
        self.temp.cleanup()

    def _skill(self, *, code="def run(context):\n    return {'ok': True}\n", contract=None, version="1.0.0"):
        parameters = {
            "mission_run_id": "mission-1",
            "mission_node_id": "node-1",
            "execution_contract": contract or {
                "kind": "python_run_context",
                "replay_eligible": True,
            },
        }
        return Skill(
            id="skill-demo",
            name="Demo Skill",
            domain="python",
            description="test",
            code=code,
            parameters=parameters,
            trust_level=SkillTrustLevel.DRAFT,
            version=version,
        )

    @patch("admin.skill_replay_runtime.verify_validation_response")
    @patch("admin.skill_replay_runtime.verify_broker_response")
    def test_recovery_review_reverifies_broker_and_validator_signed_receipts(
        self, verify_broker, verify_validator,
    ):
        environ = dict(self.environ, **{
            "EVO_SKILL_REPLAY_VALIDATOR_SOCKET": "/run/evo-skill-validator/validator.sock",
            "EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY": str(self.validator_key_path),
            "EVO_SKILL_REPLAY_VALIDATOR_KEY_ID": "validator-test-key",
        })
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=environ)
        context = {
            "tenant_id": "tenant-a", "mission_run_id": "mission-a",
            "node_id": "node-a", "task_id": "task-a",
        }
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill-a", "skill_version": "1.0.0",
            "content_sha256": "a" * 64, "trust_level": "draft",
            "mission_context": context,
        }
        broker_envelope = {"signed": "broker-envelope"}
        verify_broker.return_value = {"execution_succeeded": True}
        verify_validator.return_value = {"validation_id": "validation-a"}
        result = runtime.verify_recovery_responses(
            mission_context=context,
            skill_binding=binding,
            execution_request_id="11111111-1111-4111-8111-111111111111",
            validation_request_id="22222222-2222-4222-8222-222222222222",
            broker_outcomes={
                "execution": {"status": "completed", "response": broker_envelope},
            },
            validator_outcome={
                "status": "completed", "response": {"signed": "validator-envelope"},
            },
        )
        self.assertEqual(result["broker_execution"], "verified")
        self.assertEqual(result["validator"], "verified")
        self.assertEqual(result["validation_id"], "validation-a")
        expected_identity = verify_validator.call_args.kwargs["expected_identity"]
        self.assertEqual(expected_identity["broker_attestation_sha256"], broker_response_sha256(broker_envelope))
        self.assertEqual(expected_identity["content_sha256"], "a" * 64)
        self.assertEqual(expected_identity["mission_run_id"], "mission-a")

    @patch("admin.skill_replay_runtime.verify_validation_response")
    @patch("admin.skill_replay_runtime.verify_broker_response")
    def test_recovery_review_rejects_invalid_broker_receipt_before_validator(
        self, verify_broker, verify_validator,
    ):
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=dict(self.environ, **{
            "EVO_SKILL_REPLAY_VALIDATOR_SOCKET": "/run/evo-skill-validator/validator.sock",
            "EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY": str(self.validator_key_path),
            "EVO_SKILL_REPLAY_VALIDATOR_KEY_ID": "validator-test-key",
        }))
        context = {
            "tenant_id": "tenant-a", "mission_run_id": "mission-a",
            "node_id": "node-a", "task_id": "task-a",
        }
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill-a", "skill_version": "1.0.0",
            "content_sha256": "a" * 64, "trust_level": "draft",
            "mission_context": context,
        }
        verify_broker.side_effect = ValueError("bad signature")
        result = runtime.verify_recovery_responses(
            mission_context=context,
            skill_binding=binding,
            execution_request_id="11111111-1111-4111-8111-111111111111",
            validation_request_id="22222222-2222-4222-8222-222222222222",
            broker_outcomes={
                "execution": {"status": "completed", "response": {"tampered": True}},
            },
            validator_outcome={
                "status": "completed", "response": {"signed": "validator-envelope"},
            },
        )
        self.assertEqual(result["broker_execution"], "invalid")
        self.assertEqual(result["validator"], "not_checked")
        verify_validator.assert_not_called()

    @patch("admin.skill_replay_runtime.verify_validation_response")
    @patch("admin.skill_replay_runtime.verify_broker_response")
    def test_recovery_review_rejects_validator_pass_for_failed_broker_execution(
        self, verify_broker, verify_validator,
    ):
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=dict(self.environ, **{
            "EVO_SKILL_REPLAY_VALIDATOR_SOCKET": "/run/evo-skill-validator/validator.sock",
            "EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY": str(self.validator_key_path),
            "EVO_SKILL_REPLAY_VALIDATOR_KEY_ID": "validator-test-key",
        }))
        context = {
            "tenant_id": "tenant-a", "mission_run_id": "mission-a",
            "node_id": "node-a", "task_id": "task-a",
        }
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill-a", "skill_version": "1.0.0",
            "content_sha256": "a" * 64, "trust_level": "draft",
            "mission_context": context,
        }
        verify_broker.return_value = {"execution_succeeded": False}
        result = runtime.verify_recovery_responses(
            mission_context=context,
            skill_binding=binding,
            execution_request_id="11111111-1111-4111-8111-111111111111",
            validation_request_id="22222222-2222-4222-8222-222222222222",
            broker_outcomes={
                "execution": {"status": "completed", "response": {"signed": "failed-execution"}},
            },
            validator_outcome={
                "status": "completed", "response": {"signed": "unexpected-validator-pass"},
            },
        )
        self.assertEqual(result["broker_execution"], "verified")
        self.assertFalse(result["execution_succeeded"])
        self.assertEqual(result["validator"], "invalid")
        verify_validator.assert_not_called()

    @patch("admin.skill_replay_runtime.verify_validation_response")
    @patch("admin.skill_replay_runtime.verify_broker_response")
    def test_recovery_review_verifies_signed_promotion_receipt(
        self, verify_broker, verify_validator,
    ):
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=dict(self.environ, **{
            "EVO_SKILL_REPLAY_VALIDATOR_SOCKET": "/run/evo-skill-validator/validator.sock",
            "EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY": str(self.validator_key_path),
            "EVO_SKILL_REPLAY_VALIDATOR_KEY_ID": "validator-test-key",
        }))
        context = {
            "tenant_id": "tenant-a", "mission_run_id": "mission-a",
            "node_id": "node-a", "task_id": "task-a",
        }
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill-a", "skill_version": "1.0.0",
            "content_sha256": "a" * 64, "trust_level": "draft",
            "mission_context": context,
        }
        broker_envelope = {"signed": "broker-envelope"}
        validation_attestation = {
            "validation_id": "validation-a",
            "validator_id": "validator-a",
            "policy_id": "policy-a",
            "policy_sha256": "b" * 64,
            "checks_sha256": "c" * 64,
        }
        verify_broker.return_value = {"execution_succeeded": True}
        verify_validator.return_value = validation_attestation
        provenance = {
            "schema_version": SKILL_VALIDATION_PROVENANCE_SCHEMA,
            **validation_attestation,
            "broker_request_id": "11111111-1111-4111-8111-111111111111",
            "broker_attestation_sha256": broker_response_sha256(broker_envelope),
        }
        payload = {
            "schema_version": SKILL_CANDIDATE_PROMOTION_RESPONSE_SCHEMA,
            "request_id": "33333333-3333-4333-8333-333333333333",
            "workspace_id": "workspace-a",
            "mission_context": context,
            "artifact": {
                "schema_version": "mission.skill-artifact.v2",
                "tenant_id": "tenant-a",
                "skill_id": "skill-a",
                "skill_version": "1.0.0",
                "content_sha256": "a" * 64,
                "trust_level": "verified",
            },
            "validation_provenance": provenance,
        }
        signed = json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
        response = {
            **payload,
            "signature": {
                "algorithm": "ed25519",
                "key_id": "broker-test-key",
                "value": base64.b64encode(self.broker_private_key.sign(signed)).decode("ascii"),
            },
        }
        result = runtime.verify_recovery_responses(
            mission_context=context,
            skill_binding=binding,
            execution_request_id="11111111-1111-4111-8111-111111111111",
            validation_request_id="22222222-2222-4222-8222-222222222222",
            promotion_request_id="33333333-3333-4333-8333-333333333333",
            broker_outcomes={
                "execution": {"status": "completed", "response": broker_envelope},
                "promotion": {"status": "completed", "response": response},
            },
            validator_outcome={
                "status": "completed", "response": {"signed": "validator-envelope"},
            },
        )
        self.assertEqual(result["broker_execution"], "verified")
        self.assertEqual(result["validator"], "verified")
        self.assertEqual(result["broker_promotion"], "verified")

    def test_missing_configuration_keeps_replay_disabled(self):
        self.assertIsNone(create_skill_replay_runtime(workspace=self.workspace, environ={}))

    def test_partial_configuration_fails_closed(self):
        with self.assertRaisesRegex(SkillReplayRuntimeConfigurationError, "incomplete"):
            create_skill_replay_runtime(
                workspace=self.workspace,
                environ={"EVO_SKILL_REPLAY_BROKER_SOCKET": "/run/evo-sandbox-broker.sock"},
            )

    def test_complete_configuration_builds_runtime(self):
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=self.environ)
        self.assertIsInstance(runtime, SkillReplayRuntime)
        self.assertEqual(runtime.workspace_id, "workspace-a")
        self.assertEqual(runtime.broker_key_id, "broker-test-key")

    def test_validator_configuration_is_optional_but_must_be_complete(self):
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=self.environ)
        self.assertIsNone(runtime.validator_socket_path)
        partial = dict(self.environ, EVO_SKILL_REPLAY_VALIDATOR_SOCKET="/run/evo-skill-validator/validator.sock")
        with self.assertRaisesRegex(SkillReplayRuntimeConfigurationError, "Validator configuration is incomplete"):
            create_skill_replay_runtime(workspace=self.workspace, environ=partial)

    @patch("admin.skill_replay_runtime.promote_skill_candidate_via_broker")
    @patch("admin.skill_replay_runtime.request_skill_validation")
    @patch("admin.skill_replay_runtime.stage_skill_candidate_via_broker")
    def test_successful_replay_is_independently_validated_then_published(self, stage, validate, promote):
        from admin.knowledge_runtime import write_skill_candidate

        skill = self._skill()
        write_skill_candidate(self.workspace, "tenant-a", skill)
        environ = dict(self.environ, **{
            "EVO_SKILL_REPLAY_VALIDATOR_SOCKET": "/run/evo-skill-validator/validator.sock",
            "EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY": str(self.validator_key_path),
            "EVO_SKILL_REPLAY_VALIDATOR_KEY_ID": "validator-test-key",
        })
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=environ)
        stage.return_value = {"schema_version": "mission.skill-candidate-stage-response.v1"}
        runtime.adapter.execute = lambda *args, **kwargs: {
            "schema_version": "mission.skill-replay-result.v1",
            "result": {"execution_succeeded": True},
            "evidence": {"evidence_id": "evidence-1"},
            "experience": {"id": "experience-1"},
        }
        runtime.evidence_store.load_verified = lambda **kwargs: {
            "broker_attestation": {"schema_version": "mission.sandbox-broker-response.v4"},
        }
        validate.return_value = {
            "schema_version": "mission.skill-validation-attestation.v1",
            "validation_id": "validation-1", "validator_id": "validator-independent",
            "policy_id": "policy-1",
        }
        promote.return_value = {
            "artifact": {
                "schema_version": "mission.skill-artifact.v1", "tenant_id": "tenant-a",
                "skill_id": "skill-demo", "skill_version": "1.0.0",
                "content_sha256": "a" * 64, "trust_level": "verified",
            },
        }
        mission_run = {
            "mission_run_id": "mission-1", "tenant_id": "tenant-a",
            "plan": {"nodes": [{"id": "node-1"}]},
        }
        result = runtime.replay_candidate(
            tenant_id="tenant-a", mission_run=mission_run, node_id="node-1",
            task_id="task-1", skill_id="skill-demo",
        )
        validate.assert_called_once()
        request = validate.call_args.kwargs["request"]
        self.assertEqual(request["skill_binding"], result["skill_binding"])
        self.assertEqual(request["trust_level"], "verified")
        self.assertEqual(request["broker_attestation"]["schema_version"], "mission.sandbox-broker-response.v4")
        promote.assert_called_once()
        self.assertEqual(promote.call_args.kwargs["content_sha256"], result["skill_binding"]["content_sha256"])
        self.assertEqual(result["validation"]["status"], "passed")
        self.assertEqual(result["promotion"]["status"], "published")

    @patch("admin.skill_replay_runtime.promote_skill_candidate_via_broker")
    @patch("admin.skill_replay_runtime.request_skill_validation")
    @patch("admin.skill_replay_runtime.stage_skill_candidate_via_broker")
    def test_validator_rejection_never_calls_artifact_promotion(self, stage, validate, promote):
        from admin.knowledge_runtime import write_skill_candidate

        write_skill_candidate(self.workspace, "tenant-a", self._skill())
        environ = dict(self.environ, **{
            "EVO_SKILL_REPLAY_VALIDATOR_SOCKET": "/run/evo-skill-validator/validator.sock",
            "EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY": str(self.validator_key_path),
            "EVO_SKILL_REPLAY_VALIDATOR_KEY_ID": "validator-test-key",
        })
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=environ)
        stage.return_value = {"schema_version": "mission.skill-candidate-stage-response.v1"}
        runtime.adapter.execute = lambda *args, **kwargs: {
            "schema_version": "mission.skill-replay-result.v1",
            "result": {"execution_succeeded": True},
            "evidence": {"evidence_id": "evidence-1"},
            "experience": {"id": "experience-1"},
        }
        runtime.evidence_store.load_verified = lambda **kwargs: {
            "broker_attestation": {"schema_version": "mission.sandbox-broker-response.v4"},
        }
        validate.side_effect = RuntimeError("policy rejected after Validator request claim")
        with self.assertRaises(SkillReplayOutcomeIndeterminate) as raised:
            runtime.replay_candidate(
                tenant_id="tenant-a",
                mission_run={"mission_run_id": "mission-1", "tenant_id": "tenant-a", "plan": {"nodes": [{"id": "node-1"}]}},
                node_id="node-1", task_id="task-1", skill_id="skill-demo",
            )
        self.assertEqual(raised.exception.evidence_ref["evidence_id"], "evidence-1")
        self.assertIn("Validator outcome", str(raised.exception))
        promote.assert_not_called()

    @patch("admin.skill_replay_runtime.promote_skill_candidate_via_broker")
    @patch("admin.skill_replay_runtime.request_skill_validation")
    @patch("admin.skill_replay_runtime.stage_skill_candidate_via_broker")
    def test_uncertain_artifact_publication_requires_manual_recovery(self, stage, validate, promote):
        from admin.knowledge_runtime import write_skill_candidate

        write_skill_candidate(self.workspace, "tenant-a", self._skill())
        environ = dict(self.environ, **{
            "EVO_SKILL_REPLAY_VALIDATOR_SOCKET": "/run/evo-skill-validator/validator.sock",
            "EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY": str(self.validator_key_path),
            "EVO_SKILL_REPLAY_VALIDATOR_KEY_ID": "validator-test-key",
        })
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=environ)
        stage.return_value = {"schema_version": "mission.skill-candidate-stage-response.v1"}
        runtime.adapter.execute = lambda *args, **kwargs: {
            "schema_version": "mission.skill-replay-result.v1",
            "result": {"execution_succeeded": True},
            "evidence": {"evidence_id": "evidence-1", "sha256": "b" * 64},
            "experience": {"id": "experience-1"},
        }
        runtime.evidence_store.load_verified = lambda **kwargs: {
            "broker_attestation": {"schema_version": "mission.sandbox-broker-response.v4"},
        }
        validate.return_value = {
            "schema_version": "mission.skill-validation-attestation.v1",
            "validation_id": "validation-1", "validator_id": "validator-independent",
            "policy_id": "policy-1",
        }
        promote.side_effect = RuntimeError("Broker response lost after possible publication")
        with self.assertRaises(SkillReplayOutcomeIndeterminate) as raised:
            runtime.replay_candidate(
                tenant_id="tenant-a",
                mission_run={"mission_run_id": "mission-1", "tenant_id": "tenant-a", "plan": {"nodes": [{"id": "node-1"}]}},
                node_id="node-1", task_id="task-1", skill_id="skill-demo",
            )
        self.assertEqual(raised.exception.evidence_ref["evidence_id"], "evidence-1")
        self.assertIn("publication outcome", str(raised.exception))
        promote.assert_called_once()

    def test_rejects_symlinked_broker_public_key(self):
        real_key = self.root / "real-broker.pub"
        real_key.write_bytes(self.key_path.read_bytes())
        real_key.chmod(0o400)
        self.key_path.unlink()
        self.key_path.symlink_to(real_key)
        with self.assertRaisesRegex(SkillReplayRuntimeConfigurationError, "non-symlink"):
            create_skill_replay_runtime(workspace=self.workspace, environ=self.environ)

    def test_rejects_group_or_world_accessible_evidence_root(self):
        self.evidence_root.chmod(0o750)
        with self.assertRaisesRegex(SkillReplayRuntimeConfigurationError, "private"):
            create_skill_replay_runtime(workspace=self.workspace, environ=self.environ)

    def test_recipe_candidate_is_not_replay_eligible(self):
        recipe = self._skill(
            code="1. Read the project.\\n2. Fix the issue.\\n",
            contract={
                "kind": "non_executable_recipe",
                "replay_eligible": False,
            },
        )
        with self.assertRaisesRegex(ValueError, "Recipe"):
            SkillReplayRuntime._validate_executable_contract(recipe)

    def test_rejects_missing_async_or_wrong_run_entrypoint(self):
        for code in (
            "print('no run')",
            "async def run(context):\\n    return {}\\n",
            "def run():\\n    return {}\\n",
            "def run(context, extra):\\n    return {}\\n",
            "def run(*context):\\n    return {}\\n",
        ):
            with self.subTest(code=code):
                with self.assertRaises(ValueError):
                    SkillReplayRuntime._validate_executable_contract(self._skill(code=code))

    def test_replay_candidate_loader_rejects_tenant_directory_symlink(self):
        from admin.skill_replay_runtime import _load_draft_skill_payload

        tenants = self.workspace / ".tenants"
        tenants.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "skill-demo.json").write_text("{}", encoding="utf-8")
        (tenants / "tenant-a").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            _load_draft_skill_payload(self.workspace, "tenant-a", "skill-demo")

    @patch("admin.skill_replay_runtime.stage_skill_candidate_via_broker")
    def test_replay_stages_exact_candidate_then_calls_adapter(self, stage):
        from admin.knowledge_runtime import write_skill_candidate

        skill = self._skill()
        write_skill_candidate(self.workspace, "tenant-a", skill)
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=self.environ)
        stage.return_value = {"schema_version": "mission.skill-candidate-stage-response.v1"}
        runtime.adapter.execute = lambda *args, **kwargs: {
            "schema_version": "mission.skill-replay-result.v1",
            "result": {"execution_succeeded": True},
            "evidence": {"evidence_id": "evidence-1"},
            "experience": {"id": "experience-1"},
        }
        mission_run = {
            "mission_run_id": "mission-1",
            "tenant_id": "tenant-a",
            "plan": {"nodes": [{"id": "node-1"}]},
        }
        result = runtime.replay_candidate(
            tenant_id="tenant-a",
            mission_run=mission_run,
            node_id="node-1",
            task_id="task-1",
            skill_id="skill-demo",
        )
        stage.assert_called_once()
        self.assertEqual(result["skill_binding"]["mission_context"]["task_id"], "task-1")
        self.assertEqual(result["replay"]["evidence"]["evidence_id"], "evidence-1")
        self.assertEqual(result["validation"]["status"], "not_configured")
        self.assertEqual(result["promotion"]["status"], "not_attempted")

    @patch("admin.skill_replay_runtime.stage_skill_candidate_via_broker")
    def test_candidate_binding_callback_runs_before_broker_staging(self, stage):
        from admin.knowledge_runtime import write_skill_candidate

        write_skill_candidate(self.workspace, "tenant-a", self._skill())
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=self.environ)
        stage.return_value = {"schema_version": "mission.skill-candidate-stage-response.v1"}
        runtime.adapter.execute = lambda *args, **kwargs: {
            "schema_version": "mission.skill-replay-result.v1",
            "result": {"execution_succeeded": True},
            "evidence": {"evidence_id": "evidence-1"},
            "experience": {"id": "experience-1"},
        }
        events = []
        def on_bound(payload):
            events.append(("bound", payload))
        stage.side_effect = lambda *args, **kwargs: events.append(("stage", kwargs)) or {
            "schema_version": "mission.skill-candidate-stage-response.v1"
        }
        runtime.replay_candidate(
            tenant_id="tenant-a",
            mission_run={
                "mission_run_id": "mission-1",
                "tenant_id": "tenant-a",
                "plan": {"nodes": [{"id": "node-1"}]},
            },
            node_id="node-1",
            task_id="task-1",
            skill_id="skill-demo",
            on_candidate_bound=on_bound,
        )
        self.assertEqual(events[0][0], "bound")
        self.assertEqual(events[1][0], "stage")
        pinned = events[0][1]
        self.assertEqual(len(pinned["skill_binding"]["content_sha256"]), 64)
        self.assertEqual(events[1][1]["request_id"], pinned["stage_request_id"])

    @patch("admin.skill_replay_runtime.stage_skill_candidate_via_broker")
    def test_replay_requires_explicit_mission_tenant_before_broker_staging(self, stage):
        from admin.knowledge_runtime import write_skill_candidate

        write_skill_candidate(self.workspace, "tenant-a", self._skill())
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=self.environ)
        with self.assertRaisesRegex(ValueError, "tenant identity is missing or invalid"):
            runtime.replay_candidate(
                tenant_id="tenant-a",
                mission_run={
                    "mission_run_id": "mission-1",
                    "plan": {"nodes": [{"id": "node-1"}]},
                },
                node_id="node-1",
                task_id="task-1",
                skill_id="skill-demo",
            )
        stage.assert_not_called()

    @patch("admin.skill_replay_runtime.stage_skill_candidate_via_broker")
    def test_stage_idempotency_is_bound_to_candidate_identity(self, stage):
        from admin.knowledge_runtime import write_skill_candidate

        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=self.environ)
        stage.return_value = {"schema_version": "mission.skill-candidate-stage-response.v1"}
        runtime.adapter.execute = lambda *args, **kwargs: {
            "schema_version": "mission.skill-replay-result.v1",
            "result": {"execution_succeeded": True},
            "evidence": {"evidence_id": "evidence-1"},
            "experience": {"id": "experience-1"},
        }
        mission_run = {
            "mission_run_id": "mission-1",
            "tenant_id": "tenant-a",
            "plan": {"nodes": [{"id": "node-1"}]},
        }

        write_skill_candidate(self.workspace, "tenant-a", self._skill(version="1.0.0"))
        runtime.replay_candidate(
            tenant_id="tenant-a", mission_run=mission_run, node_id="node-1",
            task_id="task-1", skill_id="skill-demo",
        )
        first_id = stage.call_args.kwargs["request_id"]

        write_skill_candidate(self.workspace, "tenant-a", self._skill(version="1.0.1"))
        runtime.replay_candidate(
            tenant_id="tenant-a", mission_run=mission_run, node_id="node-1",
            task_id="task-1", skill_id="skill-demo",
        )
        second_id = stage.call_args.kwargs["request_id"]

        runtime.replay_candidate(
            tenant_id="tenant-a", mission_run=mission_run, node_id="node-1",
            task_id="task-1", skill_id="skill-demo",
        )
        third_id = stage.call_args.kwargs["request_id"]
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(second_id, third_id)

    @patch("admin.skill_replay_runtime.stage_skill_candidate_via_broker")
    def test_replay_rejects_recipe_before_broker_staging(self, stage):
        from admin.knowledge_runtime import write_skill_candidate

        recipe = self._skill(
            code="Recipe only",
            contract={"kind": "non_executable_recipe", "replay_eligible": False},
        )
        write_skill_candidate(self.workspace, "tenant-a", recipe)
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=self.environ)
        with self.assertRaisesRegex(ValueError, "Recipe"):
            runtime.replay_candidate(
                tenant_id="tenant-a",
                mission_run={
                    "mission_run_id": "mission-1",
                    "tenant_id": "tenant-a",
                    "plan": {"nodes": [{"id": "node-1"}]},
                },
                node_id="node-1",
                task_id="task-1",
                skill_id="skill-demo",
            )
        stage.assert_not_called()


    @patch("admin.skill_replay_runtime.promote_skill_candidate_via_broker")
    @patch("admin.skill_replay_runtime.verify_validation_response")
    def test_resume_promotion_reissues_only_exact_original_publication(self, verify_validator, promote):
        from admin.knowledge_runtime import write_skill_candidate
        from admin.skill_replay_runtime import _deterministic_request_id
        from core.skill_replay_contract import build_skill_replay_binding

        environ = dict(self.environ, **{
            "EVO_SKILL_REPLAY_VALIDATOR_SOCKET": "/run/evo-skill-validator/validator.sock",
            "EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY": str(self.validator_key_path),
            "EVO_SKILL_REPLAY_VALIDATOR_KEY_ID": "validator-test-key",
        })
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=environ)
        skill = self._skill()
        write_skill_candidate(self.workspace, "tenant-a", skill)
        context = {
            "tenant_id": "tenant-a", "mission_run_id": "mission-1",
            "node_id": "node-1", "task_id": "task-1",
        }
        binding = build_skill_replay_binding(skill, context)
        stage_id = "11111111-1111-4111-8111-111111111111"
        execution_id = "22222222-2222-4222-8222-222222222222"
        validation_id = "33333333-3333-4333-8333-333333333333"
        validation_attestation = {
            "validation_id": "validation-1", "validator_id": "validator-independent",
            "policy_id": "policy-1", "policy_sha256": "a" * 64,
            "checks_sha256": "b" * 64,
        }
        verify_validator.return_value = validation_attestation
        promotion_id = _deterministic_request_id("promotion", {
            "mission_context": context,
            "skill_id": skill.id,
            "skill_version": skill.version,
            "content_sha256": binding["content_sha256"],
            "validation_attestation": validation_attestation,
        })
        runtime.broker_request_status = lambda request_id, mission_context: (
            {"status": "indeterminate"} if request_id == promotion_id
            else {"status": "completed", "response": {"receipt": request_id}}
        )
        runtime.validator_request_status = lambda request_id, mission_context: {
            "status": "completed", "response": {"attestation": "original"}
        }
        runtime.verify_recovery_responses = lambda **kwargs: {
            "broker_stage": "verified",
            "broker_execution": "verified",
            "execution_succeeded": True,
            "validator": "verified",
        }
        runtime.adapter.execute = lambda *args, **kwargs: self.fail(
            "promotion recovery must never execute Skill code"
        )
        promote.return_value = {
            "artifact": {"skill_id": skill.id, "skill_version": skill.version},
            "validation_provenance": {"validation_id": "validation-1"},
        }

        result = runtime.resume_promotion(
            tenant_id="tenant-a", mission_run_id="mission-1",
            node_id="node-1", task_id="task-1", skill_id=skill.id,
            skill_binding=binding, stage_request_id=stage_id,
            execution_request_id=execution_id, validation_request_id=validation_id,
            promotion_request_id=promotion_id,
        )

        self.assertEqual(result["status"], "published")
        self.assertEqual(result["promotion_request_id"], promotion_id)
        self.assertEqual(promote.call_args.kwargs["request_id"], promotion_id)
        self.assertEqual(promote.call_args.kwargs["validation_attestation"], validation_attestation)

    def test_resume_promotion_rejects_changed_draft_before_status_queries(self):
        from admin.knowledge_runtime import write_skill_candidate
        from core.skill_replay_contract import build_skill_replay_binding

        environ = dict(self.environ, **{
            "EVO_SKILL_REPLAY_VALIDATOR_SOCKET": "/run/evo-skill-validator/validator.sock",
            "EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY": str(self.validator_key_path),
            "EVO_SKILL_REPLAY_VALIDATOR_KEY_ID": "validator-test-key",
        })
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=environ)
        original = self._skill(version="1.0.0")
        write_skill_candidate(self.workspace, "tenant-a", self._skill(version="1.0.1"))
        context = {
            "tenant_id": "tenant-a", "mission_run_id": "mission-1",
            "node_id": "node-1", "task_id": "task-1",
        }
        original_binding = build_skill_replay_binding(original, context)
        runtime.broker_request_status = lambda *args, **kwargs: self.fail(
            "changed candidate must be rejected before contacting Broker"
        )
        with self.assertRaisesRegex(PermissionError, "changed after"):
            runtime.resume_promotion(
                tenant_id="tenant-a", mission_run_id="mission-1",
                node_id="node-1", task_id="task-1", skill_id=original.id,
                skill_binding=original_binding,
                stage_request_id="11111111-1111-4111-8111-111111111111",
                execution_request_id="22222222-2222-4222-8222-222222222222",
                validation_request_id="33333333-3333-4333-8333-333333333333",
                promotion_request_id="44444444-4444-4444-8444-444444444444",
            )

    def test_resume_promotion_refuses_already_completed_publication(self):
        from admin.knowledge_runtime import write_skill_candidate
        from core.skill_replay_contract import build_skill_replay_binding

        environ = dict(self.environ, **{
            "EVO_SKILL_REPLAY_VALIDATOR_SOCKET": "/run/evo-skill-validator/validator.sock",
            "EVO_SKILL_REPLAY_VALIDATOR_PUBLIC_KEY": str(self.validator_key_path),
            "EVO_SKILL_REPLAY_VALIDATOR_KEY_ID": "validator-test-key",
        })
        runtime = create_skill_replay_runtime(workspace=self.workspace, environ=environ)
        skill = self._skill()
        write_skill_candidate(self.workspace, "tenant-a", skill)
        context = {
            "tenant_id": "tenant-a", "mission_run_id": "mission-1",
            "node_id": "node-1", "task_id": "task-1",
        }
        runtime.broker_request_status = lambda request_id, mission_context: (
            {"status": "completed"} if request_id == "44444444-4444-4444-8444-444444444444"
            else {"status": "completed"}
        )
        with self.assertRaisesRegex(ValueError, "already completed"):
            runtime.resume_promotion(
                tenant_id="tenant-a", mission_run_id="mission-1",
                node_id="node-1", task_id="task-1", skill_id=skill.id,
                skill_binding=build_skill_replay_binding(skill, context),
                stage_request_id="11111111-1111-4111-8111-111111111111",
                execution_request_id="22222222-2222-4222-8222-222222222222",
                validation_request_id="33333333-3333-4333-8333-333333333333",
                promotion_request_id="44444444-4444-4444-8444-444444444444",
            )


if __name__ == "__main__":
    unittest.main()
