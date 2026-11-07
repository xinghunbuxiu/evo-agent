import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.organization_runtime import OrganizationRegistry, recommend_workforce_for_node, recommend_workforce_for_nodes, sync_worker_catalog


class OrganizationRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = OrganizationRegistry(Path(self.temp.name))
        self.registry.create_role(
            role_id="android-dev", title="Android Developer",
            responsibilities=["implement", "test"],
            required_capabilities=["android", "kotlin"], standards=["tests-required"],
        )
        self.registry.create_worker(
            worker_id="android-a", role_id="android-dev",
            profile={"model": "configured-model", "skills": ["android-build"]},
        )

    def test_clone_is_independent_and_does_not_copy_active_tasks(self):
        self.registry.set_worker_status(worker_id="android-a", status="busy", active_task_ids=["task-1"])
        clone = self.registry.clone_worker(source_worker_id="android-a", new_worker_id="android-b")
        self.assertEqual(clone["role_id"], "android-dev")
        self.assertEqual(clone["created_from_worker_id"], "android-a")
        self.assertEqual(clone["profile"], self.registry.get_worker("android-a")["profile"])
        self.assertEqual(clone["status"], "available")
        self.assertEqual(clone["active_task_ids"], [])
        self.registry.set_worker_status(
            worker_id="android-b", status="busy", active_task_ids=["task-2"],
        )
        self.assertEqual(self.registry.get_worker("android-a")["active_task_ids"], ["task-1"])
        self.assertEqual(self.registry.get_worker("android-b")["active_task_ids"], ["task-2"])
        self.assertEqual(self.registry.get_worker("android-a")["status"], "busy")
        self.assertEqual(self.registry.get_worker("android-b")["status"], "busy")
        self.assertEqual(len(self.registry.list_workers(role_id="android-dev")), 2)

    def test_new_work_can_create_a_persistent_role(self):
        role = self.registry.create_role(
            role_id="toutiao-ops", title="Toutiao Operations",
            responsibilities=["content planning", "performance analysis"],
            required_capabilities=["content_strategy", "analytics"],
        )
        worker = self.registry.create_worker(
            worker_id="toutiao-ops-a", role_id=role["role_id"],
            profile={"specialty": "content operations"},
        )
        self.assertEqual(worker["role_id"], "toutiao-ops")
        self.assertEqual(self.registry.get_role("toutiao-ops")["status"], "active")

    def test_retirement_preserves_role_and_only_links_validated_assets(self):
        self.registry.register_knowledge_asset(
            asset_id="android-skill-v1", role_id="android-dev",
            title="Verified Android regression workflow", asset_type="skill",
            status="candidate", evidence_refs=[],
            content_ref="skills/android-regression/SKILL.md",
        )
        self.registry.validate_knowledge_asset(
            asset_id="android-skill-v1", evidence_refs=["test-run:123"],
        )
        retired = self.registry.retire_worker(
            worker_id="android-a", validated_knowledge_asset_ids=["android-skill-v1"],
        )
        self.assertEqual(retired["status"], "retired")
        self.assertIsNotNone(self.registry.get_role("android-dev"))
        self.assertEqual(self.registry.get_role("android-dev")["knowledge_asset_ids"], ["android-skill-v1"])
        self.assertEqual(self.registry.list_workers(role_id="android-dev"), [])
        self.assertEqual(len(self.registry.list_workers(role_id="android-dev", include_retired=True)), 1)

    def test_retirement_rejects_candidate_assets_and_active_tasks(self):
        self.registry.register_knowledge_asset(
            asset_id="candidate", role_id="android-dev", title="Possible improvement",
            asset_type="experience", status="candidate", evidence_refs=[],
            content_ref="experiences/candidate.json",
        )
        with self.assertRaises(ValueError):
            self.registry.retire_worker(worker_id="android-a", validated_knowledge_asset_ids=["candidate"])
        self.registry.set_worker_status(worker_id="android-a", status="busy", active_task_ids=["task-1"])
        with self.assertRaises(ValueError):
            self.registry.retire_worker(worker_id="android-a", validated_knowledge_asset_ids=[])

    def test_retired_worker_cannot_be_reactivated_or_cloned(self):
        self.registry.retire_worker(worker_id="android-a", validated_knowledge_asset_ids=[])
        with self.assertRaises(ValueError):
            self.registry.set_worker_status(worker_id="android-a", status="available")
        with self.assertRaises(ValueError):
            self.registry.clone_worker(source_worker_id="android-a", new_worker_id="android-b")

    def test_duplicate_and_unsafe_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            self.registry.create_role(role_id="../bad", title="bad", responsibilities=[], required_capabilities=[])
        with self.assertRaises(ValueError):
            self.registry.create_worker(worker_id="android-a", role_id="android-dev", profile={})


    def test_worker_task_claim_is_exclusive_and_release_reopens_worker(self):
        claimed = self.registry.claim_worker_task(
            worker_id="android-a", task_id="mission-node-1",
        )
        self.assertEqual(claimed["status"], "busy")
        self.assertEqual(claimed["active_task_ids"], ["mission-node-1"])

        # Retrying the same claim is idempotent; a different task cannot steal the worker.
        same_claim = self.registry.claim_worker_task(
            worker_id="android-a", task_id="mission-node-1",
        )
        self.assertEqual(same_claim["active_task_ids"], ["mission-node-1"])
        with self.assertRaises(ValueError):
            self.registry.claim_worker_task(
                worker_id="android-a", task_id="mission-node-2",
            )

        released = self.registry.release_worker_task(
            worker_id="android-a", task_id="mission-node-1",
        )
        self.assertEqual(released["status"], "available")
        self.assertEqual(released["active_task_ids"], [])
        # Duplicate release is idempotent, but the same claim cannot be reopened.
        repeated_release = self.registry.release_worker_task(
            worker_id="android-a", task_id="mission-node-1",
        )
        self.assertEqual(repeated_release["status"], "available")
        with self.assertRaises(ValueError):
            self.registry.claim_worker_task(
                worker_id="android-a", task_id="mission-node-1",
            )

    def test_concurrent_claims_for_one_worker_allow_exactly_one_task(self):
        import concurrent.futures
        import threading

        barrier = threading.Barrier(2)
        def claim(task_id):
            barrier.wait(timeout=2)
            try:
                self.registry.claim_worker_task(worker_id="android-a", task_id=task_id)
                return "claimed"
            except ValueError:
                return "rejected"

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(claim, ["parallel-task-a", "parallel-task-b"]))
        self.assertEqual(outcomes.count("claimed"), 1)
        self.assertEqual(outcomes.count("rejected"), 1)
        worker = self.registry.get_worker("android-a")
        self.assertEqual(worker["status"], "busy")
        self.assertEqual(len(worker["active_task_ids"]), 1)

    def test_worker_with_multiple_active_tasks_stays_busy_until_all_released(self):
        self.registry.set_worker_status(
            worker_id="android-a", status="busy",
            active_task_ids=["task-1", "task-2"],
        )
        released = self.registry.release_worker_task(
            worker_id="android-a", task_id="task-1",
        )
        self.assertEqual(released["status"], "busy")
        self.assertEqual(released["active_task_ids"], ["task-2"])
        released = self.registry.release_worker_task(
            worker_id="android-a", task_id="task-2",
        )
        self.assertEqual(released["status"], "available")
        self.assertEqual(released["active_task_ids"], [])

    def test_clone_drops_credentials_and_live_runtime_fields(self):
        self.registry.create_worker(
            worker_id="android-secret",
            role_id="android-dev",
            profile={
                "model": "configured-model",
                "skills": ["android-build"],
                "api_key": "do-not-copy",
                "nested": {"access_token": "do-not-copy", "runtime_state": {"pid": 42}, "region": "local", "rapid_mode": True},
            },
        )
        clone = self.registry.clone_worker(source_worker_id="android-secret", new_worker_id="android-safe")
        self.assertEqual(clone["profile"]["model"], "configured-model")
        self.assertEqual(clone["profile"]["skills"], ["android-build"])
        self.assertNotIn("api_key", clone["profile"])
        self.assertNotIn("access_token", clone["profile"]["nested"])
        self.assertNotIn("runtime_state", clone["profile"]["nested"])
        self.assertEqual(clone["profile"]["nested"]["region"], "local")
        self.assertTrue(clone["profile"]["nested"]["rapid_mode"])

    def test_validated_asset_requires_evidence_reference(self):
        with self.assertRaises(ValueError):
            self.registry.register_knowledge_asset(
                asset_id="unsupported-claim", role_id="android-dev", title="No evidence",
                asset_type="skill", status="validated", evidence_refs=["claimed"],
                content_ref="skills/no-evidence/SKILL.md",
            )
        self.registry.register_knowledge_asset(
            asset_id="candidate-no-evidence", role_id="android-dev", title="Candidate",
            asset_type="skill", status="candidate", evidence_refs=[],
            content_ref="skills/candidate/SKILL.md",
        )
        with self.assertRaises(ValueError):
            self.registry.validate_knowledge_asset(
                asset_id="candidate-no-evidence", evidence_refs=[],
            )
        validated = self.registry.validate_knowledge_asset(
            asset_id="candidate-no-evidence", evidence_refs=["ci-run:456"],
        )
        self.assertEqual(validated["status"], "validated")
        self.assertEqual(validated["evidence_refs"], ["ci-run:456"])

    def test_standard_promotion_requires_validated_asset_and_approval(self):
        self.registry.register_knowledge_asset(
            asset_id="standard-candidate", role_id="android-dev", title="Candidate",
            asset_type="skill", status="candidate", evidence_refs=[],
            content_ref="skills/standard-candidate/SKILL.md",
        )
        with self.assertRaises(ValueError):
            self.registry.promote_knowledge_asset_to_standard(
                asset_id="standard-candidate", approval_ref="approval:1",
            )
        self.registry.validate_knowledge_asset(
            asset_id="standard-candidate", evidence_refs=["ci-run:789"],
        )
        with self.assertRaises(ValueError):
            self.registry.promote_knowledge_asset_to_standard(
                asset_id="standard-candidate", approval_ref="",
            )
        standard = self.registry.promote_knowledge_asset_to_standard(
            asset_id="standard-candidate", approval_ref="approval:1",
        )
        self.assertEqual(standard["status"], "standard")
        self.assertEqual(standard["evidence_refs"], ["ci-run:789", "approval:1"])
        self.registry.retire_worker(
            worker_id="android-a", validated_knowledge_asset_ids=["standard-candidate"],
        )
        self.assertIn(
            "standard-candidate",
            self.registry.get_role("android-dev")["knowledge_asset_ids"],
        )

    def test_worker_catalog_sync_creates_durable_roles_and_only_enabled_instances(self):
        fresh = OrganizationRegistry(Path(self.temp.name) / "catalog")
        result = sync_worker_catalog(
            fresh,
            {
                "android": {
                    "title": "Android Worker",
                    "capability_type": "android",
                    "task_types": ["analyze"],
                    "owned_modules": ["runtime"],
                },
                "toutiao": {
                    "title": "Toutiao Worker",
                    "capability_type": "automation",
                    "task_types": ["execute"],
                },
            },
            {"android"},
        )
        self.assertEqual(result, {"roles_created": 2, "workers_created": 1})
        self.assertEqual(fresh.get_role("android")["required_capabilities"], ["android"])
        self.assertEqual(fresh.get_worker("android")["profile"]["handler_id"], "android")
        self.assertIsNone(fresh.get_worker("toutiao"))

    def test_workforce_recommendation_respects_resolved_handler_route(self):
        self.registry.create_role(
            role_id="android-alt", title="Alternate Android Handler",
            responsibilities=["analyze"],
            required_capabilities=["android"],
        )
        self.registry.create_worker(
            worker_id="android-b", role_id="android-alt",
            profile={"handler_id": "android-b", "capability_type": "android"},
        )
        decision = recommend_workforce_for_node(
            {
                "id": "route-specific-node",
                "status": "ready",
                "required_capabilities": ["android"],
                "preferred_handler_id": "android-b",
            },
            self.registry,
        )
        self.assertEqual(decision["decision"], "assign_existing_worker_recommended")
        self.assertEqual(decision["recommended_worker_id"], "android-b")
        self.assertEqual(decision["recommended_role_id"], "android-alt")

    def test_workforce_recommends_available_worker_without_claiming_dispatch(self):
        decision = recommend_workforce_for_node(
            {"id": "node-a", "status": "ready", "required_capabilities": ["android", "kotlin"]},
            self.registry,
        )
        self.assertEqual(decision["decision"], "assign_existing_worker_recommended")
        self.assertEqual(decision["recommended_worker_id"], "android-a")
        self.assertFalse(decision["dispatch_authorized"])
        self.assertEqual(decision["dispatch_state"], "recommendation_only")

    def test_busy_worker_is_cloned_only_when_node_is_explicitly_parallel_safe(self):
        self.registry.set_worker_status(worker_id="android-a", status="busy", active_task_ids=["task-1"])
        safe = recommend_workforce_for_node(
            {"id": "node-safe", "status": "ready", "required_capabilities": ["android", "kotlin"], "parallel_safe": True},
            self.registry,
        )
        unsafe = recommend_workforce_for_node(
            {"id": "node-unsafe", "status": "ready", "required_capabilities": ["android", "kotlin"], "parallel_safe": False},
            self.registry,
        )
        self.assertEqual(safe["decision"], "clone_worker_recommended")
        self.assertEqual(safe["recommended_source_worker_id"], "android-a")
        self.assertEqual(unsafe["decision"], "wait_for_worker_recommended")
        self.assertIsNone(safe["recommended_worker_id"])

    def test_workforce_recommends_new_role_when_capabilities_are_missing(self):
        decision = recommend_workforce_for_node(
            {"id": "node-toutiao", "status": "ready", "required_capabilities": ["content_strategy", "analytics"]},
            self.registry,
        )
        self.assertEqual(decision["decision"], "create_role_and_worker_recommended")
        self.assertFalse(decision["dispatch_authorized"])

    def test_workforce_catalog_absence_is_explicit(self):
        decision = recommend_workforce_for_node(
            {"id": "node-a", "status": "ready", "required_capabilities": ["android"]},
            None,
        )
        self.assertEqual(decision["decision"], "catalog_unavailable")
        self.assertFalse(decision["dispatch_authorized"])

    def test_plan_does_not_recommend_same_available_worker_twice(self):
        decisions = recommend_workforce_for_nodes(
            [
                {"id": "node-a", "status": "ready", "required_capabilities": ["android", "kotlin"]},
                {"id": "node-b", "status": "ready", "required_capabilities": ["android", "kotlin"]},
            ],
            self.registry,
        )
        self.assertEqual(decisions[0]["recommended_worker_id"], "android-a")
        self.assertEqual(decisions[1]["decision"], "wait_for_worker_recommended")


if __name__ == "__main__":
    unittest.main()
