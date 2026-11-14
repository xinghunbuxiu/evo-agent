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

    def _skill_replay_container_options(self, *, command, labels, volumes=None) -> dict:
        """Return the single fixed container policy used by Replay and startup probes."""
        options = {
            "image": self.image,
            "command": command,
            "name": None,
            "hostname": None,
            "user": "65532:65532",
            "working_dir": "/tmp",
            "environment": {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                "HOME": "/tmp",
                "PYTHONNOUSERSITE": "1",
            },
            "read_only": True,
            "network_mode": "none",
            "privileged": False,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "mem_limit": _MAX_MEMORY_BYTES,
            "memswap_limit": _MAX_MEMORY_BYTES,
            "nano_cpus": _MAX_CPU_NANOS,
            "shm_size": 32 * 1024 * 1024,
            "pids_limit": _MAX_PIDS,
            "ipc_mode": "private",
            "tmpfs": {
                "/tmp": (
                    f"rw,noexec,nosuid,nodev,size={_TMPFS_SIZE_BYTES},"
                    "mode=1777"
                ),
            },
            "log_config": self.log_config,
            "labels": dict(labels),
            "detach": True,
            "auto_remove": False,
            "stdin_open": False,
            "tty": False,
            "init": True,
        }
        if volumes is not None:
            options["volumes"] = volumes
        return options

    def _verify_container_isolation(self, container: Any, *, expected_mounts) -> None:
        """Inspect the created container before start; reject policy drift."""
        try:
            container.reload()
            attributes = container.attrs
        except Exception as exc:
            raise DockerSandboxConfigurationError(
                "Docker could not confirm the created container isolation policy"
            ) from exc
        if not isinstance(attributes, dict):
            raise DockerSandboxConfigurationError("Docker container inspection is malformed")
        config = attributes.get("Config")
        host = attributes.get("HostConfig")
        mounts = attributes.get("Mounts")
        if not isinstance(config, dict) or not isinstance(host, dict) or not isinstance(mounts, list):
            raise DockerSandboxConfigurationError("Docker container inspection is incomplete")

        if config.get("User") != "65532:65532" or config.get("Tty") is not False or config.get("OpenStdin") is not False:
            raise DockerSandboxConfigurationError("Docker container identity or interactive settings are unsafe")
        required_host_values = {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "Privileged": False,
            "Memory": _MAX_MEMORY_BYTES,
            "MemorySwap": _MAX_MEMORY_BYTES,
            "NanoCpus": _MAX_CPU_NANOS,
            "PidsLimit": _MAX_PIDS,
            "ShmSize": 32 * 1024 * 1024,
            "IpcMode": "private",
            "AutoRemove": False,
        }
        if any(host.get(key) != value for key, value in required_host_values.items()):
            raise DockerSandboxConfigurationError("Docker did not apply the required resource or isolation policy")
        if set(host.get("CapDrop") or []) != {"ALL"} or host.get("CapAdd") not in (None, []):
            raise DockerSandboxConfigurationError("Docker capability policy is unsafe")
        security_options = host.get("SecurityOpt")
        if not isinstance(security_options, list) or "no-new-privileges:true" not in security_options:
            raise DockerSandboxConfigurationError("Docker no-new-privileges policy is missing")
        if host.get("Devices") not in (None, []) or host.get("DeviceRequests") not in (None, []):
            raise DockerSandboxConfigurationError("Docker device access is not permitted")
        if host.get("VolumesFrom") not in (None, []):
            raise DockerSandboxConfigurationError("Docker inherited mounts are not permitted")
        if host.get("PidMode") not in (None, "", "private"):
            raise DockerSandboxConfigurationError("Docker host or shared PID namespace is not permitted")

        tmpfs = host.get("Tmpfs")
        if not isinstance(tmpfs, dict) or set(tmpfs) != {"/tmp"}:
            raise DockerSandboxConfigurationError("Docker writable temporary filesystem policy is invalid")
        tmpfs_options = set(str(tmpfs["/tmp"]).split(","))
        if not {
            "rw", "noexec", "nosuid", "nodev",
            f"size={_TMPFS_SIZE_BYTES}", "mode=1777",
        }.issubset(tmpfs_options):
            raise DockerSandboxConfigurationError("Docker temporary filesystem is not sufficiently restricted")

        allowed_system_mounts = {"/etc/hosts", "/etc/hostname", "/etc/resolv.conf"}
        actual_mounts = []
        for mount in mounts:
            if not isinstance(mount, dict):
                raise DockerSandboxConfigurationError("Docker mount inspection is malformed")
            destination = mount.get("Destination")
            if destination in allowed_system_mounts:
                continue
            if mount.get("Type") != "bind" or mount.get("RW") is not False:
                raise DockerSandboxConfigurationError("Docker contains an unexpected writable or non-bind mount")
            actual_mounts.append((mount.get("Source"), destination))
        expected = [(str(Path(source).resolve()), destination) for source, destination in expected_mounts]
        if sorted(actual_mounts) != sorted(expected):
            raise DockerSandboxConfigurationError("Docker mount set does not match the exact read-only input contract")

    def _verify_daemon_capabilities(self) -> None:
        """Require seccomp and cgroup resource enforcement before accepting work."""
        try:
            info = self.docker_client.info()
        except Exception as exc:
            raise DockerSandboxConfigurationError("Docker daemon security capabilities are unavailable") from exc
        if not isinstance(info, dict):
            raise DockerSandboxConfigurationError("Docker daemon information is malformed")
        security_options = info.get("SecurityOptions")
        if (
            not isinstance(security_options, list)
            or not any(
                "seccomp" in str(option).lower() and "unconfined" not in str(option).lower()
                for option in security_options
            )
        ):
            raise DockerSandboxConfigurationError("Docker daemon does not report an enforced seccomp profile")
        for feature in ("MemoryLimit", "SwapLimit", "CpuCfsQuota", "PidsLimit"):
            if info.get(feature) is not True:
                raise DockerSandboxConfigurationError(
                    f"Docker daemon does not confirm required cgroup feature: {feature}"
                )
        if str(info.get("CgroupVersion") or "") not in {"1", "2"}:
            raise DockerSandboxConfigurationError("Docker cgroup version is unavailable")

    def verify_runtime_ready(self) -> bool:
        """Prove the pinned image and fixed isolation policy work before daemon startup."""
        self._verify_daemon_capabilities()
        try:
            image = self.docker_client.images.get(self.image)
        except Exception as exc:
            raise DockerSandboxConfigurationError(
                "the exact digest-pinned Skill Replay image is not available locally"
            ) from exc
        image_attributes = getattr(image, "attrs", None)
        repo_digests = image_attributes.get("RepoDigests") if isinstance(image_attributes, dict) else None
        if not isinstance(repo_digests, list) or self.image not in repo_digests:
            raise DockerSandboxConfigurationError(
                "Docker image inspection did not confirm the exact configured repository digest"
            )

        container = None
        try:
            container = self.docker_client.containers.create(
                **self._skill_replay_container_options(
                    command=["/usr/local/bin/python", "-I", "-S", "-c", "pass"],
                    labels={
                        "com.evo-agent.sandbox": "true",
                        "com.evo-agent.skill-replay": "preflight",
                    },
                )
            )
            self._verify_container_isolation(container, expected_mounts=[])
            container.start()
            result = container.wait(timeout=10)
            if (
                not isinstance(result, dict)
                or isinstance(result.get("StatusCode"), bool)
                or result.get("StatusCode") != 0
            ):
                raise DockerSandboxConfigurationError(
                    "isolated Skill Replay preflight container did not exit successfully"
                )
        except DockerSandboxConfigurationError:
            raise
        except Exception as exc:
            raise DockerSandboxConfigurationError(
                "isolated Skill Replay preflight container could not complete"
            ) from exc
        finally:
            if container is not None:
                try:
                    container.remove(force=True, v=True)
                except Exception as exc:
                    raise DockerSandboxConfigurationError(
                        "isolated Skill Replay preflight container cleanup failed"
                    ) from exc
        return True

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
                **self._skill_replay_container_options(
                    command=["/usr/local/bin/python", "-I", "-S", "-c", _SKILL_REPLAY_BOOTSTRAP],
                    volumes={str(stage_dir): {"bind": "/replay", "mode": "ro"}},
                    labels={"com.evo-agent.sandbox": "true", "com.evo-agent.skill-replay": "true"},
                )
            )
            self._verify_container_isolation(
                container, expected_mounts=[(str(stage_dir), "/replay")],
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
            self._verify_container_isolation(
                container, expected_mounts=[(str(workspace), "/workspace")],
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
