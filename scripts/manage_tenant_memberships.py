#!/usr/bin/env python3
"""Provision tenant memberships from a trusted server shell (never an HTTP endpoint)."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import pwd
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROLES = {"tenant_admin", "member", "viewer"}
SUBJECT_RE = re.compile(r"^(password|gitee):([1-9][0-9]*)$")


def _read_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    if not isinstance(data, dict):
        raise ValueError("membership registry root must be an object")
    for subject, tenants in data.items():
        if not SUBJECT_RE.fullmatch(subject) or not isinstance(tenants, dict):
            raise ValueError(f"invalid subject entry: {subject}")
        for tenant_id, role in tenants.items():
            if not isinstance(tenant_id, str) or not tenant_id.strip() or role not in ROLES:
                raise ValueError(f"invalid membership: {subject}/{tenant_id}")
    return data


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=Path(os.getenv(
        "EVO_TENANT_MEMBERSHIPS_FILE", ".tenants/memberships.json"
    )))
    sub = parser.add_subparsers(dest="command", required=True)
    set_cmd = sub.add_parser("set", help="create or change a membership")
    set_cmd.add_argument("subject", help="password:<numeric-id> or gitee:<numeric-id>")
    set_cmd.add_argument("tenant_id")
    set_cmd.add_argument("role", choices=sorted(ROLES))
    remove_cmd = sub.add_parser("remove", help="remove a membership")
    remove_cmd.add_argument("subject")
    remove_cmd.add_argument("tenant_id")
    sub.add_parser("list", help="list memberships")
    args = parser.parse_args()

    lock_path = args.file.with_suffix(args.file.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(lock_fd, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        registry = _read_registry(args.file)
        if args.command == "list":
            print(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        if not SUBJECT_RE.fullmatch(args.subject):
            parser.error("subject must be password:<positive-id> or gitee:<positive-id>")
        tenant_id = args.tenant_id.strip()
        if not tenant_id:
            parser.error("tenant_id must not be empty")

        previous = registry.get(args.subject, {}).get(tenant_id)
        if args.command == "set":
            registry.setdefault(args.subject, {})[tenant_id] = args.role
            action, new_role = "set", args.role
        else:
            memberships = registry.get(args.subject)
            if not isinstance(memberships, dict) or tenant_id not in memberships:
                parser.error("membership does not exist")
            del memberships[tenant_id]
            if not memberships:
                del registry[args.subject]
            action, new_role = "remove", None

        audit_path = args.file.with_name("membership-audit.jsonl")
        effective_uid = os.geteuid()
        try:
            effective_username = pwd.getpwuid(effective_uid).pw_name
        except KeyError:
            effective_username = str(effective_uid)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor_username": effective_username,
            "actor_uid": effective_uid,
            "action": action,
            "subject": args.subject,
            "tenant_id": tenant_id,
            "previous_role": previous,
            "new_role": new_role,
        }
        # Record intent first; the applied event is written only after atomic replacement.
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_fd = os.open(audit_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            os.fchmod(audit_fd, 0o600)
            os.write(audit_fd, (json.dumps({**record, "event": "change_requested"}, ensure_ascii=False) + "\n").encode("utf-8"))
            os.fsync(audit_fd)
        finally:
            os.close(audit_fd)

        _atomic_write(args.file, registry)
        audit_fd = os.open(audit_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            os.fchmod(audit_fd, 0o600)
            os.write(audit_fd, (json.dumps({**record, "event": "change_applied"}, ensure_ascii=False) + "\n").encode("utf-8"))
            os.fsync(audit_fd)
        finally:
            os.close(audit_fd)
        print(json.dumps({"ok": True, **record, "registry": str(args.file)}, ensure_ascii=False))
        return 0
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
