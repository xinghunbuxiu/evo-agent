"""Strict, bounded canonical Manifest contract for Broker-published Skills.

This module is deliberately independent of Artifact Store and Validator wiring.
It validates descriptive metadata only; a valid Manifest does not authorize
execution, publication, or tenant access.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any


MANIFEST_SCHEMA = "mission.skill-manifest.v1"
RUNTIME_CONTRACT_PYTHON_RUN_CONTEXT_V1 = "python.run_context.v1"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_SCHEMA_DEPTH = 16
MAX_SCHEMA_NODES = 512
MAX_SCHEMA_PROPERTIES = 64
MAX_SCHEMA_ARRAY_ITEMS = 128
MAX_SCHEMA_STRING_LENGTH = 4096

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_TASK_TYPE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_RUNTIME_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){1,2}$")

_REQUIRED_FIELDS = {
    "schema_version", "skill_id", "skill_version", "name", "domain",
    "capability_type", "description", "task_types", "input_schema",
    "output_schema", "runtime_contract", "compatibility",
}
_RUNTIME_FIELDS = {"id", "entrypoint", "call_signature"}
_COMPATIBILITY_FIELDS = {"runtime", "min_version", "max_version"}
_SCHEMA_KEYS = {
    "type", "properties", "required", "additionalProperties", "items",
    "enum", "const", "minimum", "maximum", "minLength", "maxLength",
    "minItems", "maxItems", "title", "description",
}
_SCHEMA_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


class SkillManifestError(ValueError):
    """A Skill Manifest is malformed, unsupported, or exceeds safety bounds."""


def _text(value: Any, field: str, *, maximum: int, minimum: int = 1) -> str:
    if not isinstance(value, str):
        raise SkillManifestError(f"{field} must be a string")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise SkillManifestError(f"{field} must be valid UTF-8") from exc
    if not minimum <= len(value) <= maximum or "\x00" in value:
        raise SkillManifestError(f"{field} length is invalid")
    return value


def _identity(value: Any, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise SkillManifestError(f"{field} is invalid")
    return value


def _strict_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SkillManifestError("Manifest must contain strict JSON values") from exc
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise SkillManifestError("Manifest exceeds the 64 KiB limit")
    return encoded


def _validate_schema(value: Any, field: str) -> dict[str, Any]:
    """Validate a deliberately small, non-reference JSON Schema subset."""
    budget = [0]

    def visit(node: Any, depth: int, path: str) -> dict[str, Any]:
        budget[0] += 1
        if budget[0] > MAX_SCHEMA_NODES:
            raise SkillManifestError(f"{field} exceeds the JSON Schema node limit")
        if depth > MAX_SCHEMA_DEPTH:
            raise SkillManifestError(f"{field} exceeds the JSON Schema depth limit")
        if not isinstance(node, dict) or not node or set(node) - _SCHEMA_KEYS:
            raise SkillManifestError(f"{path} has unsupported or missing schema fields")

        kind = node.get("type")
        if kind not in _SCHEMA_TYPES:
            raise SkillManifestError(f"{path}.type is unsupported")
        result: dict[str, Any] = {"type": kind}

        for key in ("title", "description"):
            if key in node:
                result[key] = _text(node[key], f"{path}.{key}", maximum=256)

        if "enum" in node:
            enum = node["enum"]
            if not isinstance(enum, list) or not 1 <= len(enum) <= 64:
                raise SkillManifestError(f"{path}.enum must contain 1..64 values")
            canonical = [_strict_json_bytes(item) for item in enum]
            if len(set(canonical)) != len(canonical):
                raise SkillManifestError(f"{path}.enum contains duplicate values")
            result["enum"] = enum
        if "const" in node:
            _strict_json_bytes(node["const"])
            result["const"] = node["const"]

        if kind == "object":
            properties = node.get("properties", {})
            required = node.get("required", [])
            additional = node.get("additionalProperties", False)
            if not isinstance(properties, dict) or len(properties) > MAX_SCHEMA_PROPERTIES:
                raise SkillManifestError(f"{path}.properties exceeds the property limit")
            if any(
                not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", name)
                for name in properties
            ):
                raise SkillManifestError(f"{path}.properties contains an invalid key")
            if not isinstance(required, list) or len(required) > len(properties):
                raise SkillManifestError(f"{path}.required is invalid")
            if any(not isinstance(name, str) for name in required) or len(set(required)) != len(required):
                raise SkillManifestError(f"{path}.required contains invalid or duplicate names")
            if not set(required).issubset(properties):
                raise SkillManifestError(f"{path}.required references an unknown property")
            if not isinstance(additional, bool):
                raise SkillManifestError(f"{path}.additionalProperties must be boolean")
            result["properties"] = {
                name: visit(schema, depth + 1, f"{path}.properties.{name}")
                for name, schema in sorted(properties.items())
            }
            result["required"] = sorted(required)
            result["additionalProperties"] = additional
        elif any(key in node for key in ("properties", "required", "additionalProperties")):
            raise SkillManifestError(f"{path} object keywords require type=object")

        if kind == "array":
            items = node.get("items")
            if items is None:
                raise SkillManifestError(f"{path}.items is required for arrays")
            result["items"] = visit(items, depth + 1, f"{path}.items")
            minimum = node.get("minItems", 0)
            maximum = node.get("maxItems", MAX_SCHEMA_ARRAY_ITEMS)
            if (
                isinstance(minimum, bool) or not isinstance(minimum, int)
                or isinstance(maximum, bool) or not isinstance(maximum, int)
                or minimum < 0 or maximum < minimum or maximum > MAX_SCHEMA_ARRAY_ITEMS
            ):
                raise SkillManifestError(f"{path} item bounds are invalid")
            result["minItems"] = minimum
            result["maxItems"] = maximum
        elif any(key in node for key in ("items", "minItems", "maxItems")):
            raise SkillManifestError(f"{path} array keywords require type=array")

        if kind == "string":
            minimum = node.get("minLength", 0)
            maximum = node.get("maxLength", MAX_SCHEMA_STRING_LENGTH)
            if (
                isinstance(minimum, bool) or not isinstance(minimum, int)
                or isinstance(maximum, bool) or not isinstance(maximum, int)
                or minimum < 0 or maximum < minimum or maximum > MAX_SCHEMA_STRING_LENGTH
            ):
                raise SkillManifestError(f"{path} string bounds are invalid")
            result["minLength"] = minimum
            result["maxLength"] = maximum
        elif any(key in node for key in ("minLength", "maxLength")):
            raise SkillManifestError(f"{path} string keywords require type=string")

        if kind in {"integer", "number"}:
            for key in ("minimum", "maximum"):
                if key in node:
                    number = node[key]
                    if isinstance(number, bool) or not isinstance(number, (int, float)):
                        raise SkillManifestError(f"{path}.{key} must be numeric")
                    if isinstance(number, float) and not math.isfinite(number):
                        raise SkillManifestError(f"{path}.{key} must be finite")
                    result[key] = number
            if "minimum" in result and "maximum" in result and result["minimum"] > result["maximum"]:
                raise SkillManifestError(f"{path} numeric bounds are inverted")
        elif any(key in node for key in ("minimum", "maximum")):
            raise SkillManifestError(f"{path} numeric keywords require a numeric type")

        return result

    normalized = visit(value, 0, field)
    _strict_json_bytes(normalized)
    return normalized


def normalize_skill_manifest(value: Any) -> dict[str, Any]:
    """Return the sole canonical in-memory representation of a v1 Manifest."""
    if not isinstance(value, Mapping) or set(value) != _REQUIRED_FIELDS:
        raise SkillManifestError("Manifest has unsupported or missing fields")
    if value.get("schema_version") != MANIFEST_SCHEMA:
        raise SkillManifestError("unsupported Skill Manifest schema")

    skill_id = _identity(value.get("skill_id"), "skill_id", _ID_RE)
    version = _identity(value.get("skill_version"), "skill_version", _VERSION_RE)
    name = _text(value.get("name"), "name", maximum=128)
    domain = _identity(value.get("domain"), "domain", _CAPABILITY_RE)
    capability = _identity(value.get("capability_type"), "capability_type", _CAPABILITY_RE)
    description = _text(value.get("description"), "description", maximum=1024)

    raw_tasks = value.get("task_types")
    if not isinstance(raw_tasks, list) or not 1 <= len(raw_tasks) <= 32:
        raise SkillManifestError("task_types must contain 1..32 entries")
    task_types = [_identity(item, "task_type", _TASK_TYPE_RE) for item in raw_tasks]
    if len(set(task_types)) != len(task_types):
        raise SkillManifestError("task_types must be unique")
    task_types.sort()

    runtime = value.get("runtime_contract")
    if not isinstance(runtime, dict) or set(runtime) != _RUNTIME_FIELDS:
        raise SkillManifestError("runtime_contract has unsupported or missing fields")
    if runtime != {
        "id": RUNTIME_CONTRACT_PYTHON_RUN_CONTEXT_V1,
        "entrypoint": "run",
        "call_signature": "run(context)",
    }:
        raise SkillManifestError("unsupported runtime contract")

    compatibility = value.get("compatibility")
    if not isinstance(compatibility, dict) or set(compatibility) != _COMPATIBILITY_FIELDS:
        raise SkillManifestError("compatibility has unsupported or missing fields")
    if compatibility.get("runtime") != "python":
        raise SkillManifestError("compatibility runtime is unsupported")
    minimum = _identity(compatibility.get("min_version"), "compatibility.min_version", _RUNTIME_VERSION_RE)
    maximum = _identity(compatibility.get("max_version"), "compatibility.max_version", _RUNTIME_VERSION_RE)
    min_parts = tuple(map(int, minimum.split(".")))
    max_parts = tuple(map(int, maximum.split(".")))
    width = max(len(min_parts), len(max_parts))
    if min_parts + (0,) * (width - len(min_parts)) > max_parts + (0,) * (width - len(max_parts)):
        raise SkillManifestError("compatibility runtime version range is inverted")

    input_schema = _validate_schema(value.get("input_schema"), "input_schema")
    if input_schema["type"] != "object":
        raise SkillManifestError("input_schema root must describe the run(context) object")

    normalized = {
        "schema_version": MANIFEST_SCHEMA,
        "skill_id": skill_id,
        "skill_version": version,
        "name": name,
        "domain": domain,
        "capability_type": capability,
        "description": description,
        "task_types": task_types,
        "input_schema": input_schema,
        "output_schema": _validate_schema(value.get("output_schema"), "output_schema"),
        "runtime_contract": {
            "id": RUNTIME_CONTRACT_PYTHON_RUN_CONTEXT_V1,
            "entrypoint": "run",
            "call_signature": "run(context)",
        },
        "compatibility": {
            "runtime": "python", "min_version": minimum, "max_version": maximum,
        },
    }
    _strict_json_bytes(normalized)
    return normalized


def canonical_manifest_bytes(value: Any) -> bytes:
    """Validate, normalize, and serialize a Manifest deterministically."""
    return _strict_json_bytes(normalize_skill_manifest(value))


def manifest_sha256(value: Any) -> str:
    """Return the digest of canonical Manifest bytes, never of source code."""
    return hashlib.sha256(canonical_manifest_bytes(value)).hexdigest()
