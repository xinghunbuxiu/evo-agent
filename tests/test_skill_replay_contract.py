"""Regression tests for immutable Skill replay artifact bindings."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.skill_replay_contract import (
    SkillReplayBindingError,
    build_skill_replay_binding,
    verify_skill_replay_binding,
)


MISSION = {
    "tenant_id": "tenant-a",
    "mission_run_id": "mission-17",
    "node_id": "node-2",
    "task_id": "task-9",
}


def make_skill(**overrides):
    values = {
        "id": "skill-python-review",
        "version": "2.4.1",
        "code": "steps:\\n  - inspect\\n  - test\\n",
        "trust_level": SimpleNamespace(value="draft"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SkillReplayContractTests(unittest.TestCase):
    def test_binding_freezes_skill_artifact_and_mission_lineage(self):
        skill = make_skill()
        binding = build_skill_replay_binding(skill, MISSION)

        self.assertEqual(binding["skill_id"], skill.id)
        self.assertEqual(binding["skill_version"], "2.4.1")
        self.assertEqual(len(binding["content_sha256"]), 64)
        self.assertEqual(binding["mission_context"], MISSION)
        self.assertEqual(verify_skill_replay_binding(binding, skill), binding)

    def test_manifest_binding_v2_pins_canonical_manifest_digest(self):
        from core.skill_manifest import manifest_sha256
        manifest = {
            "schema_version": "mission.skill-manifest.v1",
            "skill_id": "skill-python-review", "skill_version": "2.4.1",
            "name": "Python Review", "domain": "python",
            "capability_type": "general_dev", "description": "Review Python tasks",
            "task_types": ["code.review"],
            "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            "output_schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False},
            "runtime_contract": {"id": "python.run_context.v1", "entrypoint": "run", "call_signature": "run(context)"},
            "compatibility": {"runtime": "python", "min_version": "3.11.0", "max_version": "3.14.0"},
        }
        skill = make_skill(
            name="Python Review", domain="python", capability_type="general_dev",
            description="Review Python tasks", parameters={"manifest": manifest},
        )
        binding = build_skill_replay_binding(skill, MISSION)
        self.assertEqual(binding["schema_version"], "mission.skill-replay-binding.v2")
        self.assertEqual(binding["manifest_sha256"], manifest_sha256(manifest))
        self.assertEqual(verify_skill_replay_binding(binding, skill), binding)
        changed_skill = make_skill(
            name="Python Review", domain="python", capability_type="general_dev",
            description="Review Python tasks",
            parameters={"manifest": dict(manifest, description="substituted")},
        )
        with self.assertRaisesRegex(SkillReplayBindingError, "changed"):
            verify_skill_replay_binding(binding, changed_skill)

    def test_changed_content_is_rejected(self):
        binding = build_skill_replay_binding(make_skill(), MISSION)
        with self.assertRaisesRegex(SkillReplayBindingError, "changed"):
            verify_skill_replay_binding(binding, make_skill(code="steps:\\n  - altered\\n"))

    def test_changed_version_is_rejected(self):
        binding = build_skill_replay_binding(make_skill(), MISSION)
        with self.assertRaisesRegex(SkillReplayBindingError, "changed"):
            verify_skill_replay_binding(binding, make_skill(version="2.4.2"))

    def test_invalid_or_incomplete_lineage_is_rejected(self):
        with self.assertRaises(SkillReplayBindingError):
            build_skill_replay_binding(make_skill(), {"tenant_id": "tenant-a"})

    def test_empty_skill_content_is_rejected(self):
        with self.assertRaisesRegex(SkillReplayBindingError, "non-empty"):
            build_skill_replay_binding(make_skill(code="  "), MISSION)

    def test_binding_rejects_unrecognized_fields(self):
        binding = build_skill_replay_binding(make_skill(), MISSION)
        binding["caller_argv"] = ["sh", "-c", "unexpected"]
        with self.assertRaisesRegex(SkillReplayBindingError, "unsupported"):
            verify_skill_replay_binding(binding, make_skill())


if __name__ == "__main__":
    unittest.main()
