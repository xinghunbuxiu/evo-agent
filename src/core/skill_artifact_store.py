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
import base64
import binascii
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


ARTIFACT_SCHEMA = "mission.skill-artifact.v1"
VALIDATION_ATTESTATION_SCHEMA = "mission.skill-validation-attestation.v1"
VALIDATION_SIGNATURE_ALGORITHM = "ed25519"
_ATTESTATION_FIELDS = {
    "schema_version", "validation_id", "validator_id", "tenant_id",
    "skill_id", "skill_version", "content_sha256", "trust_level", "passed", "signature",
}
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
    mode 0700). Publication requires a detached Ed25519 attestation from the
    independently trusted validator; a caller-supplied trust_level is not proof.
    """

    def __init__(self, root: Path, *, validator_public_key: bytes, validator_key_id: str):
        self.root = _secure_directory(Path(root), create=False)
        if not isinstance(validator_key_id, str) or not validator_key_id.strip():
            raise SkillArtifactStoreError("validator_key_id is required")
        try:
            self.validator_public_key = Ed25519PublicKey.from_public_bytes(validator_public_key)
        except (ValueError, TypeError) as exc:
            raise SkillArtifactStoreError("validator public key is invalid") from exc
        self.validator_key_id = validator_key_id

    def _verify_validation_attestation(
        self, attestation: Any, *, tenant_id: str, skill_id: str,
        version: str, digest: str, trust_level: str,
    ) -> None:
        if not isinstance(attestation, Mapping) or set(attestation) != _ATTESTATION_FIELDS:
            raise SkillArtifactStoreError("validation attestation has unsupported or missing fields")
        if attestation.get("schema_version") != VALIDATION_ATTESTATION_SCHEMA:
            raise SkillArtifactStoreError("unsupported validation attestation schema")
        if attestation.get("passed") is not True:
            raise SkillArtifactStoreError("Skill validation attestation did not pass")
        for field in ("validation_id", "validator_id"):
            _identity(attestation.get(field), field, _ID_RE)
        expected = {
            "tenant_id": tenant_id,
            "skill_id": skill_id,
            "skill_version": version,
            "content_sha256": digest,
            "trust_level": trust_level,
        }
        if any(attestation.get(field) != value for field, value in expected.items()):
            raise SkillArtifactStoreError("validation attestation does not bind this exact Skill artifact")
        signature = attestation.get("signature")
        if not isinstance(signature, Mapping) or set(signature) != {"algorithm", "key_id", "value"}:
            raise SkillArtifactStoreError("validation attestation signature metadata is invalid")
        if signature.get("algorithm") != VALIDATION_SIGNATURE_ALGORITHM or signature.get("key_id") != self.validator_key_id:
            raise SkillArtifactStoreError("validation attestation signer is not trusted")
        encoded = signature.get("value")
        if not isinstance(encoded, str) or not encoded:
            raise SkillArtifactStoreError("validation attestation signature is missing")
        payload = {key: attestation[key] for key in _ATTESTATION_FIELDS if key != "signature"}
        try:
            self.validator_public_key.verify(base64.b64decode(encoded, validate=True), _canonical_json(payload))
        except (ValueError, TypeError, binascii.Error, InvalidSignature) as exc:
            raise SkillArtifactStoreError("validation attestation signature verification failed") from exc

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

    def publish(self, *, tenant_id: str, skill: Any, validation_attestation: Mapping[str, Any]) -> dict[str, str]:
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
        normalized_tenant = _identity(tenant_id, "tenant_id", _ID_RE)
        self._verify_validation_attestation(
            validation_attestation, tenant_id=normalized_tenant,
            skill_id=skill_id, version=version, digest=digest, trust_level=trust,
        )
        artifact = {
            "schema_version": ARTIFACT_SCHEMA,
            "tenant_id": normalized_tenant,
            "skill_id": skill_id,
            "skill_version": version,
            "trust_level": trust,
            "content_sha256": digest,
            "code": code,
            # Persist the signed validator statement so the Broker can re-verify
            # provenance using only its pinned public key at every load.
            "validation_attestation": dict(validation_attestation),
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
        for field in ("mission_run_id", "node_id", "task_id"):
            _identity(context.get(field), field, _ID_RE)
        skill_id = _identity(binding.get("skill_id"), "skill_id", _ID_RE)
        version = _identity(binding.get("skill_version"), "skill_version", _VERSION_RE)
        expected_digest = binding.get("content_sha256")
        if not isinstance(expected_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
            raise SkillArtifactStoreError("Skill replay content digest is invalid")
        expected_trust = binding.get("trust_level")
        if not isinstance(expected_trust, str) or expected_trust not in _TRUST_LEVELS:
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
            "trust_level", "content_sha256", "code", "validation_attestation",
        }
        if not isinstance(artifact, dict) or set(artifact) != fields:
            raise SkillArtifactStoreError("stored Skill artifact has unsupported or missing fields")
        code = artifact.get("code")
        if not isinstance(code, str) or not code.strip():
            raise SkillArtifactStoreError("stored Skill artifact code is invalid")
        try:
            actual_digest = hashlib.sha256(code.encode("utf-8", errors="strict")).hexdigest()
        except UnicodeError as exc:
            raise SkillArtifactStoreError("stored Skill artifact code is not valid UTF-8") from exc
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
        # Re-check the independent validator signature on every broker load.
        # A matching file digest alone is not proof that this Skill was validated.
        self._verify_validation_attestation(
            artifact.get("validation_attestation"),
            tenant_id=tenant_id,
            skill_id=skill_id,
            version=version,
            digest=actual_digest,
            trust_level=expected_trust,
        )
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
    "VALIDATION_ATTESTATION_SCHEMA",
    "SkillArtifactStore",
    "SkillArtifactStoreError",
]
