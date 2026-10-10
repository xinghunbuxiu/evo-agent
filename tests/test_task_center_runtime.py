"""Regression tests for formal task registration and dispatch gating."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.task_center_runtime import (  # noqa: E402
    has_open_formal_task,
    has_suggested_recommendation,
    upsert_task,
    upsert_task_recommendation,
)


class TaskCenterRuntimeTests(unittest.TestCase):
    def test_upsert_updates_existing_task_without_creating_duplicate(self):
        center = {"items": [{"task_id": "task-1", "title": "old", "status": "assigned"}]}
        result = upsert_task(center, {"task_id": "task-1", "title": "revised"})
        self.assertEqual(len(center["items"]), 1)
        self.assertIs(result, center["items"][0])
        self.assertEqual(result["title"], "revised")
        self.assertEqual(result["status"], "assigned")

    def test_open_task_gate_only_clears_when_other_tasks_are_approved(self):
        center = {"items": [
            {"task_id": "task-1", "member_id": "member-a", "status": "approved"},
            {"task_id": "task-2", "member_id": "member-a", "status": "submitted"},
            {"task_id": "task-3", "member_id": "member-b", "status": "assigned"},
        ]}
        self.assertTrue(has_open_formal_task(center, "member-a"))
        self.assertFalse(has_open_formal_task(center, "member-a", exclude_task_id="task-2"))
        self.assertTrue(has_open_formal_task(center, "member-b"))
        self.assertFalse(has_open_formal_task(center, "member-c"))

    def test_suggested_recommendation_can_be_scoped_to_source(self):
        center = {"recommendations": [
            {"recommendation_id": "r1", "member_id": "member-a", "status": "suggested",
             "metadata": {"source": "auto_observation"}},
            {"recommendation_id": "r2", "member_id": "member-a", "status": "dismissed",
             "metadata": {"source": "manual"}},
        ]}
        self.assertTrue(has_suggested_recommendation(center, "member-a"))
        self.assertTrue(has_suggested_recommendation(center, "member-a", sources={"auto_observation"}))
        self.assertFalse(has_suggested_recommendation(center, "member-a", sources={"manual"}))
        self.assertFalse(has_suggested_recommendation(center, "member-b"))

    def test_recommendation_upsert_does_not_duplicate_id(self):
        center = {"recommendations": [
            {"recommendation_id": "r1", "status": "suggested", "title": "first"}
        ]}
        result = upsert_task_recommendation(center, {
            "recommendation_id": "r1", "status": "accepted"
        })
        self.assertEqual(len(center["recommendations"]), 1)
        self.assertEqual(result["title"], "first")
        self.assertEqual(result["status"], "accepted")


if __name__ == "__main__":
    unittest.main()
