"""Accepted Reflection synthesis creates a new immutable draft executable candidate."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.knowledge_runtime import create_accepted_reflection_executable_candidate
from core import Experience, ExperienceStore
from core.experience_reflection import ExperienceReflectionStore


class ExperienceReflectionExecutableCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.tenant_id = "tenant-synthesis"
        self.source = Experience(
            id="source-experience", domain="python", task_type="automation",
            input_summary="Automate a deterministic check",
            output_summary="The task completed and the output was inspected",
            quality_score=0.0,
            metadata={"evidence_refs": ["task-1", "verifier-event-1"]},
        )
        ExperienceStore(self.workspace, self.tenant_id).save(self.source)
        self.store = ExperienceReflectionStore(self.workspace, self.tenant_id)
        self.reflection = self.store.append(
            self.source.id, author="member:1",
            findings={
                "title": "Reusable deterministic check",
                "observed_outcome": "A deterministic check was completed",
                "steps": ["Read the input", "Validate the expected value", "Return the result"],
                "applicability_conditions": ["Input is a mapping"],
                "constraints": ["Do not access files outside the supplied workspace"],
                "counterexamples": [], "open_questions": [],
            },
            source_evidence_refs=["task-1", "verifier-event-1"],
            idempotency_key="synthesis-reflection-submit",
        )
        self.store.decide(
            self.reflection.id, reviewer="admin:2", decision="accepted",
            idempotency_key="synthesis-reflection-decision",
        )
        self.candidate = {
            "name": "Validate expected value", "domain": "python",
            "description": "Validate a mapping against a requested expected value.",
            "code": (
                '"""Deterministic value validation."""\n'
                "def run(context):\n"
                "    if not isinstance(context, dict):\n"
                "        raise TypeError('context must be a mapping')\n"
                "    return context.get('value') == context.get('expected')\n"
            ),
            "version": "1.0.0",
        }

    def tearDown(self):
        self.temp.cleanup()

    def create(self, candidate=None):
        return create_accepted_reflection_executable_candidate(
            self.workspace, self.tenant_id, self.reflection.id,
            candidate if candidate is not None else self.candidate,
        )

    def test_accepted_reflection_creates_draft_candidate_bound_to_recipe_and_source(self):
        result = self.create()
        payload = json.loads(Path(result["visible_path"]).read_text(encoding="utf-8"))
        self.assertEqual(result["trust_level"], "draft")
        self.assertTrue(result["replay_eligible"])
        self.assertEqual(result["replay_status"], "awaiting_broker_replay")
        self.assertEqual(payload["source"], "accepted_reflection_executable_candidate")
        self.assertEqual(payload["parameters"]["execution_contract"], {
            "kind": "python_run_context", "replay_eligible": True,
        })
        provenance = payload["parameters"]["provenance"]
        self.assertEqual(provenance["tenant_id"], self.tenant_id)
        self.assertEqual(provenance["source_experience_id"], self.source.id)
        self.assertEqual(provenance["source_experience_digest"], self.reflection.metadata["experience_reflection"]["source_experience_digest"])
        self.assertEqual(provenance["reflection_id"], self.reflection.id)
        self.assertEqual(provenance["recipe_skill_id"], "recipe-" + __import__("hashlib").sha256(
            f"{self.tenant_id}:{self.reflection.id}".encode("utf-8")
        ).hexdigest()[:24])
        self.assertEqual(payload["parameters"]["synthesis"]["static_contract_check"], "passed")
        self.assertEqual(payload["parameters"]["synthesis"]["method"], "caller_supplied_candidate")
        self.assertTrue(Path(result["cache_path"]).is_file())

    def test_candidate_creation_is_idempotent_and_never_overwrites(self):
        first = self.create()
        second = self.create()
        self.assertEqual(first["skill_id"], second["skill_id"])
        self.assertEqual(Path(first["visible_path"]).read_bytes(), Path(second["visible_path"]).read_bytes())
        changed = dict(self.candidate, code=self.candidate["code"] + "\n")
        third = self.create(changed)
        self.assertNotEqual(first["skill_id"], third["skill_id"])

    def test_pending_reflection_cannot_create_executable_candidate(self):
        pending = self.store.append(
            self.source.id, author="member:3",
            findings={"steps": ["Read input"], "observed_outcome": "Pending"},
            source_evidence_refs=["task-1"], idempotency_key="pending-reflection",
        )
        with self.assertRaisesRegex(ValueError, "exactly one terminal decision"):
            create_accepted_reflection_executable_candidate(
                self.workspace, self.tenant_id, pending.id, self.candidate,
            )

    def test_invalid_or_unsafe_entrypoint_is_rejected_without_executable_candidate(self):
        bad = dict(self.candidate, code="print('module side effect')\ndef run(context):\n    return context\n")
        with self.assertRaisesRegex(ValueError, "only a module docstring"):
            self.create(bad)
        bad = dict(self.candidate, code="async def run(context):\n    return context\n")
        with self.assertRaisesRegex(ValueError, "exactly one synchronous"):
            self.create(bad)
        draft_dir = self.workspace / ".tenants" / self.tenant_id / "skills" / "draft"
        self.assertFalse(any(path.name.startswith("recipe-exec-") for path in draft_dir.glob("*.json")))

    def test_client_cannot_override_trust_or_execution_contract(self):
        forged = dict(self.candidate, trust_level="verified")
        with self.assertRaisesRegex(ValueError, "unsupported or missing fields"):
            self.create(forged)


if __name__ == "__main__":
    unittest.main()
