"""Broker-side immutable storage for independently validated Skill artifacts.

The store is deliberately separate from tenant workspaces and SkillRegistry
caches. Its directory must be provisioned with broker-only write permissions.
Artifacts are create-once. Publication uses a same-directory temporary file
and an atomic no-replace hard link, so readers never observe partial contents.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import base64
import binascii
import uuid
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


ARTIFACT_SCHEMA = "mission.skill-artifact.v2"
CANDIDATE_ARTIFACT_SCHEMA = "mission.skill-candidate-artifact.v1"
VALIDATION_ATTESTATION_SCHEMA = "mission.skill-validation-attestation.v3"
VALIDATION_SIGNATURE_ALGORITHM = "ed25519"
_ATTESTATION_FIELDS = {
    "schema_version", "validation_id", "validator_id", "policy_id", "policy_sha256",
    "workspace_id", "tenant_id", "mission_run_id", "node_id", "task_id",
    "broker_request_id", "broker_attestation_sha256", "checks_sha256",
    "skill_id", "skill_version", "content_sha256", "trust_level", "passed", "signature",
}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
_WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
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


def _fsync_directory(path: Path) -> None:
    """Persist a directory entry after creating a tenant/Skill directory."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise SkillArtifactStoreError(
            "artifact directory durability could not be confirmed"
        ) from exc


def _write_create_once(path: Path, payload: bytes, *, collision_message: str) -> None:
    """Publish complete bytes atomically without replacing an existing path.

    The temporary file lives beside the destination, is fsynced and made
    read-only before publication. os.link is an atomic create-if-absent
    operation on the same filesystem; the final name is never opened for
    writing. Filesystems without hard-link support fail closed.
    """
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = None
    try:
        fd = os.open(temporary, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(payload)
            stream.flush()
            os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())

        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError as exc:
            raise SkillArtifactStoreError(collision_message) from exc
        except OSError as exc:
            raise SkillArtifactStoreError(
                "Skill artifact could not be atomically published on this filesystem"
            ) from exc

        # The final name now references a complete, read-only inode. If this
        # fsync fails, retain the complete final file and report uncertain
        # directory durability rather than deleting an already-visible artifact.
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            directory_fd = os.open(path.parent, directory_flags)
            try:
                os.fsync(directory_fd)
                os.unlink(temporary)
                temporary = None
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise SkillArtifactStoreError(
                "Skill artifact is complete but directory durability could not be confirmed"
            ) from exc
    except SkillArtifactStoreError:
        raise
    except OSError as exc:
        raise SkillArtifactStoreError("Skill artifact could not be written safely") from exc
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass



def _existing_create_once_matches(path: Path, payload: bytes, *, collision_message: str) -> bool:
    """Accept a create-once collision only when the existing immutable bytes match."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise SkillArtifactStoreError(
            "existing Skill artifact is unavailable or unsafe"
        ) from exc
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid not in {0, os.geteuid()}
            or info.st_mode & 0o222
            or info.st_size > 2 * 1024 * 1024
        ):
            raise SkillArtifactStoreError("existing Skill artifact is unsafe or oversized")
        chunks = []
        remaining = 2 * 1024 * 1024 + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        existing = b"".join(chunks)
        if len(existing) > 2 * 1024 * 1024:
            raise SkillArtifactStoreError("existing Skill artifact is oversized")
    finally:
        os.close(fd)
    if existing != payload:
        raise SkillArtifactStoreError(collision_message)
    # A concurrent publisher may have linked the final name but not yet
    # completed its directory fsync. Confirm durability before accepting retry.
    _fsync_directory(path.parent)
    return True


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
        expected_workspace_id: str | None = None,
        expected_mission_context: Mapping[str, Any] | None = None,
        expected_broker_request_id: str | None = None,
        expected_broker_attestation_sha256: str | None = None,
    ) -> None:
        if not isinstance(attestation, Mapping) or set(attestation) != _ATTESTATION_FIELDS:
            raise SkillArtifactStoreError("validation attestation has unsupported or missing fields")
        if attestation.get("schema_version") != VALIDATION_ATTESTATION_SCHEMA:
            raise SkillArtifactStoreError("unsupported validation attestation schema")
        if attestation.get("passed") is not True:
            raise SkillArtifactStoreError("Skill validation attestation did not pass")
        for field in ("validation_id", "validator_id"):
            _identity(attestation.get(field), field, _ID_RE)
        _identity(attestation.get("policy_id"), "policy_id", _ID_RE)
        _identity(attestation.get("policy_sha256"), "policy_sha256", _DIGEST_RE)
        workspace_id = _identity(attestation.get("workspace_id"), "workspace_id", _WORKSPACE_ID_RE)
        mission_context = {
            "tenant_id": _identity(attestation.get("tenant_id"), "tenant_id", _ID_RE),
            "mission_run_id": _identity(attestation.get("mission_run_id"), "mission_run_id", _ID_RE),
            "node_id": _identity(attestation.get("node_id"), "node_id", _ID_RE),
            "task_id": _identity(attestation.get("task_id"), "task_id", _ID_RE),
        }
        broker_request_id = _identity(attestation.get("broker_request_id"), "broker_request_id", _UUID_RE)
        broker_attestation_sha256 = _identity(
            attestation.get("broker_attestation_sha256"), "broker_attestation_sha256", _DIGEST_RE,
        )
        _identity(attestation.get("checks_sha256"), "checks_sha256", _DIGEST_RE)
        expected = {
            "tenant_id": tenant_id, "skill_id": skill_id, "skill_version": version,
            "content_sha256": digest, "trust_level": trust_level,
        }
        if any(attestation.get(field) != value for field, value in expected.items()):
            raise SkillArtifactStoreError("validation attestation does not bind this exact Skill artifact")
        if expected_workspace_id is not None and workspace_id != expected_workspace_id:
            raise SkillArtifactStoreError("validation attestation does not bind this workspace")
        if expected_mission_context is not None:
            if not isinstance(expected_mission_context, Mapping) or set(expected_mission_context) != {
                "tenant_id", "mission_run_id", "node_id", "task_id",
            }:
                raise SkillArtifactStoreError("expected Mission context is invalid")
            normalized_context = {
                key: _identity(expected_mission_context[key], f"mission_context.{key}", _ID_RE)
                for key in ("tenant_id", "mission_run_id", "node_id", "task_id")
            }
            if mission_context != normalized_context:
                raise SkillArtifactStoreError("validation attestation does not bind this Mission execution")
        if expected_broker_request_id is not None and broker_request_id != expected_broker_request_id:
            raise SkillArtifactStoreError("validation attestation does not bind this Broker request")
        if expected_broker_attestation_sha256 is not None and broker_attestation_sha256 != expected_broker_attestation_sha256:
            raise SkillArtifactStoreError("validation attestation does not bind this signed Broker response")
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

    def _artifact_path(
        self, tenant_id: str, skill_id: str, version: str, *, create: bool,
        candidate: bool = False,
    ) -> Path:
        tenant = _identity(tenant_id, "tenant_id", _ID_RE)
        skill = _identity(skill_id, "skill_id", _ID_RE)
        revision = _identity(version, "skill_version", _VERSION_RE)
        tenant_dir = self.root / tenant
        skill_dir = tenant_dir / skill
        # Re-check after mkdir races; never follow a pre-created symlink.
        for directory in (tenant_dir, skill_dir):
            if create:
                try:
                    directory.mkdir(mode=0o700)
                except FileExistsError:
                    pass
            try:
                info = directory.lstat()
            except OSError as exc:
                raise SkillArtifactStoreError("trusted Skill artifact directory is unavailable") from exc
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise SkillArtifactStoreError("artifact path contains a non-directory or symlink")
            if info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o077:
                raise SkillArtifactStoreError("artifact path directory permissions are unsafe")
            # Persist the child entry in its parent before creating the next
            # level (tenant first, then Skill directory). Re-fsync existing
            # entries too, so a retry after an earlier fsync failure can recover.
            _fsync_directory(directory.parent)
        suffix = ".candidate.json" if candidate else ".json"
        return skill_dir / f"{revision}{suffix}"

    def publish(
        self, *, tenant_id: str, skill: Any, validation_attestation: Mapping[str, Any],
        workspace_id: str, mission_context: Mapping[str, Any],
        broker_request_id: str, broker_attestation_sha256: str,
    ) -> dict[str, str]:
        """Atomically publish a verified Skill once, bound to its exact replay evidence."""
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
        normalized_tenant = _identity(tenant_id, "tenant_id", _ID_RE)
        normalized_workspace = _identity(workspace_id, "workspace_id", _WORKSPACE_ID_RE)
        if not isinstance(mission_context, Mapping) or set(mission_context) != {
            "tenant_id", "mission_run_id", "node_id", "task_id",
        }:
            raise SkillArtifactStoreError("Mission context has unsupported or missing fields")
        normalized_context = {
            key: _identity(mission_context[key], f"mission_context.{key}", _ID_RE)
            for key in ("tenant_id", "mission_run_id", "node_id", "task_id")
        }
        if normalized_context["tenant_id"] != normalized_tenant:
            raise SkillArtifactStoreError("Mission context tenant does not match Skill artifact tenant")
        normalized_request_id = _identity(broker_request_id, "broker_request_id", _UUID_RE)
        normalized_broker_digest = _identity(broker_attestation_sha256, "broker_attestation_sha256", _DIGEST_RE)
        digest = hashlib.sha256(code_bytes).hexdigest()
        self._verify_validation_attestation(
            validation_attestation, tenant_id=normalized_tenant,
            skill_id=skill_id, version=version, digest=digest, trust_level=trust,
            expected_workspace_id=normalized_workspace,
            expected_mission_context=normalized_context,
            expected_broker_request_id=normalized_request_id,
            expected_broker_attestation_sha256=normalized_broker_digest,
        )
        artifact = {
            "schema_version": ARTIFACT_SCHEMA,
            "tenant_id": normalized_tenant,
            "skill_id": skill_id,
            "skill_version": version,
            "trust_level": trust,
            "content_sha256": digest,
            "code": code,
            "validation_attestation": dict(validation_attestation),
        }
        payload = _canonical_json(artifact)
        path = self._artifact_path(normalized_tenant, skill_id, version, create=True)
        collision_message = "Skill artifact version already exists; publish a new version"
        try:
            _write_create_once(
                path, payload, collision_message=collision_message,
            )
        except SkillArtifactStoreError as exc:
            if str(exc) != collision_message:
                raise
            # A retry after a lost Broker response is successful only if the
            # immutable file is byte-for-byte identical, including the signed
            # Validator attestation and Mission/Broker evidence lineage.
            _existing_create_once_matches(
                path, payload, collision_message=collision_message,
            )

        # Do not let the Broker issue a successful promotion receipt based only
        # on the intended in-memory payload. Re-open the final immutable path and
        # independently verify its metadata, content digest, and Validator
        # attestation before reporting publication success.
        binding = {
            "schema_version": "mission.skill-replay-binding.v1",
            "skill_id": skill_id,
            "skill_version": version,
            "content_sha256": digest,
            "trust_level": trust,
            "mission_context": normalized_context,
        }
        try:
            persisted = self.load_for_binding(binding)
        except Exception as exc:
            raise SkillArtifactStoreError(
                "published Skill artifact failed readback verification"
            ) from exc
        if (
            getattr(persisted, "id", None) != skill_id
            or getattr(persisted, "version", None) != version
            or getattr(persisted, "tenant_id", None) != normalized_tenant
            or getattr(persisted, "trust_level", None) != trust
            or getattr(persisted, "content_sha256", None) != digest
            or getattr(persisted, "code", None) != code
        ):
            raise SkillArtifactStoreError(
                "published Skill artifact readback does not match the requested immutable identity"
            )
        return {
            "tenant_id": normalized_tenant,
            "skill_id": skill_id,
            "skill_version": version,
            "content_sha256": digest,
            "trust_level": trust,
        }

    def stage_candidate(self, *, tenant_id: str, skill: Any) -> dict[str, str]:
        """Stage an immutable draft for isolated replay; this does not validate or publish it.

        Candidate artifacts are stored separately from verified artifacts and can
        only be resolved through the Skill Replay broker profile. The broker's
        sandbox remains the execution boundary; no trust is inferred from staging.
        """
        skill_id = _identity(getattr(skill, "id", None), "skill_id", _ID_RE)
        version = _identity(getattr(skill, "version", None), "skill_version", _VERSION_RE)
        code = getattr(skill, "code", None)
        if not isinstance(code, str) or not code.strip():
            raise SkillArtifactStoreError("candidate Skill code must be a non-empty UTF-8 string")
        try:
            code_bytes = code.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise SkillArtifactStoreError("candidate Skill code is not valid UTF-8") from exc
        trust = getattr(getattr(skill, "trust_level", None), "value", getattr(skill, "trust_level", None))
        if trust != "draft":
            raise SkillArtifactStoreError("only draft Skills may be staged as replay candidates")
        normalized_tenant = _identity(tenant_id, "tenant_id", _ID_RE)
        digest = hashlib.sha256(code_bytes).hexdigest()
        artifact = {
            "schema_version": CANDIDATE_ARTIFACT_SCHEMA,
            "tenant_id": normalized_tenant,
            "skill_id": skill_id,
            "skill_version": version,
            "trust_level": "draft",
            "content_sha256": digest,
            "code": code,
        }
        payload = _canonical_json(artifact)
        path = self._artifact_path(
            normalized_tenant, skill_id, version, create=True, candidate=True,
        )
        try:
            _write_create_once(
                path, payload,
                collision_message="Skill candidate version already exists",
            )
        except SkillArtifactStoreError as exc:
            if "version already exists" not in str(exc):
                raise
            # A lost socket response may be retried with a new request ID. Only
            # the exact immutable candidate bytes may be accepted idempotently.
            read_flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                read_flags |= os.O_NOFOLLOW
            try:
                existing_fd = os.open(path, read_flags)
            except OSError as read_exc:
                raise SkillArtifactStoreError("existing Skill candidate is unavailable or unsafe") from read_exc
            try:
                info = os.fstat(existing_fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid not in {0, os.geteuid()}
                    or info.st_mode & 0o222
                    or info.st_size > 512 * 1024
                ):
                    raise SkillArtifactStoreError("existing Skill candidate is unsafe or oversized")
                with os.fdopen(existing_fd, "rb") as stream:
                    existing_bytes = stream.read(512 * 1024 + 1)
            except Exception:
                try:
                    os.close(existing_fd)
                except OSError:
                    pass
                raise
            if len(existing_bytes) > 512 * 1024:
                raise SkillArtifactStoreError("existing Skill candidate is oversized")
            try:
                existing = json.loads(existing_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as read_exc:
                raise SkillArtifactStoreError("existing Skill candidate is malformed") from read_exc
            if (
                not isinstance(existing, dict)
                or set(existing) != {
                    "schema_version", "tenant_id", "skill_id", "skill_version",
                    "trust_level", "content_sha256", "code",
                }
                or existing.get("schema_version") != CANDIDATE_ARTIFACT_SCHEMA
                or existing.get("tenant_id") != normalized_tenant
                or existing.get("skill_id") != skill_id
                or existing.get("skill_version") != version
                or existing.get("trust_level") != "draft"
                or not isinstance(existing.get("code"), str)
            ):
                raise SkillArtifactStoreError("existing Skill candidate identity is invalid")
            try:
                existing_digest = hashlib.sha256(existing["code"].encode("utf-8", errors="strict")).hexdigest()
            except UnicodeError as read_exc:
                raise SkillArtifactStoreError("existing Skill candidate code is invalid UTF-8") from read_exc
            if existing.get("content_sha256") != existing_digest:
                raise SkillArtifactStoreError("existing Skill candidate digest is invalid")
            if existing["code"] != code:
                raise SkillArtifactStoreError("Skill candidate version already exists with different content")
            return {
                "tenant_id": normalized_tenant,
                "skill_id": skill_id,
                "skill_version": version,
                "content_sha256": existing_digest,
                "trust_level": "draft",
            }
        return {
            "tenant_id": normalized_tenant,
            "skill_id": skill_id,
            "skill_version": version,
            "content_sha256": digest,
            "trust_level": "draft",
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
        if not isinstance(expected_trust, str) or expected_trust not in (_TRUST_LEVELS | {"draft"}):
            raise SkillArtifactStoreError("Skill replay trust level is not executable")

        is_candidate = expected_trust == "draft"
        path = self._artifact_path(
            tenant_id, skill_id, version, create=False, candidate=is_candidate,
        )
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
        if not is_candidate:
            fields.add("validation_attestation")
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
            "schema_version": CANDIDATE_ARTIFACT_SCHEMA if is_candidate else ARTIFACT_SCHEMA,
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
        if not is_candidate:
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
    "CANDIDATE_ARTIFACT_SCHEMA",
    "VALIDATION_ATTESTATION_SCHEMA",
    "SkillArtifactStore",
    "SkillArtifactStoreError",
]
