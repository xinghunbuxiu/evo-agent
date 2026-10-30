"""Tests for safe, read-only Mission artifact verification."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.mission_brain import build_mission_brain_contract
from core.verification import normalize_verification_contract, verify_workspace_artifacts


class WorkspaceArtifactVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "hello.py").write_text(
            "def hello():\n    return 'world'\n", encoding="utf-8"
        )
        (self.workspace / "result.json").write_text(
            json.dumps({"tests": {"passed": 3, "failed": 0}}), encoding="utf-8"
        )

    def tearDown(self):
        self.temp.cleanup()

    def _action(self, checks):
        return {
            "verification_contract": {
                "schema_version": "mission.verification.v1",
                "checks": checks,
            }
        }

    def test_verifies_file_presence_content_and_json_value(self):
        action = self._action([
            {"check_id": "source_exists", "type": "file_exists", "path": "src/hello.py"},
            {
                "check_id": "hello_function",
                "type": "file_contains",
                "path": "src/hello.py",
                "expected": "def hello():",
            },
            {
                "check_id": "tests_passed",
                "type": "json_value_equals",
                "path": "result.json",
                "key_path": ["tests", "failed"],
                "expected": 0,
            },
        ])
        evidence = verify_workspace_artifacts(
            workspace=self.workspace,
            tenant_id="tenant-a",
            mission_run={"id": "mission-1"},
            action=action,
            task=SimpleNamespace(id="task-1"),
        )
        self.assertEqual(
            evidence["checks"],
            [
                {"check_id": "source_exists", "passed": True},
                {"check_id": "hello_function", "passed": True},
                {"check_id": "tests_passed", "passed": True},
            ],
        )

    def test_failed_check_is_reported_as_failed(self):
        action = self._action([{
            "check_id": "wrong_content",
            "type": "file_contains",
            "path": "src/hello.py",
            "expected": "def goodbye():",
        }])
        evidence = verify_workspace_artifacts(
            workspace=self.workspace,
            tenant_id="tenant-a",
            mission_run={},
            action=action,
            task=SimpleNamespace(id="task-2"),
        )
        self.assertEqual(evidence["checks"], [{"check_id": "wrong_content", "passed": False}])

    def test_path_traversal_and_symlink_escape_fail_closed(self):
        outside = Path(self.temp.name).parent / "outside-verification-secret.txt"
        outside.write_text("secret", encoding="utf-8")
        try:
            action = self._action([{
                "check_id": "escape",
                "type": "file_exists",
                "path": "../outside-verification-secret.txt",
            }])
            self.assertIsNone(verify_workspace_artifacts(
                workspace=self.workspace,
                tenant_id="tenant-a",
                mission_run={},
                action=action,
                task=SimpleNamespace(id="task-3"),
            ))
            link = self.workspace / "outside-link.txt"
            link.symlink_to(outside)
            action = self._action([{
                "check_id": "symlink_escape",
                "type": "file_exists",
                "path": "outside-link.txt",
            }])
            evidence = verify_workspace_artifacts(
                workspace=self.workspace,
                tenant_id="tenant-a",
                mission_run={},
                action=action,
                task=SimpleNamespace(id="task-4"),
            )
            self.assertEqual(evidence["checks"], [{"check_id": "symlink_escape", "passed": False}])
        finally:
            outside.unlink(missing_ok=True)

    def test_invalid_contract_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_verification_contract({
                "schema_version": "mission.verification.v1",
                "checks": [{
                    "check_id": "run_shell",
                    "type": "shell",
                    "command": "rm -rf /",
                }],
            })

    def test_mission_brain_preserves_validated_contract(self):
        contract = {
            "schema_version": "mission.verification.v1",
            "checks": [{
                "check_id": "source_exists",
                "type": "file_exists",
                "path": "src/hello.py",
            }],
        }
        node = {
            "id": "node-1",
            "status": "ready",
            "reasoning": [],
            "blockers": [],
            "recommended_skill_ids": [],
            "validation_checks": ["source file exists"],
            "verification_contract": contract,
            "decision_trace": [],
            "parallel_safe": False,
        }
        result = build_mission_brain_contract([node])
        self.assertEqual(
            result["node_decisions"][0]["verification_contract"]["checks"][0]["check_id"],
            "source_exists",
        )

    def test_mission_brain_rejects_invalid_contract(self):
        node = {
            "id": "node-1",
            "status": "ready",
            "reasoning": [],
            "blockers": [],
            "recommended_skill_ids": [],
            "validation_checks": [],
            "verification_contract": {
                "schema_version": "mission.verification.v1",
                "checks": [{"check_id": "bad", "type": "shell", "path": "x"}],
            },
            "decision_trace": [],
            "parallel_safe": False,
        }
        with self.assertRaises(ValueError):
            build_mission_brain_contract([node])


if __name__ == "__main__":
    unittest.main()
