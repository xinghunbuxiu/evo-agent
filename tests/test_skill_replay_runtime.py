"""Regression tests for the opt-in Mission-to-Broker Skill Replay runtime."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core import Skill, SkillTrustLevel
from admin.skill_replay_runtime import (
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
        self.key_path.write_bytes(key.public_key().public_bytes_raw())
        self.key_path.chmod(0o400)
        self.environ = {
            "EVO_SKILL_REPLAY_BROKER_SOCKET": "/run/evo-sandbox-broker.sock",
            "EVO_SKILL_REPLAY_WORKSPACE_ID": "workspace-a",
            "EVO_SKILL_REPLAY_BROKER_PUBLIC_KEY": str(self.key_path),
            "EVO_SKILL_REPLAY_BROKER_KEY_ID": "broker-test-key",
            "EVO_SKILL_REPLAY_EVIDENCE_ROOT": str(self.evidence_root),
        }

    def tearDown(self):
        self.temp.cleanup()

    def _skill(self, *, code="def run(context):\n    return {'ok': True}\n", contract=None):
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
            version="1.0.0",
        )

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


if __name__ == "__main__":
    unittest.main()
