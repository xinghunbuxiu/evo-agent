"""Policy tests for the Docker-backed sandbox executor (no daemon required)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.execution_profiles import resolve_execution_profile
from core.sandbox_docker_executor import (
    DockerSandboxConfigurationError,
    DockerSandboxExecutor,
)


IMAGE = "registry.example/evo/python-runner@sha256:" + ("a" * 64)


class FakeContainer:
    def __init__(self, wait_result=None, logs=(b"stdout", b"stderr"), wait_error=None):
        self.wait_result = wait_result or {"StatusCode": 0}
        self.logs_result = logs
        self.wait_error = wait_error
        self.start_error = None
        self.logs_error = None
        self.remove_error = None
        self.started = False
        self.killed = False
        self.removed = False
        self.create_config = None

    def start(self):
        if self.start_error:
            raise self.start_error
        self.started = True

    def wait(self, timeout):
        self.wait_timeout = timeout
        if self.wait_error:
            raise self.wait_error
        return self.wait_result

    def logs(self, **kwargs):
        self.logs_kwargs = kwargs
        if self.logs_error:
            raise self.logs_error
        return self.logs_result

    def kill(self):
        self.killed = True

    def remove(self, **kwargs):
        self.removed = True
        if self.remove_error:
            raise self.remove_error


class FakeContainers:
    def __init__(self, container):
        self.container = container
        self.config = None

    def create(self, **kwargs):
        self.config = kwargs
        self.container.create_config = kwargs
        return self.container


class FakeDockerClient:
    def __init__(self, container):
        self.containers = FakeContainers(container)


class DockerSandboxExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "test_sample.py").write_text("def test_ok(): pass\n", encoding="utf-8")
        self.spec = resolve_execution_profile(self.root, {
            "profile_id": "python.pytest", "target": "test_sample.py",
            "timeout_seconds": 7,
        })
        self.container = FakeContainer()
        self.client = FakeDockerClient(self.container)
        self.executor = DockerSandboxExecutor(docker_client=self.client, image=IMAGE)

    def tearDown(self):
        self.temp.cleanup()

    def test_creates_container_with_fixed_isolation_policy(self):
        result = self.executor(self.spec)
        config = self.client.containers.config
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(config["image"], IMAGE)
        self.assertEqual(config["command"], [
            "/usr/local/bin/python", "-m", "pytest", "-p", "no:cacheprovider",
            "/workspace/test_sample.py",
        ])
        self.assertEqual(config["network_mode"], "none")
        self.assertTrue(config["init"])
        self.assertIn("-p", config["command"])
        self.assertEqual(config["environment"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")
        self.assertTrue(config["read_only"])
        self.assertEqual(config["volumes"][str(self.root.resolve())]["mode"], "ro")
        self.assertEqual(config["cap_drop"], ["ALL"])
        self.assertEqual(config["security_opt"], ["no-new-privileges:true"])
        self.assertEqual(config["mem_limit"], 512 * 1024 * 1024)
        self.assertEqual(config["memswap_limit"], 512 * 1024 * 1024)
        self.assertEqual(config["shm_size"], 32 * 1024 * 1024)
        self.assertEqual(config["pids_limit"], 128)
        self.assertTrue(self.container.removed)

    def test_output_is_bounded(self):
        self.container.logs_result = (b"a" * 200, b"b" * 200)
        spec = self.spec.__class__(
            **{**self.spec.__dict__, "max_output_bytes": 256}
        )
        result = self.executor(spec)
        self.assertEqual(len(result.stdout) + len(result.stderr), 256)

    def test_bounded_streams_preserves_both_streams_when_stdout_is_larger(self):
        stdout, stderr = DockerSandboxExecutor._bounded_streams(
            (b"o" * 200, b"e" * 200), 100,
        )
        self.assertEqual(len(stdout), 50)
        self.assertEqual(len(stderr), 50)
        self.assertEqual(stdout, b"o" * 50)
        self.assertEqual(stderr, b"e" * 50)

    def test_bounded_streams_borrows_unused_stderr_capacity(self):
        stdout, stderr = DockerSandboxExecutor._bounded_streams(
            (b"o" * 100, b"e" * 10), 100,
        )
        self.assertEqual(stdout, b"o" * 90)
        self.assertEqual(stderr, b"e" * 10)

    def test_bounded_streams_borrows_unused_stdout_capacity(self):
        stdout, stderr = DockerSandboxExecutor._bounded_streams(
            (b"o" * 10, b"e" * 100), 100,
        )
        self.assertEqual(stdout, b"o" * 10)
        self.assertEqual(stderr, b"e" * 90)

    def test_bounded_streams_never_exceeds_limit(self):
        stdout, stderr = DockerSandboxExecutor._bounded_streams(
            (b"o" * 500, b"e" * 500), 127,
        )
        self.assertEqual(len(stdout) + len(stderr), 127)

    def test_rejects_tag_only_image(self):
        with self.assertRaises(DockerSandboxConfigurationError):
            DockerSandboxExecutor(docker_client=self.client, image="python:3.12")

    def test_rejects_forged_command_target(self):
        forged = self.spec.__class__(
            **{**self.spec.__dict__, "target": "../etc/passwd"}
        )
        with self.assertRaises(DockerSandboxConfigurationError):
            self.executor(forged)

    def test_timeout_kills_container_and_returns_timed_out_observation(self):
        self.container.wait_error = TimeoutError("wait timed out")
        result = self.executor(self.spec)
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.exit_code)
        self.assertTrue(self.container.killed)
        self.assertTrue(self.container.removed)

    def test_nonzero_exit_is_preserved(self):
        self.container.wait_result = {"StatusCode": 3}
        result = self.executor(self.spec)
        self.assertEqual(result.exit_code, 3)

    def test_start_failure_still_removes_created_container(self):
        self.container.start_error = RuntimeError("start failed")
        with self.assertRaisesRegex(RuntimeError, "start failed"):
            self.executor(self.spec)
        self.assertTrue(self.container.removed)

    def test_invalid_wait_status_fails_closed_and_removes_container(self):
        self.container.wait_result = {"StatusCode": True}
        with self.assertRaisesRegex(RuntimeError, "invalid wait result"):
            self.executor(self.spec)
        self.assertTrue(self.container.removed)

    def test_log_collection_failure_does_not_return_execution_result(self):
        self.container.logs_error = RuntimeError("logs unavailable")
        with self.assertRaisesRegex(RuntimeError, "logs unavailable"):
            self.executor(self.spec)
        self.assertTrue(self.container.removed)

    def test_cleanup_failure_prevents_success_result(self):
        self.container.remove_error = RuntimeError("cleanup failed")
        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            self.executor(self.spec)
        self.assertTrue(self.container.removed)


if __name__ == "__main__":
    unittest.main()
