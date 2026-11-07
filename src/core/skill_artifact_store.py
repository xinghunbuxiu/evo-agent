"""Broker-side immutable storage for independently validated Skill artifacts.

The store is deliberately separate from tenant workspaces and SkillRegistry
caches. Its directory must be provisioned with broker-only write permissions.
Artifacts are create-once; publishing a changed Skill requires a new version.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


ARTIFACT_SCHEMA = "mission.skill-artifact.v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
_TRUST_LEVELS = {"verified", "cloud"}
_BINDING_FIELDS = {
    "schema_version", "skill_id", "skill_version", "content_sha256",
    "trust_level", "mission_context",
}


class SkillArtifactStoreError(ValueError):
    """A Skill artifact cannot be safely published or loaded."""


def _identity(value: Any, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise SkillArtifactStoreError(f"{field} is invalid")
    return value


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _secure_directory(path: Path, *, create: bool) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise SkillArtifactStoreError("artifact store path must be absolute and non-symlink")
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        info = path.lstat()
    except OSError as exc:
        raise SkillArtifactStoreError("artifact store directory is unavailable") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise SkillArtifactStoreError("artifact store path must be a real directory")
    if info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o077:
        raise SkillArtifactStoreError(
            "artifact store directory must be broker-owned and inaccessible to group/other"
        )
    resolved = path.resolve(strict=True)
    if resolved != path:
        raise SkillArtifactStoreError("artifact store path must be canonical")
    return resolved


class SkillArtifactStore:
    """Create-once Skill artifact store rooted outside tenant workspaces.

    The deployment must provision the root directory as broker-owned (normally
    mode 0700) and expose writes only to the trusted validation/promotion path.
    This class does not itself decide whether a Skill passed independent tests;
    it accepts only the verified/cloud trust states after that policy gate.
    """

    def __init__(self, root: Path):
        self.root = _secure_directory(Path(root), create=False)

    def _artifact_path(self, tenant_id: str, skill_id: str, version: str, *, create: bool) -> Path:
        tenant = _identity(tenant_id, "tenant_id", _ID_RE)
        skill = _identity(skill_id, "skill_id", _ID_RE)
        revision = _identity(version, "skill_version", _VERSION_RE)
        tenant_dir = self.root / tenant
        skill_dir = tenant_dir / skill
        # Never follow a pre-created symlink in any path component.
        for directory in (tenant_dir, skill_dir):
            if directory.exists() or directory.is_symlink():
                info = directory.lstat()
                if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    raise SkillArtifactStoreError("artifact path contains a non-directory or symlink")
                if info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o077:
                    raise SkillArtifactStoreError("artifact path directory permissions are unsafe")
            elif create:
                directory.mkdir(mode=0o700)
            else:
                raise SkillArtifactStoreError("trusted Skill artifact directory is unavailable")
        return skill_dir / f"{revision}.json"

    def publish(self, *, tenant_id: str, skill: Any) -> dict[str, str]:
        """Atomically publish a verified Skill once; existing versions never mutate."""
        skill_id = _identity(getattr(skill, "id", None), "skill_id", _ID_RE)
        version = _identity(getattr(skill, "version", None), "skill_version", _VERSION_RE)
        code = getattr(skill, "code", None)
        if not isinstance(code, str) or not code.strip():
            raise SkillArtifactStoreError("skill code must be a non-empty UTF-8 string")
        try:
            code_bytes = code.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise SkillArtifactStoreError("skill code is not valid UTF-8") from exc
        trust = getattr(getattr(skill, "trust_level", None), "value", getattr(skill, "trust_level", None))
        if trust not in _TRUST_LEVELS:
            raise SkillArtifactStoreError("only verified or cloud Skills may be published")

        digest = hashlib.sha256(code_bytes).hexdigest()
        artifact = {
            "schema_version": ARTIFACT_SCHEMA,
            "tenant_id": _identity(tenant_id, "tenant_id", _ID_RE),
            "skill_id": skill_id,
            "skill_version": version,
            "trust_level": trust,
            "content_sha256": digest,
            "code": code,
        }
        payload = _canonical_json(artifact)
        path = self._artifact_path(tenant_id, skill_id, version, create=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags, 0o400)
        except FileExistsError as exc:
            raise SkillArtifactStoreError("Skill artifact version already exists; publish a new version") from exc
        except OSError as exc:
            raise SkillArtifactStoreError("Skill artifact could not be created safely") from exc
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(path, 0o400)
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            try:
                path.unlink()
            except OSError:
                pass
            raise
        return {
            "tenant_id": tenant_id,
            "skill_id": skill_id,
            "skill_version": version,
            "content_sha256": digest,
            "trust_level": trust,
        }

    def load_for_binding(self, binding: Any) -> SimpleNamespace:
        """Load and independently verify the exact artifact named by a replay binding."""
        if not isinstance(binding, Mapping) or set(binding) != _BINDING_FIELDS:
            raise SkillArtifactStoreError("Skill replay binding has unsupported or missing fields")
        if binding.get("schema_version") != "mission.skill-replay-binding.v1":
            raise SkillArtifactStoreError("unsupported Skill replay binding schema")
        context = binding.get("mission_context")
        if not isinstance(context, Mapping) or set(context) != {
            "tenant_id", "mission_run_id", "node_id", "task_id",
        }:
            raise SkillArtifactStoreError("Skill replay binding mission context is invalid")
        tenant_id = _identity(context.get("tenant_id"), "tenant_id", _ID_RE)
        skill_id = _identity(binding.get("skill_id"), "skill_id", _ID_RE)
        version = _identity(binding.get("skill_version"), "skill_version", _VERSION_RE)
        expected_digest = binding.get("content_sha256")
        if not isinstance(expected_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
            raise SkillArtifactStoreError("Skill replay content digest is invalid")
        expected_trust = binding.get("trust_level")
        if expected_trust not in _TRUST_LEVELS:
            raise SkillArtifactStoreError("Skill replay trust level is not executable")

        path = self._artifact_path(tenant_id, skill_id, version, create=False)
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise SkillArtifactStoreError("Skill artifact must be a regular non-symlink file")
            if info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o222:
                raise SkillArtifactStoreError("Skill artifact must be broker-owned and read-only")
            raw = path.read_bytes()
            artifact = json.loads(raw.decode("utf-8"))
        except SkillArtifactStoreError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SkillArtifactStoreError("trusted Skill artifact is unavailable or malformed") from exc

        fields = {
            "schema_version", "tenant_id", "skill_id", "skill_version",
            "trust_level", "content_sha256", "code",
        }
        if not isinstance(artifact, dict) or set(artifact) != fields:
            raise SkillArtifactStoreError("stored Skill artifact has unsupported or missing fields")
        code = artifact.get("code")
        if not isinstance(code, str) or not code.strip():
            raise SkillArtifactStoreError("stored Skill artifact code is invalid")
        actual_digest = hashlib.sha256(code.encode("utf-8", errors="strict")).hexdigest()
        expected = {
            "schema_version": ARTIFACT_SCHEMA,
            "tenant_id": tenant_id,
            "skill_id": skill_id,
            "skill_version": version,
            "trust_level": expected_trust,
            "content_sha256": expected_digest,
        }
        if any(artifact.get(key) != value for key, value in expected.items()):
            raise SkillArtifactStoreError("stored Skill artifact identity does not match replay binding")
        if actual_digest != expected_digest or artifact.get("content_sha256") != actual_digest:
            raise SkillArtifactStoreError("stored Skill artifact content digest mismatch")
        return SimpleNamespace(
            id=skill_id,
            version=version,
            code=code,
            trust_level=expected_trust,
            tenant_id=tenant_id,
            content_sha256=actual_digest,
        )


__all__ = [
    "ARTIFACT_SCHEMA",
    "SkillArtifactStore",
    "SkillArtifactStoreError",
]
