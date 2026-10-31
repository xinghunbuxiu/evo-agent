"""Tests for bounded, digest-only trusted runner result normalization."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.execution_profiles import MAX_OUTPUT_BYTES, resolve_execution_profile
from core.execution_results import EXECUTION_RESULT_SCHEMA, build_execution_result


class ExecutionResultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        (self.workspace / "tests").mkdir()
        (self.workspace / "tests" / "test_sample.py").write_text(
            "def test_sample():\n    assert True\n", encoding="utf-8"
        )
        self.spec = resolve_execution_profile(self.workspace, {
            "profile_id": "python.pytest",
            "target": "tests/test_sample.py",
        })

    def tearDown(self):
        self.temp.cleanup()

    def test_success_result_contains_runner_identity_and_output_digests(self):
        result = build_execution_result(
            self.spec,
            runner_id="sandbox-01",
            runner_version="1.2.3",
            exit_code=0,
            stdout=b"1 passed",
            stderr=b"",
        )
        self.assertEqual(result["schema_version"], EXECUTION_RESULT_SCHEMA)
        self.assertEqual(result["runner"], {"id": "sandbox-01", "version": "1.2.3"})
        self.assertEqual(result["target"], "tests/test_sample.py")
        self.assertTrue(result["execution_succeeded"])
        self.assertEqual(result["stdout"]["bytes"], 8)
        self.assertEqual(len(result["stdout"]["sha256"]), 64)
        self.assertNotIn("1 passed", str(result))

    def test_failure_and_timeout_never_become_success(self):
        failed = build_execution_result(
            self.spec, runner_id="sandbox-01", runner_version="1",
            exit_code=2, stdout=b"", stderr=b"failed",
        )
        timed_out = build_execution_result(
            self.spec, runner_id="sandbox-01", runner_version="1",
            exit_code=None, stdout=b"", stderr=b"", timed_out=True,
        )
        self.assertFalse(failed["execution_succeeded"])
        self.assertFalse(timed_out["execution_succeeded"])

    def test_invalid_exit_codes_and_timeout_combinations_are_rejected(self):
        invalid = (
            {"exit_code": True, "timed_out": False},
            {"exit_code": -1, "timed_out": False},
            {"exit_code": None, "timed_out": False},
            {"exit_code": 0, "timed_out": True},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                build_execution_result(
                    self.spec, runner_id="runner", runner_version="1",
                    stdout=b"", stderr=b"", **values,
                )

    def test_output_limit_and_runner_identity_are_enforced(self):
        with self.assertRaises(ValueError):
            build_execution_result(
                self.spec, runner_id="runner", runner_version="1", exit_code=0,
                stdout=b"x" * (MAX_OUTPUT_BYTES + 1), stderr=b"",
            )
        with self.assertRaises(ValueError):
            build_execution_result(
                self.spec, runner_id="", runner_version="1", exit_code=0,
                stdout=b"", stderr=b"",
            )
        with self.assertRaises(ValueError):
            build_execution_result(
                self.spec, runner_id="runner", runner_version="1", exit_code=0,
                stdout="not bytes", stderr=b"",
            )


if __name__ == "__main__":
    unittest.main()
