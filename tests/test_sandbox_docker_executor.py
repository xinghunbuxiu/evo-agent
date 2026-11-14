"""Policy tests for the Docker-backed sandbox executor (no daemon required)."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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
        self.attrs = {}
        self.attrs_override = {}

    def reload(self):
        return None

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
        mounts = [
            {
                "Type": "bind",
                "Source": str(Path(source).resolve()),
                "Destination": mount["bind"],
                "RW": mount.get("mode") != "ro",
            }
            for source, mount in (kwargs.get("volumes") or {}).items()
        ]
        self.container.attrs = {
            "Config": {
                "User": kwargs.get("user"),
                "Tty": kwargs.get("tty"),
                "OpenStdin": kwargs.get("stdin_open"),
            },
            "HostConfig": {
                "NetworkMode": kwargs.get("network_mode"),
                "ReadonlyRootfs": kwargs.get("read_only"),
                "Privileged": kwargs.get("privileged"),
                "CapDrop": kwargs.get("cap_drop"),
                "CapAdd": kwargs.get("cap_add"),
                "SecurityOpt": kwargs.get("security_opt"),
                "Memory": kwargs.get("mem_limit"),
                "MemorySwap": kwargs.get("memswap_limit"),
                "NanoCpus": kwargs.get("nano_cpus"),
                "PidsLimit": kwargs.get("pids_limit"),
                "ShmSize": kwargs.get("shm_size"),
                "IpcMode": kwargs.get("ipc_mode"),
                "Tmpfs": kwargs.get("tmpfs"),
                "Devices": kwargs.get("devices"),
                "DeviceRequests": kwargs.get("device_requests"),
                "VolumesFrom": kwargs.get("volumes_from"),
                "PidMode": kwargs.get("pid_mode") or "",
                "AutoRemove": kwargs.get("auto_remove"),
            },
            "Mounts": mounts,
        }
        for section, override in self.container.attrs_override.items():
            self.container.attrs.setdefault(section, {}).update(override)
        return self.container


class FakeImages:
    def __init__(self, image):
        self.image = image

    def get(self, reference):
        if reference != IMAGE:
            raise AssertionError("unexpected image reference")
        return self.image


class FakeDockerClient:
    def __init__(self, container):
        self.containers = FakeContainers(container)
        self.info_payload = {
            "SecurityOptions": ["name=seccomp,profile=builtin"],
            "MemoryLimit": True,
            "SwapLimit": True,
            "CpuCfsQuota": True,
            "PidsLimit": True,
            "CgroupVersion": "2",
        }
        self.images = FakeImages(SimpleNamespace(attrs={"RepoDigests": [IMAGE]}))

    def info(self):
        return dict(self.info_payload)


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

    def test_runtime_preflight_verifies_pinned_image_and_real_container_policy(self):
        self.assertTrue(self.executor.verify_runtime_ready())
        config = self.client.containers.config
        self.assertEqual(config["image"], IMAGE)
        self.assertEqual(config["command"], ["/usr/local/bin/python", "-I", "-S", "-c", "pass"])
        self.assertEqual(config["network_mode"], "none")
        self.assertTrue(config["read_only"])
        self.assertEqual(config["cap_drop"], ["ALL"])
        self.assertEqual(config["security_opt"], ["no-new-privileges:true"])
        self.assertTrue(self.container.started)
        self.assertTrue(self.container.removed)
        self.assertEqual(config.get("volumes"), None)

    def test_runtime_preflight_rejects_missing_seccomp_before_container_creation(self):
        self.client.info_payload["SecurityOptions"] = ["name=apparmor"]
        with self.assertRaisesRegex(DockerSandboxConfigurationError, "seccomp"):
            self.executor.verify_runtime_ready()
        self.assertIsNone(self.client.containers.config)

    def test_runtime_preflight_rejects_missing_cgroup_resource_enforcement(self):
        self.client.info_payload["PidsLimit"] = False
        with self.assertRaisesRegex(DockerSandboxConfigurationError, "PidsLimit"):
            self.executor.verify_runtime_ready()
        self.assertIsNone(self.client.containers.config)

    def test_runtime_preflight_rejects_digest_not_reported_by_daemon(self):
        self.client.images.image.attrs["RepoDigests"] = ["registry.example/evo/python-runner@sha256:" + ("c" * 64)]
        with self.assertRaisesRegex(DockerSandboxConfigurationError, "exact configured repository digest"):
            self.executor.verify_runtime_ready()
        self.assertIsNone(self.client.containers.config)

    def test_runtime_preflight_rejects_inspected_host_network_override(self):
        self.container.attrs_override = {"HostConfig": {"NetworkMode": "host"}}
        with self.assertRaisesRegex(DockerSandboxConfigurationError, "resource or isolation policy"):
            self.executor.verify_runtime_ready()
        self.assertFalse(self.container.started)
        self.assertTrue(self.container.removed)

    def test_runtime_preflight_rejects_failed_probe_and_cleans_container(self):
        self.container.wait_result = {"StatusCode": 9}
        with self.assertRaisesRegex(DockerSandboxConfigurationError, "did not exit successfully"):
            self.executor.verify_runtime_ready()
        self.assertTrue(self.container.started)
        self.assertTrue(self.container.removed)

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
        self.assertEqual((result.stdout_available_bytes, result.stderr_available_bytes), (200, 200))

    def test_bounded_streams_preserves_both_streams_when_stdout_is_larger(self):
        stdout, stderr, stdout_total, stderr_total = DockerSandboxExecutor._bounded_streams((b"o" * 200, b"e" * 200), 100)
        self.assertEqual(len(stdout), 50)
        self.assertEqual(len(stderr), 50)
        self.assertEqual(stdout, b"o" * 50)
        self.assertEqual(stderr, b"e" * 50)
        self.assertEqual((stdout_total, stderr_total), (200, 200))

    def test_bounded_streams_borrows_unused_stderr_capacity(self):
        stdout, stderr, _, _ = DockerSandboxExecutor._bounded_streams((b"o" * 100, b"e" * 10), 100)
        self.assertEqual(stdout, b"o" * 90)
        self.assertEqual(stderr, b"e" * 10)

    def test_bounded_streams_borrows_unused_stdout_capacity(self):
        stdout, stderr, _, _ = DockerSandboxExecutor._bounded_streams((b"o" * 10, b"e" * 100), 100)
        self.assertEqual(stdout, b"o" * 10)
        self.assertEqual(stderr, b"e" * 90)

    def test_bounded_streams_never_exceeds_limit(self):
        stdout, stderr, _, _ = DockerSandboxExecutor._bounded_streams((b"o" * 500, b"e" * 500), 127)
        self.assertEqual(len(stdout) + len(stderr), 127)

    def test_result_reports_per_stream_truncation_and_original_byte_counts(self):
        self.container.logs_result = (b"o" * 200, b"e" * 200)
        spec = self.spec.__class__(**{**self.spec.__dict__, "max_output_bytes": 100})
        result = self.executor(spec)
        self.assertEqual((len(result.stdout), len(result.stderr)), (50, 50))
        self.assertEqual((result.stdout_available_bytes, result.stderr_available_bytes), (200, 200))

    def test_skill_replay_uses_a_separate_read_only_networkless_container(self):
        staging = self.root / "trusted-artifacts"
        staging.mkdir(mode=0o700)
        code = "def run(context):\\n    return {'ok': True}\\n"
        skill = SimpleNamespace(
            id="skill-demo",
            version="1.0.0",
            code=code,
            content_sha256=hashlib.sha256(code.encode("utf-8")).hexdigest(),
        )
        envelope = {
            "schema_version": "mission.skill-replay-output.v1",
            "success": True,
            "value": {"ok": True},
            "error": None,
            "logs": "",
        }
        self.container.logs_result = (json.dumps(envelope).encode("utf-8"), b"")
        executor = DockerSandboxExecutor(
            docker_client=self.client, image=IMAGE, replay_staging_root=staging,
        )
        result = executor.execute_skill_replay(
            skill,
            {"tenant_id": "tenant-a", "mission_run_id": "mission-1", "node_id": "node-1", "task_id": "task-1"},
            timeout_seconds=9,
        )
        config = self.client.containers.config
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(config["network_mode"], "none")
        self.assertTrue(config["read_only"])
        self.assertEqual(config["user"], "65532:65532")
        self.assertEqual(config["cap_drop"], ["ALL"])
        self.assertEqual(config["security_opt"], ["no-new-privileges:true"])
        mount = next(iter(config["volumes"].values()))
        self.assertEqual((mount["bind"], mount["mode"]), ("/replay", "ro"))
        self.assertNotIn(str(self.root.resolve()), config["volumes"])
        self.assertIn("-I", config["command"])
        self.assertIn("-S", config["command"])
        self.assertEqual(config["labels"]["com.evo-agent.skill-replay"], "true")
        self.assertTrue(self.container.removed)
        self.assertFalse(Path(next(iter(config["volumes"]))).exists())

    def test_skill_replay_rejects_changed_artifact_digest_before_container_creation(self):
        staging = self.root / "trusted-artifacts"
        staging.mkdir(mode=0o700)
        executor = DockerSandboxExecutor(
            docker_client=self.client, image=IMAGE, replay_staging_root=staging,
        )
        skill = SimpleNamespace(
            id="skill-demo", version="1.0.0", code="def run(context): return True",
            content_sha256="0" * 64,
        )
        with self.assertRaisesRegex(DockerSandboxConfigurationError, "digest changed"):
            executor.execute_skill_replay(
                skill,
                {"tenant_id": "tenant-a", "mission_run_id": "mission-1", "node_id": "node-1", "task_id": "task-1"},
                timeout_seconds=5,
            )
        self.assertIsNone(self.client.containers.config)

    def test_skill_replay_requires_private_broker_staging_root(self):
        skill = SimpleNamespace(
            id="skill-demo", version="1.0.0", code="def run(context): return True",
            content_sha256=hashlib.sha256(b"def run(context): return True").hexdigest(),
        )
        with self.assertRaisesRegex(DockerSandboxConfigurationError, "staging root"):
            self.executor.execute_skill_replay(
                skill,
                {"tenant_id": "tenant-a", "mission_run_id": "mission-1", "node_id": "node-1", "task_id": "task-1"},
                timeout_seconds=5,
            )

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
