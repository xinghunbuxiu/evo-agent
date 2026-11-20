"""Manifest-bearing published Skill artifacts are immutable and fully reverified."""
from __future__ import annotations

import base64
import hashlib
import unittest
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.skill_artifact_store import (
    ARTIFACT_MANIFEST_SCHEMA, SkillArtifactStore, SkillArtifactStoreError,
)
from core.skill_manifest import manifest_sha256
from core.sandbox_broker_protocol import _canonical_json


class ArtifactStoreManifestPublicationTests(unittest.TestCase):
    def _manifest(self):
        return {
            "schema_version": "mission.skill-manifest.v1",
            "skill_id": "published-manifest-skill", "skill_version": "1.0.0",
            "name": "Published Manifest Skill", "domain": "python",
            "capability_type": "automation", "description": "test artifact",
            "task_types": ["automation"],
            "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            "output_schema": {"type": "object", "properties": {"ok": {"type": "boolean"}},
                              "required": ["ok"], "additionalProperties": False},
            "runtime_contract": {"id": "python.run_context.v1", "entrypoint": "run",
                                 "call_signature": "run(context)"},
            "compatibility": {"runtime": "python", "min_version": "3.10", "max_version": "3.13"},
        }

    def _attestation(self, validator_key, context, code_digest, manifest_digest, broker_request_id, broker_digest):
        statement = {
            "schema_version": "mission.skill-validation-attestation.v4",
            "validation_id": "validation-manifest-v2",
            "validator_id": "independent-validator",
            "policy_id": "manifest-policy",
            "policy_sha256": hashlib.sha256(b"policy").hexdigest(),
            "workspace_id": "manifest-workspace",
            **context,
            "broker_request_id": broker_request_id,
            "broker_attestation_sha256": broker_digest,
            "checks_sha256": hashlib.sha256(b"checks").hexdigest(),
            "skill_id": "published-manifest-skill",
            "skill_version": "1.0.0",
            "content_sha256": code_digest,
            "manifest_sha256": manifest_digest,
            "trust_level": "verified",
            "passed": True,
        }
        signature = validator_key.sign(_canonical_json(statement))
        return {
            **statement,
            "signature": {
                "algorithm": "ed25519", "key_id": "validator-key",
                "value": base64.b64encode(signature).decode("ascii"),
            },
        }

    def test_publish_manifest_artifact_is_create_once_and_readback_verified(self):
        with __import__("tempfile").TemporaryDirectory() as temp:
            from pathlib import Path
            root = Path(temp)
            root.chmod(0o700)
            validator_key = Ed25519PrivateKey.generate()
            store = SkillArtifactStore(
                root, validator_public_key=validator_key.public_key().public_bytes_raw(),
                validator_key_id="validator-key",
            )
            manifest = self._manifest()
            manifest_digest = manifest_sha256(manifest)
            code = "def run(context):\n    return {'ok': True}\n"
            code_digest = hashlib.sha256(code.encode()).hexdigest()
            context = {
                "tenant_id": "tenant-manifest", "mission_run_id": "mission-manifest",
                "node_id": "node-manifest", "task_id": "task-manifest",
            }
            broker_request_id = str(uuid.uuid4())
            broker_digest = hashlib.sha256(b"signed broker envelope").hexdigest()
            attestation = self._attestation(
                validator_key, context, code_digest, manifest_digest,
                broker_request_id, broker_digest,
            )
            skill = type("Skill", (), {
                "id": "published-manifest-skill", "version": "1.0.0",
                "code": code, "trust_level": "verified",
            })()
            identity = store.publish_manifest(
                tenant_id=context["tenant_id"], skill=skill, manifest=manifest,
                manifest_sha256=manifest_digest, validation_attestation=attestation,
                workspace_id="manifest-workspace", mission_context=context,
                broker_request_id=broker_request_id,
                broker_attestation_sha256=broker_digest,
            )
            self.assertEqual(identity["manifest_sha256"], manifest_digest)
            binding = {
                "schema_version": "mission.skill-replay-binding.v2",
                "skill_id": skill.id, "skill_version": skill.version,
                "content_sha256": code_digest, "manifest_sha256": manifest_digest,
                "trust_level": "verified", "mission_context": context,
            }
            loaded = store.load_published_manifest(binding)
            self.assertEqual(loaded.code, code)
            self.assertEqual(loaded.manifest, manifest)
            self.assertEqual(loaded.manifest_sha256, manifest_digest)
            path = root / context["tenant_id"] / skill.id / f"{skill.version}.json"
            import json
            artifact = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["schema_version"], ARTIFACT_MANIFEST_SCHEMA)
            self.assertEqual(artifact["manifest_sha256"], manifest_digest)
            with self.assertRaises(SkillArtifactStoreError):
                store.publish_manifest(
                    tenant_id=context["tenant_id"], skill=skill, manifest=manifest,
                    manifest_sha256=manifest_digest, validation_attestation=attestation,
                    workspace_id="manifest-workspace", mission_context=context,
                    broker_request_id=broker_request_id,
                    broker_attestation_sha256=broker_digest,
                )

    def test_load_rejects_manifest_substitution_after_publication(self):
        with __import__("tempfile").TemporaryDirectory() as temp:
            from pathlib import Path
            import json
            root = Path(temp)
            root.chmod(0o700)
            key = Ed25519PrivateKey.generate()
            store = SkillArtifactStore(root, validator_public_key=key.public_key().public_bytes_raw(),
                                       validator_key_id="validator-key")
            manifest = self._manifest()
            mdigest = manifest_sha256(manifest)
            code = "def run(context):\n    return {'ok': True}\n"
            cdigest = hashlib.sha256(code.encode()).hexdigest()
            context = {"tenant_id":"tenant-manifest","mission_run_id":"mission-manifest",
                       "node_id":"node-manifest","task_id":"task-manifest"}
            request_id = str(uuid.uuid4())
            broker_digest = hashlib.sha256(b"broker").hexdigest()
            attestation = self._attestation(key, context, cdigest, mdigest, request_id, broker_digest)
            skill = type("Skill", (), {"id":"published-manifest-skill","version":"1.0.0",
                                       "code":code,"trust_level":"verified"})()
            store.publish_manifest(tenant_id=context["tenant_id"],skill=skill,manifest=manifest,
                manifest_sha256=mdigest,validation_attestation=attestation,
                workspace_id="manifest-workspace",mission_context=context,
                broker_request_id=request_id,broker_attestation_sha256=broker_digest)
            path=root/context["tenant_id"]/skill.id/f"{skill.version}.json"
            artifact=json.loads(path.read_text(encoding="utf-8"))
            artifact["manifest"]["description"]="substituted"
            path.chmod(0o600)
            path.write_text(json.dumps(artifact),encoding="utf-8")
            path.chmod(0o400)
            binding={"schema_version":"mission.skill-replay-binding.v2","skill_id":skill.id,
                "skill_version":skill.version,"content_sha256":cdigest,"manifest_sha256":mdigest,
                "trust_level":"verified","mission_context":context}
            with self.assertRaises(SkillArtifactStoreError):
                store.load_published_manifest(binding)


if __name__ == "__main__":
    unittest.main()
