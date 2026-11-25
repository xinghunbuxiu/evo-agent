"""Accepted Experience Reflections create only immutable non-executable Recipe drafts."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.knowledge_runtime import create_accepted_reflection_recipe_skill
from core import Experience, ExperienceStore
from core.experience_reflection import ExperienceReflectionStore


class ExperienceReflectionRecipeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.tenant_id = "tenant-a"
        self.experiences = ExperienceStore(self.workspace, self.tenant_id)
        self.source = Experience(
            id="mission-source-1",
            domain="android",
            task_type="device_diagnostics",
            input_summary="Inspect device connection",
            output_summary="ADB connection restored",
            quality_score=0.9,
            metadata={"mission_run_id": "mission-run-1", "evidence_ids": ["evidence-1"]},
        )
        self.experiences.save(self.source)
        self.reflections = ExperienceReflectionStore(self.workspace, self.tenant_id)
        self.reflection = self.reflections.append(
            self.source.id,
            author="member:1",
            findings={
                "title": "Recover ADB connection",
                "observed_outcome": "ADB connection restored after checking authorization",
                "steps": [
                    "Check that the device is visible to the host",
                    "Inspect the authorization prompt on the device",
                    "Retry the connection after approval",
                ],
                "applicability_conditions": ["USB debugging is enabled"],
                "constraints": ["Do not bypass device-owner authorization"],
                "counterexamples": ["A damaged cable requires hardware replacement"],
                "open_questions": ["Should wireless debugging be supported?"],
            },
            source_evidence_refs=["evidence-1"],
            idempotency_key="reflection-submit-1",
        )

    def tearDown(self):
        self.temp.cleanup()

    def accept(self):
        return self.reflections.decide(
            self.reflection.id,
            reviewer="admin:2",
            decision="accepted",
            idempotency_key="reflection-decision-1",
        )

    def test_pending_reflection_cannot_create_recipe(self):
        with self.assertRaisesRegex(ValueError, "exactly one terminal decision"):
            create_accepted_reflection_recipe_skill(
                self.workspace, self.tenant_id, self.reflection.id
            )
        self.assertFalse((self.workspace / ".tenants/tenant-a/skills/draft").exists())

    def test_rejected_reflection_cannot_create_recipe(self):
        self.reflections.decide(
            self.reflection.id,
            reviewer="admin:2",
            decision="rejected",
            reason="Evidence is insufficient",
            idempotency_key="reflection-decision-rejected",
        )
        with self.assertRaisesRegex(ValueError, "only an accepted Reflection"):
            create_accepted_reflection_recipe_skill(
                self.workspace, self.tenant_id, self.reflection.id
            )

    def test_accepted_reflection_creates_non_executable_draft_with_provenance(self):
        decision = self.accept()
        result = create_accepted_reflection_recipe_skill(
            self.workspace, self.tenant_id, self.reflection.id
        )
        path = Path(result["visible_path"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["trust_level"], "draft")
        self.assertEqual(payload["source"], "accepted_experience_reflection_recipe")
        self.assertEqual(payload["code"], "")
        self.assertFalse(payload["parameters"]["executable"])
        self.assertEqual(payload["parameters"]["recipe"]["steps"][0], "Check that the device is visible to the host")
        provenance = payload["parameters"]["provenance"]
        self.assertEqual(provenance["tenant_id"], self.tenant_id)
        self.assertEqual(provenance["source_experience_id"], self.source.id)
        self.assertEqual(provenance["reflection_id"], self.reflection.id)
        self.assertEqual(provenance["decision_id"], decision.id)
        self.assertEqual(provenance["reviewer"], "admin:2")

    def test_recipe_generation_is_idempotent_and_does_not_overwrite(self):
        self.accept()
        first = create_accepted_reflection_recipe_skill(
            self.workspace, self.tenant_id, self.reflection.id
        )
        second = create_accepted_reflection_recipe_skill(
            self.workspace, self.tenant_id, self.reflection.id
        )
        self.assertEqual(first["skill_id"], second["skill_id"])
        self.assertEqual(
            Path(first["visible_path"]).read_bytes(),
            Path(second["visible_path"]).read_bytes(),
        )

    def test_recipe_generation_requires_explicit_steps(self):
        self.reflections.append(
            self.source.id,
            author="member:3",
            findings={"observed_outcome": "No explicit procedure"},
            source_evidence_refs=["evidence-1"],
            idempotency_key="reflection-without-steps",
        )
        latest = self.reflections.list_for_source(self.source.id)[-1]
        self.reflections.decide(
            latest.id,
            reviewer="admin:4",
            decision="accepted",
            idempotency_key="reflection-accept-no-steps",
        )
        with self.assertRaisesRegex(ValueError, "explicit natural-language steps"):
            create_accepted_reflection_recipe_skill(
                self.workspace, self.tenant_id, latest.id
            )


if __name__ == "__main__":
    unittest.main()
