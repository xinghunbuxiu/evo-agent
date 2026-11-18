"""Regression tests for the strict, bounded Skill Manifest v1 contract."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.skill_manifest import (
    MANIFEST_SCHEMA,
    RUNTIME_CONTRACT_PYTHON_RUN_CONTEXT_V1,
    SkillManifestError,
    canonical_manifest_bytes,
    manifest_sha256,
    normalize_skill_manifest,
)


def valid_manifest():
    return {
        "schema_version": MANIFEST_SCHEMA,
        "skill_id": "skill_android_login",
        "skill_version": "1.2.0",
        "name": "Android login",
        "domain": "android",
        "capability_type": "account.login",
        "description": "Perform a validated Android login flow.",
        "task_types": ["android.login", "account.authenticate"],
        "input_schema": {
            "type": "object",
            "properties": {
                "username": {"type": "string", "minLength": 1, "maxLength": 128},
                "password": {"type": "string", "minLength": 1, "maxLength": 256},
            },
            "required": ["username", "password"],
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {"authenticated": {"type": "boolean"}},
            "required": ["authenticated"],
            "additionalProperties": False,
        },
        "runtime_contract": {
            "id": RUNTIME_CONTRACT_PYTHON_RUN_CONTEXT_V1,
            "entrypoint": "run",
            "call_signature": "run(context)",
        },
        "compatibility": {
            "runtime": "python", "min_version": "3.11.0", "max_version": "3.13.9",
        },
    }


class SkillManifestTests(unittest.TestCase):
    def test_normalizes_task_types_and_schema_property_order(self):
        manifest = valid_manifest()
        manifest["task_types"].reverse()
        manifest["input_schema"]["properties"] = dict(
            reversed(list(manifest["input_schema"]["properties"].items()))
        )
        normalized = normalize_skill_manifest(manifest)
        self.assertEqual(normalized["task_types"], sorted(manifest["task_types"]))
        self.assertEqual(list(normalized["input_schema"]["properties"]), ["password", "username"])

    def test_canonical_digest_is_stable_across_mapping_order(self):
        first = valid_manifest()
        second = dict(reversed(list(first.items())))
        second["input_schema"] = dict(reversed(list(first["input_schema"].items())))
        self.assertEqual(canonical_manifest_bytes(first), canonical_manifest_bytes(second))
        self.assertEqual(manifest_sha256(first), manifest_sha256(second))
        self.assertEqual(manifest_sha256(first), hashlib.sha256(canonical_manifest_bytes(first)).hexdigest())

    def test_manifest_digest_is_independent_of_executable_code(self):
        manifest = valid_manifest()
        digest = manifest_sha256(manifest)
        code_a = "def run(context): return {'authenticated': True}"
        code_b = "def run(context): return {'authenticated': False}"
        self.assertNotEqual(hashlib.sha256(code_a.encode()).hexdigest(), hashlib.sha256(code_b.encode()).hexdigest())
        self.assertEqual(digest, manifest_sha256(manifest))

    def test_rejects_missing_and_unknown_top_level_fields(self):
        missing = valid_manifest()
        del missing["description"]
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(missing)
        unknown = valid_manifest()
        unknown["shell_command"] = "whoami"
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(unknown)

    def test_rejects_invalid_identity_and_version(self):
        for field, value in (
            ("skill_id", "../outside"), ("skill_version", "v1/../../"),
            ("domain", "Android"), ("capability_type", "Account Login"),
        ):
            manifest = valid_manifest()
            manifest[field] = value
            with self.subTest(field=field), self.assertRaises(SkillManifestError):
                normalize_skill_manifest(manifest)

    def test_rejects_long_strings_and_invalid_utf8(self):
        manifest = valid_manifest()
        manifest["description"] = "x" * 1025
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)
        manifest = valid_manifest()
        manifest["name"] = "\ud800"
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)

    def test_rejects_duplicate_or_unbounded_task_types(self):
        manifest = valid_manifest()
        manifest["task_types"] = ["android.login", "android.login"]
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)
        manifest["task_types"] = ["task.type"] * 33
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)

    def test_rejects_unsupported_runtime_and_entrypoint(self):
        manifest = valid_manifest()
        manifest["runtime_contract"]["id"] = "python.dynamic_import.v1"
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)
        manifest = valid_manifest()
        manifest["runtime_contract"]["entrypoint"] = "main"
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)

    def test_rejects_unsupported_compatibility_fields_and_inverted_range(self):
        manifest = valid_manifest()
        manifest["compatibility"]["platform"] = "android"
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)
        manifest = valid_manifest()
        manifest["compatibility"]["min_version"] = "3.14.0"
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)

    def test_rejects_unknown_json_schema_keywords_and_references(self):
        for key in ("$ref", "$defs", "allOf", "not", "default"):
            manifest = valid_manifest()
            manifest["input_schema"][key] = {}
            with self.subTest(key=key), self.assertRaises(SkillManifestError):
                normalize_skill_manifest(manifest)

    def test_rejects_invalid_schema_types_and_required_properties(self):
        manifest = valid_manifest()
        manifest["input_schema"]["type"] = "function"
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)
        manifest = valid_manifest()
        manifest["input_schema"]["required"] = ["missing"]
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)

    def test_rejects_invalid_or_unbounded_schema_array(self):
        manifest = valid_manifest()
        manifest["output_schema"] = {
            "type": "array", "items": {"type": "string"}, "maxItems": 129,
        }
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)

    def test_rejects_excessive_schema_depth_and_nodes(self):
        schema = {"type": "string"}
        for _ in range(18):
            schema = {"type": "array", "items": schema}
        manifest = valid_manifest()
        manifest["output_schema"] = schema
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)

        properties = {f"field_{i}": {"type": "string"} for i in range(65)}
        manifest = valid_manifest()
        manifest["output_schema"] = {
            "type": "object", "properties": properties, "required": [],
            "additionalProperties": False,
        }
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)

    def test_rejects_non_json_and_nan_values(self):
        manifest = valid_manifest()
        manifest["output_schema"]["enum"] = [float("nan")]
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)
        manifest = valid_manifest()
        manifest["input_schema"]["properties"]["nested"] = {"type": "object", "properties": {"bad": object()}}
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)

    def test_rejects_oversized_manifest(self):
        manifest = valid_manifest()
        manifest["description"] = "x" * 1024
        manifest["name"] = "n" * 128
        manifest["task_types"] = [f"task.{i}" for i in range(32)]
        manifest["output_schema"] = {
            "type": "object",
            "properties": {f"field_{i}": {"type": "string", "description": "d" * 256} for i in range(64)},
            "required": [], "additionalProperties": False,
        }
        with self.assertRaises(SkillManifestError):
            normalize_skill_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
