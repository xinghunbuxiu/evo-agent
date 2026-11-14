"""Standalone system service for independent Skill validation."""
from __future__ import annotations

import argparse
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

from .skill_validator import SkillValidatorError, SkillValidatorRequestStore, SkillValidatorService
from .skill_validator_transport import serve_validator_listener

LOGGER = logging.getLogger("evo.skill_validator")
DEFAULT_CONFIG = Path("/etc/evo-skill-validator/config.json")
_CONFIG_FIELDS = {
    "socket_path", "policy_file", "signing_key", "key_id", "validator_id",
    "broker_public_key", "broker_key_id", "allowed_uids", "workspace_ids",
    "replay_store_path", "max_workers",
}


class SkillValidatorDaemonConfigurationError(ValueError):
    """Validator service configuration is absent, unsafe, or malformed."""


def _regular_file(path_value: Any, *, field: str, max_bytes: int = 2 * 1024 * 1024) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise SkillValidatorDaemonConfigurationError(f"{field} must be a file path")
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink():
        raise SkillValidatorDaemonConfigurationError(f"{field} must be absolute and non-symlink")
    try:
        info = path.lstat()
    except OSError as exc:
        raise SkillValidatorDaemonConfigurationError(f"{field} is unavailable") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
        raise SkillValidatorDaemonConfigurationError(f"{field} must be a bounded regular file")
    if info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o022:
        raise SkillValidatorDaemonConfigurationError(f"{field} must be service/root-owned and not group/world writable")
    return path


def _load_json_file(path_value: Any, *, field: str) -> dict:
    path = _regular_file(path_value, field=field)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkillValidatorDaemonConfigurationError(f"{field} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise SkillValidatorDaemonConfigurationError(f"{field} must contain a JSON object")
    return value


def build_service(config: dict) -> tuple[SkillValidatorService, tuple[int, ...], int]:
    if not isinstance(config, dict) or set(config) != _CONFIG_FIELDS:
        raise SkillValidatorDaemonConfigurationError("Validator config has unsupported or missing fields")
    policies = _load_json_file(config["policy_file"], field="policy_file")
    key_path = _regular_file(config["signing_key"], field="signing_key", max_bytes=16 * 1024)
    try:
        private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    except (OSError, ValueError, TypeError) as exc:
        raise SkillValidatorDaemonConfigurationError("Validator private key could not be loaded") from exc
    if not isinstance(private_key, Ed25519PrivateKey):
        raise SkillValidatorDaemonConfigurationError("Validator private key must be Ed25519")
    key_info = key_path.stat()
    if key_info.st_mode & 0o077:
        raise SkillValidatorDaemonConfigurationError("Validator private key must be mode 0600 or stricter")
    broker_key_path = _regular_file(config["broker_public_key"], field="broker_public_key", max_bytes=32)
    broker_public_key = broker_key_path.read_bytes()
    if len(broker_public_key) != 32:
        raise SkillValidatorDaemonConfigurationError("Broker public key must contain 32 raw Ed25519 bytes")
    allowed_uids = config["allowed_uids"]
    if (
        not isinstance(allowed_uids, list) or not allowed_uids
        or any(isinstance(uid, bool) or not isinstance(uid, int) or uid < 0 for uid in allowed_uids)
        or len(set(allowed_uids)) != len(allowed_uids)
    ):
        raise SkillValidatorDaemonConfigurationError("allowed_uids must be unique non-negative integers")
    workspace_ids = config["workspace_ids"]
    if not isinstance(workspace_ids, list) or not workspace_ids:
        raise SkillValidatorDaemonConfigurationError("workspace_ids must be a non-empty list")
    workers = config["max_workers"]
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 16:
        raise SkillValidatorDaemonConfigurationError("max_workers must be between 1 and 16")
    try:
        service = SkillValidatorService(
            validator_id=config["validator_id"], key_id=config["key_id"],
            signing_key=private_key, broker_public_key=broker_public_key,
            broker_key_id=config["broker_key_id"], workspace_ids=workspace_ids,
            policies=policies.get("policies"),
            request_store=SkillValidatorRequestStore(config["replay_store_path"]),
        )
    except (SkillValidatorError, TypeError) as exc:
        raise SkillValidatorDaemonConfigurationError("Validator identity or policy configuration is invalid") from exc
    return service, tuple(allowed_uids), workers


def run(config_path: Path = DEFAULT_CONFIG) -> None:
    config = _load_json_file(str(config_path), field="config")
    service, allowed_uids, workers = build_service(config)
    socket_path = Path(config["socket_path"])
    if not socket_path.is_absolute() or socket_path.parent.is_symlink():
        raise SkillValidatorDaemonConfigurationError("socket_path must be absolute with a non-symlink parent")
    socket_path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    if socket_path.parent.resolve(strict=True) != socket_path.parent:
        raise SkillValidatorDaemonConfigurationError("Validator socket directory must be canonical")
    parent_info = socket_path.parent.stat()
    if parent_info.st_uid not in {0, os.geteuid()} or parent_info.st_mode & 0o022:
        raise SkillValidatorDaemonConfigurationError("Validator socket directory ownership or permissions are unsafe")
    if socket_path.exists() or socket_path.is_symlink():
        info = socket_path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid not in {0, os.geteuid()}:
            raise SkillValidatorDaemonConfigurationError("existing Validator socket path is not a service-owned socket")
        socket_path.unlink()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    os.chmod(socket_path, 0o660)
    listener.listen(max(8, workers * 2))
    stop = threading.Event()

    def request_stop(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    LOGGER.info("independent Skill Validator listening on %s", socket_path)
    try:
        serve_validator_listener(
            listener, service=service, allowed_uids=allowed_uids,
            stop_event=stop, max_workers=workers,
        )
    finally:
        listener.close()
        socket_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent Skill Validator daemon")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run(args.config)


if __name__ == "__main__":
    main()
