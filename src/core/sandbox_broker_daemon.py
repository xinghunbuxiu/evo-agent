"""Systemd socket-activated entry point for the privileged sandbox broker."""
from __future__ import annotations

import json
import logging
import os
import signal
import socket
import stat
import threading
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .sandbox_broker import BrokerReplayStore, SandboxBrokerService
from .sandbox_broker_transport import serve_listener
from .sandbox_docker_executor import DockerSandboxExecutor


LOGGER = logging.getLogger("evo.sandbox_broker")
DEFAULT_CONFIG = Path("/etc/evo-sandbox-broker/config.json")
_CONFIG_FIELDS = {
    "workspace_roots", "replay_database", "signing_key", "key_id",
    "image", "allowed_uids", "max_workers",
}


class BrokerDaemonConfigurationError(ValueError):
    """Broker daemon configuration is absent, unsafe, or malformed."""


def _safe_regular_file(path_value: Any, *, field: str) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise BrokerDaemonConfigurationError(f"{field} must be an absolute file path")
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink():
        raise BrokerDaemonConfigurationError(f"{field} must be an absolute non-symlink path")
    try:
        info = path.stat()
    except OSError as exc:
        raise BrokerDaemonConfigurationError(f"{field} is unavailable") from exc
    if not stat.S_ISREG(info.st_mode):
        raise BrokerDaemonConfigurationError(f"{field} must be a regular file")
    return path


def _load_config(path: Path) -> dict:
    config_path = _safe_regular_file(str(path), field="broker config")
    info = config_path.stat()
    if info.st_uid != 0 or info.st_mode & 0o022:
        raise BrokerDaemonConfigurationError(
            "broker config must be root-owned and not group/world writable"
        )
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerDaemonConfigurationError("broker config is not valid JSON") from exc
    if not isinstance(config, dict) or set(config) != _CONFIG_FIELDS:
        raise BrokerDaemonConfigurationError("broker config has unsupported or missing fields")
    return config


def _load_signing_key(path_value: Any) -> Ed25519PrivateKey:
    path = _safe_regular_file(path_value, field="signing_key")
    info = path.stat()
    if info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o077:
        raise BrokerDaemonConfigurationError(
            "signing key must be readable only by root or the broker account"
        )
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, ValueError, TypeError) as exc:
        raise BrokerDaemonConfigurationError("signing key could not be loaded") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise BrokerDaemonConfigurationError("broker signing key must be Ed25519")
    return key


def build_service(config: dict) -> tuple[SandboxBrokerService, tuple[int, ...], int]:
    """Build service only from root-controlled configuration and a pinned image."""
    if not isinstance(config, dict) or set(config) != _CONFIG_FIELDS:
        raise BrokerDaemonConfigurationError("broker config has unsupported or missing fields")
    roots = config["workspace_roots"]
    if not isinstance(roots, dict) or not roots:
        raise BrokerDaemonConfigurationError("workspace_roots must be a non-empty object")
    resolved_roots = {}
    for workspace_id, raw_root in roots.items():
        if not isinstance(raw_root, str):
            raise BrokerDaemonConfigurationError("workspace root must be a path string")
        root = Path(raw_root)
        if not root.is_absolute() or root.is_symlink():
            raise BrokerDaemonConfigurationError("workspace roots must be absolute non-symlink paths")
        try:
            resolved = root.resolve(strict=True)
        except OSError as exc:
            raise BrokerDaemonConfigurationError("registered workspace is unavailable") from exc
        if resolved != root or not resolved.is_dir():
            raise BrokerDaemonConfigurationError("workspace root must be canonical directory path")
        resolved_roots[workspace_id] = resolved

    replay_path = config["replay_database"]
    if not isinstance(replay_path, str) or not Path(replay_path).is_absolute():
        raise BrokerDaemonConfigurationError("replay_database must be an absolute path")
    signing_key = _load_signing_key(config["signing_key"])
    key_id = config["key_id"]
    if not isinstance(key_id, str) or not key_id.strip() or len(key_id) > 128:
        raise BrokerDaemonConfigurationError("key_id is invalid")
    allowed = config["allowed_uids"]
    if (not isinstance(allowed, list) or not allowed
            or any(isinstance(uid, bool) or not isinstance(uid, int) or uid < 0 for uid in allowed)
            or len(set(allowed)) != len(allowed)):
        raise BrokerDaemonConfigurationError("allowed_uids must be unique non-negative integers")
    workers = config["max_workers"]
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 8:
        raise BrokerDaemonConfigurationError("max_workers must be between 1 and 8")

    executor = DockerSandboxExecutor(
        docker_client=DockerSandboxExecutor.connect_docker_socket(),
        image=config["image"],
    )
    service = SandboxBrokerService(
        workspace_roots=resolved_roots,
        replay_store=BrokerReplayStore(Path(replay_path)),
        executor=executor,
        signing_key=signing_key,
        key_id=key_id,
    )
    return service, tuple(allowed), workers


def _systemd_listener() -> socket.socket:
    try:
        listen_pid = int(os.environ.get("LISTEN_PID", "0"))
        listen_fds = int(os.environ.get("LISTEN_FDS", "0"))
    except ValueError as exc:
        raise BrokerDaemonConfigurationError("systemd socket activation metadata is invalid") from exc
    if listen_pid != os.getpid() or listen_fds != 1:
        raise BrokerDaemonConfigurationError("exactly one systemd-activated socket is required")
    listener = socket.fromfd(3, socket.AF_UNIX, socket.SOCK_STREAM)
    if listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM:
        listener.close()
        raise BrokerDaemonConfigurationError("activated broker socket must be stream-oriented")
    return listener


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config_path = Path(os.environ.get("EVO_BROKER_CONFIG", str(DEFAULT_CONFIG)))
    config = _load_config(config_path)
    service, allowed_uids, max_workers = build_service(config)
    listener = _systemd_listener()
    stop = threading.Event()

    def request_stop(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    LOGGER.info("sandbox broker started; allowed_peer_count=%d", len(allowed_uids))
    try:
        serve_listener(
            listener,
            service=service,
            allowed_uids=allowed_uids,
            stop_event=stop,
            max_workers=max_workers,
        )
    finally:
        listener.close()
        try:
            service.replay_store
        except Exception:
            pass
        LOGGER.info("sandbox broker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
