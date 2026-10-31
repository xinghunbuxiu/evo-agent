"""Docker-backed execution adapter with fixed, non-worker-configurable isolation.

The caller must run this adapter only inside the separately provisioned broker
service account, whose Docker socket access is protected by host policy.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .execution_profiles import ExecutionProfileSpec
from .sandbox_runner import RunnerProcessOutput


_IMAGE_DIGEST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:[0-9a-f]{64}$")
_MAX_MEMORY_BYTES = 512 * 1024 * 1024
_MAX_CPU_NANOS = 1_000_000_000
_MAX_PIDS = 128
_TMPFS_SIZE_BYTES = 64 * 1024 * 1024


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
    ):
        if not isinstance(image, str) or not _IMAGE_DIGEST_RE.fullmatch(image):
            raise DockerSandboxConfigurationError(
                "sandbox image must be pinned by an immutable sha256 digest"
            )
        if workspace_container_path != "/workspace":
            raise DockerSandboxConfigurationError("workspace mount path is fixed")
        self.docker_client = docker_client
        self.image = image

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
    def _bounded_streams(logs: Any, limit: int) -> tuple[bytes, bytes]:
        if isinstance(logs, tuple) and len(logs) == 2:
            stdout, stderr = logs
        else:
            stdout, stderr = logs, b""
        stdout = stdout or b""
        stderr = stderr or b""
        if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
            raise TypeError("Docker logs must be bytes")
        stdout = stdout[:limit]
        stderr = stderr[:max(0, limit - len(stdout))]
        return stdout, stderr

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

    def __call__(self, spec: ExecutionProfileSpec) -> RunnerProcessOutput:
        if not isinstance(spec, ExecutionProfileSpec):
            raise TypeError("Docker sandbox requires an ExecutionProfileSpec")
        workspace = Path(spec.cwd).resolve(strict=True)
        if not workspace.is_dir():
            raise DockerSandboxConfigurationError("workspace root must be a directory")
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
                nano_cpus=_MAX_CPU_NANOS,
                pids_limit=_MAX_PIDS,
                ipc_mode="private",
                tmpfs={
                    "/tmp": (
                        f"rw,noexec,nosuid,nodev,size={_TMPFS_SIZE_BYTES},"
                        "mode=1777"
                    ),
                },
                log_config={
                    "type": "json-file",
                    "config": {"max-size": "1m", "max-file": "1"},
                },
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
            stdout, stderr = self._bounded_streams(logs, spec.max_output_bytes)
            return RunnerProcessOutput(
                exit_code=None if timed_out else exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
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
