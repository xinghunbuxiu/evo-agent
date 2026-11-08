"""Tests for broker-side request policy, replay prevention, and signing."""
import base64
import hashlib
import json
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.skill_artifact_store import SkillArtifactStore, VALIDATION_ATTESTATION_SCHEMA
from core.sandbox_broker import (
    BrokerReplayStore,
    BrokerRequestRejected,
    SandboxBrokerService,
    validate_broker_request,
)
from core.sandbox_broker_protocol import (
    SKILL_REPLAY_PROFILE_ID,
    build_broker_request,
    verify_broker_response,
)
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
        self.skill_calls = []
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
            "project-test", self.spec, mission_context={"tenant_id": "tenant-test", "mission_run_id": "mission-test", "node_id": "node-test", "task_id": "task-test"}, request_id=self.request_id,
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
            expected_workspace_id="project-test",
            expected_mission_context={"tenant_id": "tenant-test", "mission_run_id": "mission-test", "node_id": "node-test", "task_id": "task-test"},
            expected_profile_id="python.pytest",
            expected_target="tests/test_sample.py",
        )
        self.assertTrue(result["execution_succeeded"])
        self.assertEqual(len(self.calls), 1)

    def _trusted_skill_service(self):
        artifact_root = Path(self.temp.name) / "trusted-artifacts"
        artifact_root.mkdir(mode=0o700)
        validator_key = Ed25519PrivateKey.generate()
        store = SkillArtifactStore(
            artifact_root,
            validator_public_key=validator_key.public_key().public_bytes_raw(),
            validator_key_id="validator-test-key",
        )
        skill = SimpleNamespace(
            id="skill-python-demo",
            version="1.0.0",
            code="def run(context):\n    return {'tenant_id': context['tenant_id'], 'ok': True}\n",
            trust_level="verified",
        )
        digest = hashlib.sha256(skill.code.encode("utf-8")).hexdigest()
        statement = {
            "schema_version": VALIDATION_ATTESTATION_SCHEMA,
            "validation_id": "validation-skill-demo",
            "validator_id": "independent-validator",
            "tenant_id": "tenant-test",
            "skill_id": skill.id,
            "skill_version": skill.version,
            "content_sha256": digest,
            "trust_level": "verified",
            "passed": True,
        }
        signature = validator_key.sign(json.dumps(
            statement, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8"))
        attestation = {
            **statement,
            "signature": {
                "algorithm": "ed25519",
                "key_id": "validator-test-key",
                "value": base64.b64encode(signature).decode("ascii"),
            },
        }
        store.publish(tenant_id="tenant-test", skill=skill, validation_attestation=attestation)
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": skill.id,
            "skill_version": skill.version,
            "content_sha256": digest,
            "trust_level": "verified",
            "mission_context": {
                "tenant_id": "tenant-test",
                "mission_run_id": "mission-test",
                "node_id": "node-test",
                "task_id": "task-test",
            },
        }
        service = SandboxBrokerService(
            workspace_roots={"project-test": self.root},
            replay_store=self.store,
            executor=self._execute,
            signing_key=self.key,
            key_id="broker-test-key",
            skill_artifact_store=store,
            skill_replay_executor=self._execute_skill_replay,
        )
        return service, binding

    def _execute_skill_replay(self, skill, mission_context, *, timeout_seconds):
        self.skill_calls.append((skill, mission_context, timeout_seconds))
        return RunnerProcessOutput(
            exit_code=0,
            stdout=b'{"schema_version":"mission.skill-replay-output.v1","success":true}',
            stderr=b"",
        )

    def test_trusted_skill_replay_uses_dedicated_executor_and_signed_binding(self):
        service, binding = self._trusted_skill_service()
        request = build_broker_request(
            "project-test", self.spec, mission_context=binding["mission_context"],
            request_id=str(uuid.uuid4()), skill_binding=binding,
        )
        response = service.handle_request(request)
        result = verify_broker_response(
            response,
            public_key=self.key.public_key().public_bytes_raw(),
            expected_key_id="broker-test-key",
            expected_request_id=request["request_id"],
            expected_workspace_id="project-test",
            expected_mission_context=binding["mission_context"],
            expected_profile_id=SKILL_REPLAY_PROFILE_ID,
            expected_target=f"{binding['skill_id']}@{binding['skill_version']}",
            expected_skill_binding=binding,
        )
        self.assertTrue(result["execution_succeeded"])
        self.assertEqual(len(self.skill_calls), 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(response["skill_artifact"]["content_sha256"], binding["content_sha256"])

    def test_skill_replay_is_tenant_isolated_and_rejects_missing_artifact(self):
        service, binding = self._trusted_skill_service()
        other_context = {**binding["mission_context"], "tenant_id": "tenant-other"}
        other_binding = {**binding, "mission_context": other_context}
        request = build_broker_request(
            "project-test", self.spec, mission_context=other_context,
            request_id=str(uuid.uuid4()), skill_binding=other_binding,
        )
        with self.assertRaisesRegex(BrokerRequestRejected, "independent verification"):
            service.handle_request(request)
        self.assertEqual(self.skill_calls, [])

    def test_skill_replay_request_id_cannot_be_reused(self):
        service, binding = self._trusted_skill_service()
        request = build_broker_request(
            "project-test", self.spec, mission_context=binding["mission_context"],
            request_id=str(uuid.uuid4()), skill_binding=binding,
        )
        service.handle_request(request)
        with self.assertRaisesRegex(BrokerRequestRejected, "already been used"):
            service.handle_request(request)
        self.assertEqual(len(self.skill_calls), 1)

    def test_response_skill_binding_is_bound_to_broker_signature_and_caller_expectation(self):
        service, binding = self._trusted_skill_service()
        request = build_broker_request(
            "project-test", self.spec, mission_context=binding["mission_context"],
            request_id=str(uuid.uuid4()), skill_binding=binding,
        )
        response = service.handle_request(request)
        response["skill_binding"] = {**response["skill_binding"], "skill_version": "9.9.9"}
        with self.assertRaisesRegex(ValueError, "Skill binding"):
            verify_broker_response(
                response,
                public_key=self.key.public_key().public_bytes_raw(),
                expected_key_id="broker-test-key",
                expected_request_id=request["request_id"],
                expected_workspace_id="project-test",
                expected_mission_context=binding["mission_context"],
                expected_profile_id=SKILL_REPLAY_PROFILE_ID,
                expected_target=f"{binding['skill_id']}@{binding['skill_version']}",
                expected_skill_binding=binding,
            )

    def test_skill_binding_is_rejected_until_dedicated_replay_executor_exists(self):
        context = {
            "tenant_id": "tenant-test", "mission_run_id": "mission-test",
            "node_id": "node-test", "task_id": "task-test",
        }
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill-demo", "skill_version": "1.0.0",
            "content_sha256": "a" * 64, "trust_level": "verified",
            "mission_context": context,
        }
        request = build_broker_request(
            "project-test", self.spec, mission_context=context,
            request_id=str(uuid.uuid4()), skill_binding=binding,
        )
        with self.assertRaisesRegex(BrokerRequestRejected, "Skill Artifact Store or isolated Skill Replay executor is not configured"):
            self.service.handle_request(request)
        # Crucially, a generic pytest target must not run under a Skill binding.
        self.assertEqual(self.calls, [])

    def test_skill_binding_fails_closed_without_trusted_artifact_store(self):
        context = {
            "tenant_id": "tenant-test", "mission_run_id": "mission-test",
            "node_id": "node-test", "task_id": "task-test",
        }
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": "skill-untrusted", "skill_version": "1.0.0",
            "content_sha256": "a" * 64, "trust_level": "verified",
            "mission_context": context,
        }
        request = build_broker_request(
            "project-test", self.spec, mission_context=context,
            request_id=str(uuid.uuid4()), skill_binding=binding,
        )
        with self.assertRaisesRegex(BrokerRequestRejected, "Skill Replay executor is not configured"):
            self.service.handle_request(request)
        self.assertEqual(self.calls, [])

    def test_replay_is_rejected_before_second_execution(self):
        self.service.handle_request(self.request)
        with self.assertRaisesRegex(BrokerRequestRejected, "already been used"):
            self.service.handle_request(self.request)
        self.assertEqual(len(self.calls), 1)

    def test_service_rejects_workspace_with_untrusted_writable_parent(self):
        self.root.parent.chmod(0o777)
        with self.assertRaisesRegex(ValueError, "parent"):
            SandboxBrokerService(
                workspace_roots={"project-test": self.root},
                replay_store=self.store, executor=self._execute,
                signing_key=self.key, key_id="broker-test-key",
            )

    def test_replay_store_allows_only_one_concurrent_claim(self):
        outcomes = []
        barrier = threading.Barrier(4)
        def claim():
            barrier.wait()
            try:
                self.store.claim(self.request_id, self.request)
                outcomes.append("claimed")
            except BrokerRequestRejected:
                outcomes.append("rejected")
        threads = [threading.Thread(target=claim) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(outcomes.count("claimed"), 1)
        self.assertEqual(outcomes.count("rejected"), 3)

    def test_service_rejects_symlink_workspace_root(self):
        link = Path(self.temp.name) / "workspace-link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "absolute and non-symlink"):
            SandboxBrokerService(
                workspace_roots={"project-test": link},
                replay_store=self.store, executor=self._execute,
                signing_key=self.key, key_id="broker-test-key",
            )

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

    def test_rejects_missing_or_cross_task_identity_before_execution(self):
        missing = dict(self.request)
        missing.pop("mission_context")
        with self.assertRaisesRegex(BrokerRequestRejected, "unsupported or missing"):
            self.service.handle_request(missing)
        malformed = dict(self.request, mission_context={"tenant_id": "tenant-test"})
        with self.assertRaisesRegex(BrokerRequestRejected, "mission_context"):
            self.service.handle_request(malformed)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
