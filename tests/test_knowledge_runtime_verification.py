"""Skill promotion requires explicit replay evidence, not historical success alone."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin import knowledge_runtime  # noqa: E402
from core import Skill, SkillTrustLevel  # noqa: E402


class SkillReplayVerificationTests(unittest.TestCase):
    def _skill(self):
        return Skill(
            id="candidate-skill",
            name="Candidate",
            domain="python",
            capability_type="general_dev",
            description="candidate",
            code="run and verify",
            parameters={},
            trust_level=SkillTrustLevel.DRAFT,
            source="test",
            version="1.0.0",
        )

    def test_historical_success_does_not_count_as_candidate_replay(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(knowledge_runtime, "matching_mission_delivery_experiences") as history, \
             mock.patch.object(knowledge_runtime.SkillRegistry, "verify_skill") as verify:
            history.return_value = [
                mock.Mock(id="old-task-1", quality_score=1.0),
                mock.Mock(id="old-task-2", quality_score=1.0),
            ]
            result = knowledge_runtime.maybe_auto_verify_skill_candidate(
                Path(tmp), "tenant-a", self._skill(), "python"
            )
            self.assertIsNone(result)
            history.assert_not_called()
            verify.assert_not_called()

    def test_stable_historical_experience_cluster_cannot_verify_candidate(self):
        items = [
            mock.Mock(id="history-1", quality_score=0.99),
            mock.Mock(id="history-2", quality_score=0.98),
            mock.Mock(id="history-3", quality_score=0.97),
        ]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(knowledge_runtime.SkillRegistry, "verify_skill") as verify:
            result = knowledge_runtime.maybe_auto_verify_stable_experience_skill_candidate(
                Path(tmp), "tenant-a", self._skill(), items
            )
            self.assertIsNone(result)
            verify.assert_not_called()

    def test_pending_skill_replay_observations_never_seed_stable_skill_drafts(self):
        from core import Experience, ExperienceStore

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            store = ExperienceStore(workspace, "tenant-a")
            for index in range(2):
                store.save(Experience(
                    id=f"replay-observation-{index}",
                    domain="javascript",
                    task_type="mission_delivery",
                    input_summary="Broker ran candidate in isolation",
                    output_summary="Execution completed",
                    quality_score=1.0,
                    capability_type="frontend",
                    metadata={"skill_replay": {
                        "schema_version": "mission.skill-replay-experience.v1",
                        "execution_success": True,
                        "execution_status": "succeeded",
                        "reflection": {
                            "status": "pending",
                            "reusable_experience": None,
                        },
                    }},
                ))

            groups = knowledge_runtime.collect_stable_experience_skill_groups(
                workspace, "tenant-a"
            )
            self.assertEqual(groups, [])

    def test_reflection_records_are_never_auto_drafted_as_skills(self):
        self.assertTrue(
            knowledge_runtime.should_skip_auto_skill_task_type("experience_reflection")
            knowledge_runtime.should_skip_auto_skill_task_type("experience_reflection_decision")
        )
        self.assertTrue(
            knowledge_runtime.should_skip_auto_skill_task_type("EXPERIENCE_REFLECTION")
        )

    def test_reflection_experience_records_never_enter_stable_skill_groups(self):
        from core import Experience, ExperienceStore

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            store = ExperienceStore(workspace, "tenant-a")
            for index in range(2):
                store.save(Experience(
                    id=f"reflection-{index}",
                    domain="reflection",
                    task_type="experience_reflection",
                    input_summary="Reflection",
                    output_summary="Reviewed observation",
                    quality_score=1.0,
                    metadata={"experience_reflection": {"state": "accepted"}},
                ))
            self.assertEqual(
                knowledge_runtime.collect_stable_experience_skill_groups(workspace, "tenant-a"),
                [],
            )

    def test_mission_delivery_clusters_require_explicit_pass_verdict(self):
        from core import Experience, ExperienceStore

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            store = ExperienceStore(workspace, "tenant-a")
            cases = [
                ("pass-1", {"verdict": "pass"}),
                ("pass-2", {"verdict": "pass"}),
                ("failed", {"verdict": "failed"}),
                ("needs-learning", {"verdict": "needs_learning"}),
                ("missing", None),
            ]
            for experience_id, validation in cases:
                metadata = {"mission_delivery": {}}
                if validation is not None:
                    metadata["mission_delivery"]["validation_evidence"] = validation
                store.save(Experience(
                    id=experience_id,
                    domain="javascript",
                    task_type="mission_delivery",
                    input_summary="mission input",
                    output_summary="mission output",
                    quality_score=1.0,
                    capability_type="frontend",
                    metadata=metadata,
                ))

            groups = knowledge_runtime.collect_stable_experience_skill_groups(
                workspace, "tenant-a"
            )
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["count"], 2)
            self.assertEqual(
                {item.id for item in groups[0]["items"]},
                {"pass-1", "pass-2"},
            )

    def test_stable_experience_skill_keeps_each_source_experience_mission_worker_and_task_evidence(self):
        import json
        from core import Experience, ExperienceStore

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            store = ExperienceStore(workspace, "tenant-a")
            experiences = [
                Experience(
                    id="experience-1",
                    domain="javascript",
                    task_type="mission_delivery",
                    input_summary="Vue source",
                    output_summary="Restored Vue app",
                    quality_score=0.94,
                    capability_type="frontend",
                    metadata={"mission_delivery": {
                        "mission_run_id": "run-1",
                        "mission_node_id": "node-1",
                        "primary_worker_id": "worker-vue",
                        "evidence_ids": ["analyze-1", "reconstruct-1"],
                        "validation_evidence": {"verdict": "pass", "evaluation_score": 0.94},
                        "decision_trace": [{"step": "validate", "result": "passed"}],
                    }, "skill_execution": {
                        "schema_version": "skill.execution.feedback.v1",
                        "skill_id": "skill-vue",
                        "skill_version": "2.4.1",
                        "execution_status": "succeeded",
                    }},
                ),
                Experience(
                    id="experience-2",
                    domain="javascript",
                    task_type="mission_delivery",
                    input_summary="Vue source 2",
                    output_summary="Restored Vue app 2",
                    quality_score=0.92,
                    capability_type="frontend",
                    metadata={"mission_delivery": {
                        "mission_run_id": "run-2",
                        "mission_node_id": "node-2",
                        "primary_worker_id": "worker-vue-2",
                        "evidence_ids": ["analyze-2", "reconstruct-2"],
                        "validation_evidence": {"verdict": "pass", "evaluation_score": 0.92},
                        "decision_trace": [{"step": "validate", "result": "passed"}],
                    }, "skill_execution": {
                        "schema_version": "skill.execution.feedback.v1",
                        "skill_id": "skill-vue",
                        "skill_version": "2.4.1",
                        "execution_status": "succeeded",
                    }},
                ),
            ]
            for experience in experiences:
                store.save(experience)

            with mock.patch.object(
                knowledge_runtime,
                "load_local_skill_payload",
                return_value={"trust_level": "verified", "usage_count": 7},
            ), mock.patch.object(knowledge_runtime, "collect_stable_experience_skill_groups", return_value=[{
                "domain": "javascript",
                "task_type": "mission_delivery",
                "capability_type": "frontend",
                "items": experiences,
                "count": 2,
                "avg_quality": 0.93,
            }]):
                drafted = knowledge_runtime.auto_draft_stable_experience_skills(
                    workspace,
                    "tenant-a",
                    safe_float=lambda value, default=0.0: float(value) if value is not None else default,
                    record_growth_event=lambda *args, **kwargs: None,
                )

            self.assertEqual(len(drafted), 1)
            skill_path = workspace / ".tenants" / "tenant-a" / "skills" / "draft" / "skill_auto_javascript_mission_delivery.json"
            skill = json.loads(skill_path.read_text(encoding="utf-8"))
            parameters = skill["parameters"]
            self.assertEqual(skill["trust_level"], "draft")
            self.assertEqual(skill["usage_count"], 7)
            self.assertEqual(parameters["source_experience_ids"], ["experience-1", "experience-2"])
            self.assertEqual(parameters["source_mission_run_ids"], ["run-1", "run-2"])
            self.assertEqual(parameters["source_worker_ids"], ["worker-vue", "worker-vue-2"])
            self.assertEqual(parameters["evidence_ids"], [
                "analyze-1", "reconstruct-1", "analyze-2", "reconstruct-2",
            ])
            self.assertEqual(
                [item["mission_run_id"] for item in parameters["source_experiences"]],
                ["run-1", "run-2"],
            )
            self.assertEqual(
                [item["experience_id"] for item in parameters["source_experiences"]],
                ["experience-1", "experience-2"],
            )
            self.assertEqual(
                [item["mission_node_id"] for item in parameters["source_experiences"]],
                ["node-1", "node-2"],
            )
            self.assertEqual(
                [item["primary_worker_id"] for item in parameters["source_experiences"]],
                ["worker-vue", "worker-vue-2"],
            )
            self.assertEqual(
                [item["evidence_ids"] for item in parameters["source_experiences"]],
                [["analyze-1", "reconstruct-1"], ["analyze-2", "reconstruct-2"]],
            )
            self.assertEqual(
                [item["skill_execution"]["skill_version"] for item in parameters["source_experiences"]],
                ["2.4.1", "2.4.1"],
            )
            self.assertEqual(
                [item["validation_evidence"]["verdict"] for item in parameters["source_experiences"]],
                ["pass", "pass"],
            )
            self.assertEqual(
                [item["decision_trace"][0]["result"] for item in parameters["source_experiences"]],
                ["passed", "passed"],
            )

    def test_replay_results_must_be_bound_to_candidate_and_pass_all_checks(self):
        invalid_results = [
            [{"success": True, "task_id": "task-1", "verified_by": "pytest"}],
            [{
                "success": True, "task_id": "task-1", "verified_by": "pytest",
                "validation_type": "skill_replay", "skill_id": "another-skill",
                "checks": [{"name": "smoke", "passed": True}],
            }],
            [{
                "success": True, "task_id": "task-1", "verified_by": "pytest",
                "validation_type": "skill_replay", "skill_id": "candidate-skill",
                "checks": [{"name": "smoke", "passed": False}],
            }],
            [{
                "success": True, "task_id": "task-1", "verified_by": "pytest",
                "validation_type": "skill_replay", "skill_id": "candidate-skill",
                "checks": [],
            }],
        ]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(knowledge_runtime.SkillRegistry, "verify_skill") as verify:
            for evidence in invalid_results:
                result = knowledge_runtime.maybe_auto_verify_skill_candidate(
                    Path(tmp), "tenant-a", self._skill(), "python",
                    replay_results=evidence,
                )
                self.assertIsNone(result)
            verify.assert_not_called()


    def test_forged_success_dict_cannot_reach_skill_registry_verification(self):
        forged = [{
            "success": True,
            "task_id": "task-1",
            "verified_by": "trusted-validator",
            "validation_type": "skill_replay",
            "skill_id": "candidate-skill",
            "checks": [{"name": "smoke", "passed": True}],
            "broker_signature_verified": True,
            "validator_signature_verified": True,
        }]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(knowledge_runtime.SkillRegistry, "verify_skill") as verify:
            result = knowledge_runtime.maybe_auto_verify_skill_candidate(
                Path(tmp), "tenant-a", self._skill(), "python",
                replay_results=forged,
            )
            self.assertIsNone(result)
            verify.assert_not_called()


    def test_mission_delivery_candidate_is_explicitly_non_executable_recipe(self):
        mission_run = {
            "mission_run_id": "mission-recipe-test",
            "mission_kind": "javascript_reverse",
            "runtime_route": {},
            "context": {},
            "plan": {"nodes": [{
                "id": "promote_knowledge",
                "decision_trace": [{"step": "promote", "result": "draft"}],
            }]},
        }
        captured = {}

        def capture_candidate(workspace, tenant_id, skill):
            captured["skill"] = skill
            return {"skill_id": skill.id, "trust_level": skill.trust_level.value}

        with mock.patch.object(
            knowledge_runtime, "load_local_skill_payload",
            return_value={"trust_level": "verified", "usage_count": 3},
        ), mock.patch.object(
            knowledge_runtime, "write_skill_candidate", side_effect=capture_candidate
        ), mock.patch.object(
            knowledge_runtime, "maybe_auto_verify_skill_candidate", return_value=None
        ) as replay_attempt:
            result = knowledge_runtime.create_mission_delivery_skill_candidate(
                workspace=Path("/tmp/unused-skill-candidate-test"),
                tenant_id="tenant-a",
                mission_run=mission_run,
                analyze_snapshot={"task_id": "analyze-task", "summary": "Vue bundle"},
                reconstruct_snapshot={
                    "task_id": "reconstruct-task",
                    "summary": "Vue reconstruction",
                    "evaluation_verdict": "pass",
                    "evaluation_score": 0.95,
                    "evaluation_metrics": {"components": 12, "has_target_dir": True},
                },
                safe_float=lambda value, default=0.0: float(value) if value is not None else default,
                build_snapshot_signature=lambda snapshot: {"task_id": snapshot["task_id"]},
                record_growth_event=lambda *args, **kwargs: None,
            )

        contract = captured["skill"].parameters["execution_contract"]
        self.assertEqual(captured["skill"].trust_level, SkillTrustLevel.DRAFT)
        self.assertEqual(captured["skill"].usage_count, 4)
        self.assertEqual(contract["kind"], "non_executable_recipe")
        self.assertFalse(contract["replay_eligible"])
        self.assertIn("not Python run(context)", contract["reason"])
        self.assertEqual(result["trust_level"], "draft")
        self.assertEqual(result["replay_status"], "blocked")
        self.assertEqual(result["replay_reason"], "non_executable_recipe")
        replay_attempt.assert_not_called()

if __name__ == "__main__":
    unittest.main()
