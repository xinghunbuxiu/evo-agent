import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.organization_runtime import OrganizationRegistry


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
            status="validated", evidence_refs=["test-run:123"],
            content_ref="skills/android-regression/SKILL.md",
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


if __name__ == "__main__":
    unittest.main()
