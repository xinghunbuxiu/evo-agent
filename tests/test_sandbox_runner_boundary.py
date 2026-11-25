"""Regression tests for the fail-closed sandbox runner adapter boundary."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.sandbox_runner import (
    RunnerProcessOutput,
    SandboxRunnerUnavailable,
    execute_with_sandbox,
)


class FakeSandboxRunner:
    runner_id = "test-sandbox"
    runner_version = "0.1"

    def __init__(self, output=None):
        self.output = output or RunnerProcessOutput(0, b"ok", b"")
        self.received_spec = None

    def execute(self, spec):
        self.received_spec = spec
        return self.output


class SandboxRunnerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        (self.workspace / "tests").mkdir()
        (self.workspace / "tests" / "test_sample.py").write_text(
            "def test_sample():\n    assert True\n", encoding="utf-8"
        )
        self.request = {
            "profile_id": "python.pytest",
            "target": "tests/test_sample.py",
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_runner_fails_closed_without_execution_fallback(self):
        with self.assertRaisesRegex(SandboxRunnerUnavailable, "refusing in-process"):
            execute_with_sandbox(self.workspace, self.request)

    def test_injected_runner_receives_only_resolved_fixed_spec(self):
        runner = FakeSandboxRunner()
        result = execute_with_sandbox(self.workspace, self.request, runner=runner)
        self.assertEqual(
            runner.received_spec.argv[:3],
            (sys.executable, "-m", "pytest"),
        )
        self.assertEqual(result["runner"]["id"], "test-sandbox")
        self.assertTrue(result["execution_succeeded"])
        self.assertNotIn("ok", str(result))

    def test_runner_failure_and_timeout_remain_failures(self):
        failed = execute_with_sandbox(
            self.workspace,
            self.request,
            runner=FakeSandboxRunner(RunnerProcessOutput(2, b"", b"failed")),
        )
        timed_out = execute_with_sandbox(
            self.workspace,
            self.request,
            runner=FakeSandboxRunner(RunnerProcessOutput(None, b"", b"", True)),
        )
        self.assertFalse(failed["execution_succeeded"])
        self.assertFalse(timed_out["execution_succeeded"])

    def test_incomplete_runner_and_unstructured_output_are_rejected(self):
        class Incomplete:
            def execute(self, spec):
                return RunnerProcessOutput(0, b"", b"")

        with self.assertRaises(SandboxRunnerUnavailable):
            execute_with_sandbox(self.workspace, self.request, runner=Incomplete())

        class InvalidOutput(FakeSandboxRunner):
            def execute(self, spec):
                return {"exit_code": 0}

        with self.assertRaises(TypeError):
            execute_with_sandbox(self.workspace, self.request, runner=InvalidOutput())


if __name__ == "__main__":
    unittest.main()
