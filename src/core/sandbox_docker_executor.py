"""Docker-backed execution adapter with fixed, non-worker-configurable isolation.

The caller must run this adapter only inside the separately provisioned broker
service account, whose Docker socket access is protected by host policy.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

from .execution_profiles import ExecutionProfileSpec
from .sandbox_runner import RunnerProcessOutput


_IMAGE_DIGEST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:[0-9a-f]{64}$")
_MAX_MEMORY_BYTES = 512 * 1024 * 1024
_MAX_CPU_NANOS = 1_000_000_000
_MAX_PIDS = 128
_TMPFS_SIZE_BYTES = 64 * 1024 * 1024
_SKILL_REPLAY_OUTPUT_SCHEMA = "mission.skill-replay-output.v1"
_SKILL_REPLAY_BOOTSTRAP = r'''
import contextlib
import io
import json
import pathlib
import sys

captured = io.StringIO()
try:
    context = json.loads(pathlib.Path("/replay/context.json").read_text(encoding="utf-8"))
    source = pathlib.Path("/replay/skill.py").read_text(encoding="utf-8")
    namespace = {"__name__": "__evo_skill__", "__file__": "/replay/skill.py"}
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        exec(compile(source, "/replay/skill.py", "exec"), namespace, namespace)
        entry = namespace.get("run")
        if not callable(entry):
            raise TypeError("Skill Replay requires a callable run(context) entrypoint")
        value = entry(context)
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 16384:
            raise ValueError("Skill Replay result exceeds the 16 KiB limit")
    payload = {"schema_version": "mission.skill-replay-output.v1", "success": True,
               "value": value, "error": None, "logs": captured.getvalue()[-8192:]}
    exit_code = 0
except Exception as exc:
    payload = {"schema_version": "mission.skill-replay-output.v1", "success": False,
               "value": None, "error": {"type": type(exc).__name__, "message": str(exc)[:240]},
               "logs": captured.getvalue()[-8192:]}
    exit_code = 1
sys.stdout.write(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
sys.stdout.flush()
sys.exit(exit_code)
'''


class DockerSandboxConfigurationError(ValueError):
    """Docker sandbox policy is incomplete or unsafe."""


class DockerSandboxExecutor:
    """Execute only registered Python profiles in a digest-pinned Docker image."""

    def __init__(
        self,
        *,
        docker_client: Any,
        image: str,
        workspace_container_path: str = "/workspace",
        replay_staging_root: Path | None = None,
    ):
        if not isinstance(image, str) or not _IMAGE_DIGEST_RE.fullmatch(image):
            raise DockerSandboxConfigurationError(
                "sandbox image must be pinned by an immutable sha256 digest"
            )
        if workspace_container_path != "/workspace":
            raise DockerSandboxConfigurationError("workspace mount path is fixed")
        self.docker_client = docker_client
        self.image = image
        self.replay_staging_root = None
        if replay_staging_root is not None:
            staging_root = Path(replay_staging_root)
            if not staging_root.is_absolute() or staging_root.is_symlink():
                raise DockerSandboxConfigurationError("Skill Replay staging root must be absolute and non-symlink")
            try:
                info = staging_root.lstat()
            except OSError as exc:
                raise DockerSandboxConfigurationError("Skill Replay staging root is unavailable") from exc
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                    or info.st_mode & 0o077 or staging_root.resolve(strict=True) != staging_root):
                raise DockerSandboxConfigurationError("Skill Replay staging root must be broker-owned, private and canonical")
            self.replay_staging_root = staging_root
        try:
            from docker.types import LogConfig
            self.log_config = LogConfig(
                type="json-file", config={"max-size": "1m", "max-file": "1"},
            )
        except ImportError:
            # Unit tests can inject a fake Docker client without installing the SDK.
            self.log_config = {"type": "json-file", "config": {"max-size": "1m", "max-file": "1"}}

    @staticmethod
    def _command(spec: ExecutionProfileSpec) -> list[str]:
        if spec.profile_id == "python.pytest":
            target = spec.target
            if (
                not target or target.startswith("/") or "\\" in target
                or ":" in target or any(part in {"", ".", ".."} for part in target.split("/"))
            ):
                raise DockerSandboxConfigurationError("pytest target is not workspace-relative")
            return ["/usr/local/bin/python", "-m", "pytest", "-p", "no:cacheprovider", "/workspace/" + target]
        if spec.profile_id == "python.unittest":
            target = spec.target
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9]*(?:\.[A-Za-z_][A-Za-z0-9]*)*", target):
                raise DockerSandboxConfigurationError("unittest target is not a dotted module")
            return ["/usr/local/bin/python", "-m", "unittest", target]
        raise DockerSandboxConfigurationError("unsupported sandbox execution profile")

    @staticmethod
    def _bounded_streams(logs: Any, limit: int) -> tuple[bytes, bytes, int, int]:
        if isinstance(logs, tuple) and len(logs) == 2:
            stdout, stderr = logs
        else:
            stdout, stderr = logs, b""
        stdout = stdout or b""
        stderr = stderr or b""
        if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
            raise TypeError("Docker logs must be bytes")
        # Reserve capacity for both streams so a verbose stdout cannot hide
        # all stderr diagnostics. Unused capacity is borrowed by the other stream.
        stdout_budget = limit // 2
        stderr_budget = limit - stdout_budget
        stdout_kept = stdout[:stdout_budget]
        stderr_kept = stderr[:stderr_budget]
        remaining = limit - len(stdout_kept) - len(stderr_kept)
        if remaining:
            stdout_extra = stdout[stdout_budget:stdout_budget + remaining]
            stdout_kept += stdout_extra
            remaining -= len(stdout_extra)
        if remaining:
            stderr_kept += stderr[stderr_budget:stderr_budget + remaining]
        return stdout_kept, stderr_kept, len(stdout), len(stderr)

    @staticmethod
    def connect_docker_socket(socket_path: str = "/var/run/docker.sock") -> Any:
        """Create an SDK client bound to the broker-only Unix socket."""
        if socket_path != "/var/run/docker.sock":
            raise DockerSandboxConfigurationError("Docker socket path is fixed by broker policy")
        try:
            import docker
        except ImportError as exc:
            raise DockerSandboxConfigurationError(
                "Docker SDK is missing; install requirements-broker.txt in the broker environment"
            ) from exc
        client = docker.DockerClient(
            base_url="unix:///var/run/docker.sock", version="auto", timeout=10,
        )
        client.ping()
        return client

    @staticmethod
    def _write_replay_input(path: Path, payload: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o400)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o444)

    def execute_skill_replay(
        self,
        skill: Any,
        mission_context: dict[str, str],
        *,
        timeout_seconds: int,
    ) -> RunnerProcessOutput:
        """Run one validator-signed Skill in a dedicated, networkless container."""
        if self.replay_staging_root is None:
            raise DockerSandboxConfigurationError("trusted Skill Replay staging root is not configured")
        code = getattr(skill, "code", None)
        digest = getattr(skill, "content_sha256", None)
        if not isinstance(code, str) or not code.strip():
            raise DockerSandboxConfigurationError("trusted Skill artifact has no executable Python source")
        code_bytes = code.encode("utf-8", errors="strict")
        if hashlib.sha256(code_bytes).hexdigest() != digest:
            raise DockerSandboxConfigurationError("trusted Skill source digest changed before replay")
        if not isinstance(mission_context, dict):
            raise DockerSandboxConfigurationError("Skill Replay Mission context must be an object")
        context_bytes = json.dumps(
            mission_context, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
        if len(code_bytes) > 256 * 1024 or len(context_bytes) > 32 * 1024:
            raise DockerSandboxConfigurationError("Skill Replay input exceeds its configured size limit")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 300:
            raise DockerSandboxConfigurationError("Skill Replay timeout is outside broker policy")

        stage_dir = Path(tempfile.mkdtemp(prefix="evo-skill-replay-", dir=self.replay_staging_root))
        container = None
        timed_out = False
        exit_code = None
        stdout = b""
        stderr = b""
        stdout_total = 0
        stderr_total = 0
        try:
            self._write_replay_input(stage_dir / "skill.py", code_bytes)
            self._write_replay_input(stage_dir / "context.json", context_bytes)
            os.chmod(stage_dir, 0o555)
            container = self.docker_client.containers.create(
                image=self.image,
                command=["/usr/local/bin/python", "-I", "-S", "-c", _SKILL_REPLAY_BOOTSTRAP],
                name=None,
                hostname=None,
                user="65532:65532",
                working_dir="/tmp",
                environment={
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUNBUFFERED": "1",
                    "HOME": "/tmp",
                    "PYTHONNOUSERSITE": "1",
                },
                volumes={str(stage_dir): {"bind": "/replay", "mode": "ro"}},
                read_only=True,
                network_mode="none",
                privileged=False,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit=_MAX_MEMORY_BYTES,
                memswap_limit=_MAX_MEMORY_BYTES,
                nano_cpus=_MAX_CPU_NANOS,
                shm_size=32 * 1024 * 1024,
                pids_limit=_MAX_PIDS,
                ipc_mode="private",
                tmpfs={
                    "/tmp": (
                        f"rw,noexec,nosuid,nodev,size={_TMPFS_SIZE_BYTES},"
                        "mode=1777"
                    ),
                },
                log_config=self.log_config,
                labels={"com.evo-agent.sandbox": "true", "com.evo-agent.skill-replay": "true"},
                detach=True,
                auto_remove=False,
                stdin_open=False,
                tty=False,
                init=True,
            )
            container.start()
            try:
                wait_result = container.wait(timeout=timeout_seconds)
                if not isinstance(wait_result, dict) or isinstance(wait_result.get("StatusCode"), bool):
                    raise RuntimeError("Docker returned an invalid Skill Replay wait result")
                exit_code = wait_result.get("StatusCode")
                if not isinstance(exit_code, int) or exit_code < 0:
                    raise RuntimeError("Docker returned an invalid Skill Replay exit status")
            except Exception as exc:
                try:
                    from requests.exceptions import ReadTimeout
                    timeout_error = isinstance(exc, (TimeoutError, ReadTimeout))
                except ImportError:
                    timeout_error = isinstance(exc, TimeoutError)
                if not timeout_error:
                    raise
                timed_out = True
                try:
                    container.kill()
                except Exception:
                    pass
            logs = container.logs(stdout=True, stderr=True, demux=True)
            stdout, stderr, stdout_total, stderr_total = self._bounded_streams(logs, 256 * 1024)
            if not timed_out:
                try:
                    envelope = json.loads(stdout.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise DockerSandboxConfigurationError("Skill Replay runner returned an invalid output envelope") from exc
                if (not isinstance(envelope, dict)
                        or set(envelope) != {"schema_version", "success", "value", "error", "logs"}
                        or envelope.get("schema_version") != _SKILL_REPLAY_OUTPUT_SCHEMA
                        or not isinstance(envelope.get("success"), bool)
                        or not isinstance(envelope.get("logs"), str)
                        or len(envelope["logs"].encode("utf-8")) > 8192):
                    raise DockerSandboxConfigurationError("Skill Replay runner output envelope is malformed")
                if envelope["success"]:
                    if exit_code != 0 or envelope.get("error") is not None:
                        raise DockerSandboxConfigurationError("Skill Replay success envelope conflicts with process status")
                    try:
                        encoded_value = json.dumps(
                            envelope.get("value"), ensure_ascii=False, allow_nan=False,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    except (TypeError, ValueError) as exc:
                        raise DockerSandboxConfigurationError("Skill Replay returned a non-JSON result") from exc
                    if len(encoded_value) > 16 * 1024:
                        raise DockerSandboxConfigurationError("Skill Replay result exceeds the 16 KiB limit")
                else:
                    error = envelope.get("error")
                    if (exit_code == 0 or not isinstance(error, dict)
                            or set(error) != {"type", "message"}
                            or not isinstance(error.get("type"), str)
                            or not isinstance(error.get("message"), str)
                            or len(error["message"]) > 240):
                        raise DockerSandboxConfigurationError("Skill Replay failure envelope conflicts with process status")
            return RunnerProcessOutput(
                exit_code=None if timed_out else exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                stdout_available_bytes=stdout_total,
                stderr_available_bytes=stderr_total,
            )
        finally:
            try:
                if container is not None:
                    container.remove(force=True, v=True)
            finally:
                try:
                    os.chmod(stage_dir, 0o700)
                    shutil.rmtree(stage_dir)
                except OSError as exc:
                    raise DockerSandboxConfigurationError("Skill Replay staging cleanup failed") from exc

    def __call__(self, spec: ExecutionProfileSpec) -> RunnerProcessOutput:
        if not isinstance(spec, ExecutionProfileSpec):
            raise TypeError("Docker sandbox requires an ExecutionProfileSpec")
        workspace = Path(spec.cwd).resolve(strict=True)
        if not workspace.is_dir():
            raise DockerSandboxConfigurationError("workspace root must be a directory")
        if (isinstance(spec.max_output_bytes, bool) or not isinstance(spec.max_output_bytes, int)
                or not 1 <= spec.max_output_bytes <= 256 * 1024):
            raise DockerSandboxConfigurationError("output limit is outside the broker policy")
        command = self._command(spec)
        container = None
        timed_out = False
        exit_code = None
        try:
            container = self.docker_client.containers.create(
                image=self.image,
                command=command,
                name=None,
                hostname=None,
                user="65532:65532",
                working_dir="/workspace",
                environment={
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUNBUFFERED": "1",
                    "HOME": "/tmp",
                    "PYTHONNOUSERSITE": "1",
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                },
                volumes={
                    str(workspace): {"bind": "/workspace", "mode": "ro"},
                },
                read_only=True,
                network_mode="none",
                privileged=False,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit=_MAX_MEMORY_BYTES,
                memswap_limit=_MAX_MEMORY_BYTES,
                nano_cpus=_MAX_CPU_NANOS,
                shm_size=32 * 1024 * 1024,
                pids_limit=_MAX_PIDS,
                ipc_mode="private",
                tmpfs={
                    "/tmp": (
                        f"rw,noexec,nosuid,nodev,size={_TMPFS_SIZE_BYTES},"
                        "mode=1777"
                    ),
                },
                log_config=self.log_config,
                labels={"com.evo-agent.sandbox": "true"},
                detach=True,
                auto_remove=False,
                stdin_open=False,
                tty=False,
                init=True,
            )
            container.start()
            try:
                result = container.wait(timeout=spec.timeout_seconds)
                if not isinstance(result, dict) or isinstance(result.get("StatusCode"), bool):
                    raise RuntimeError("Docker returned an invalid wait result")
                exit_code = result.get("StatusCode")
                if not isinstance(exit_code, int) or exit_code < 0:
                    raise RuntimeError("Docker returned an invalid exit status")
            except Exception as exc:
                # Docker SDK surfaces daemon/API timeouts through requests' ReadTimeout.
                # Do not reinterpret arbitrary daemon errors as successful execution.
                try:
                    from requests.exceptions import ReadTimeout
                    timeout_error = isinstance(exc, (TimeoutError, ReadTimeout))
                except ImportError:
                    timeout_error = isinstance(exc, TimeoutError)
                if not timeout_error:
                    raise
                timed_out = True
                try:
                    container.kill()
                except Exception:
                    pass
            logs = container.logs(stdout=True, stderr=True, demux=True)
            stdout, stderr, stdout_total, stderr_total = self._bounded_streams(logs, spec.max_output_bytes)
            return RunnerProcessOutput(
                exit_code=None if timed_out else exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                stdout_available_bytes=stdout_total,
                stderr_available_bytes=stderr_total,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True, v=True)
                except Exception:
                    # Cleanup errors must not turn an observed success into a success
                    # claim; surface the failure so the broker returns a generic error.
                    raise


__all__ = ["DockerSandboxExecutor", "DockerSandboxConfigurationError"]
