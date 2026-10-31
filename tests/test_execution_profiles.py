"""Regression tests for allowlisted execution-profile request validation."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.execution_profiles import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_OUTPUT_BYTES,
    resolve_execution_profile,
)


class ExecutionProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        (self.workspace / "tests").mkdir()
        (self.workspace / "tests" / "test_sample.py").write_text(
            "def test_sample():\n    assert True\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_unittest_profile_uses_only_fixed_module_arguments(self):
        spec = resolve_execution_profile(self.workspace, {
            "profile_id": "python.unittest",
            "target": "tests.test_sample",
        })
        self.assertEqual(
            spec.argv,
            (sys.executable, "-m", "unittest", "tests.test_sample"),
        )
        self.assertEqual(spec.timeout_seconds, DEFAULT_TIMEOUT_SECONDS)
        self.assertEqual(spec.max_output_bytes, MAX_OUTPUT_BYTES)
        self.assertFalse(spec.network_access)

    def test_pytest_profile_resolves_target_inside_workspace(self):
        spec = resolve_execution_profile(self.workspace, {
            "profile_id": "python.pytest",
            "target": "tests/test_sample.py",
            "timeout_seconds": 30,
        })
        self.assertEqual(spec.argv[:3], (sys.executable, "-m", "pytest"))
        self.assertEqual(spec.argv[3], str(self.workspace / "tests" / "test_sample.py"))
        self.assertEqual(spec.timeout_seconds, 30)

    def test_worker_cannot_supply_command_or_arguments(self):
        for extra in (
            {"command": "rm -rf /"},
            {"argv": ["python", "-c", "print(1)"]},
            {"env": {"PYTHONPATH": "/tmp/evil"}},
            {"cwd": "/tmp"},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                resolve_execution_profile(self.workspace, {
                    "profile_id": "python.unittest",
                    "target": "tests.test_sample",
                    **extra,
                })

    def test_unknown_profiles_and_unbounded_timeouts_are_rejected(self):
        with self.assertRaises(ValueError):
            resolve_execution_profile(self.workspace, {
                "profile_id": "python.shell",
                "target": "anything",
            })
        for timeout in (0, 301, True, "30"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                resolve_execution_profile(self.workspace, {
                    "profile_id": "python.unittest",
                    "target": "tests.test_sample",
                    "timeout_seconds": timeout,
                })

    def test_pytest_rejects_traversal_and_symlink_escape(self):
        outside = Path(self.temp.name).parent / "outside-test-target.py"
        outside.write_text("def test_outside(): pass\n", encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                resolve_execution_profile(self.workspace, {
                    "profile_id": "python.pytest",
                    "target": "../outside-test-target.py",
                })
            link = self.workspace / "tests" / "escape.py"
            link.symlink_to(outside)
            with self.assertRaises(ValueError):
                resolve_execution_profile(self.workspace, {
                    "profile_id": "python.pytest",
                    "target": "tests/escape.py",
                })
        finally:
            outside.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
