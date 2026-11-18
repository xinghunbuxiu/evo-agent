"""Regression tests for formal task registration and dispatch gating."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.task_center_runtime import (  # noqa: E402
    adopt_worker_growth_recommendation,
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

    def test_worker_growth_recommendation_adoption_creates_pinned_learning_task(self):
        center = {"recommendations": [{
            "recommendation_id": "growth:member-a:run-a:node-a",
            "member_id": "member-a",
            "title": "修复验收遗漏",
            "objective": "补齐独立验收证据并复盘失败原因",
            "deliverables": ["验证报告", "复盘记录"],
            "status": "suggested",
            "metadata": {
                "source": "talent_center_worker_growth",
                "source_mission_run_id": "run-a",
                "source_node_id": "node-a",
                "worker_id": "worker-a",
                "training_mode": "remediation",
                "priority": "high",
                "failure_reasons": ["missing verifier"],
            },
        }]}
        result = adopt_worker_growth_recommendation(
            center,
            recommendation_id="growth:member-a:run-a:node-a",
            member_id="member-a",
            now="2026-11-18T10:00:00+08:00",
        )
        task = result["task"]
        self.assertTrue(result["created"])
        self.assertEqual(task["task_id"], "learning:growth:member-a:run-a:node-a")
        self.assertEqual(task["status"], "assigned")
        self.assertFalse(task["metadata"]["execution_authorized"])
        self.assertFalse(task["metadata"]["automatic_retry"])
        self.assertEqual(task["metadata"]["source_mission_run_id"], "run-a")
        self.assertEqual(center["recommendations"][0]["status"], "adopted")

    def test_worker_growth_adoption_is_idempotent(self):
        center = {"items": [], "recommendations": [{
            "recommendation_id": "growth:member-a:run-a:node-a",
            "member_id": "member-a",
            "title": "训练",
            "objective": "目标",
            "status": "suggested",
            "metadata": {"source": "talent_center_worker_growth"},
        }]}
        first = adopt_worker_growth_recommendation(
            center, recommendation_id="growth:member-a:run-a:node-a",
            member_id="member-a", now="2026-11-18T10:00:00+08:00",
        )
        second = adopt_worker_growth_recommendation(
            center, recommendation_id="growth:member-a:run-a:node-a",
            member_id="member-a", now="2026-11-18T10:05:00+08:00",
        )
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertIs(first["task"], second["task"])
        self.assertEqual(len(center["items"]), 1)

    def test_worker_growth_adoption_rejects_cross_member_and_wrong_source(self):
        base = {
            "recommendation_id": "r1", "member_id": "member-a",
            "title": "训练", "objective": "目标", "status": "suggested",
            "metadata": {"source": "talent_center_worker_growth"},
        }
        for member_id, source, expected in (
            ("member-b", "talent_center_worker_growth", "does not match"),
            ("member-a", "manual", "not a worker-growth"),
        ):
            center = {"recommendations": [{**base, "metadata": {"source": source}}]}
            with self.assertRaisesRegex(ValueError, expected):
                adopt_worker_growth_recommendation(
                    center, recommendation_id="r1", member_id=member_id,
                    now="2026-11-18T10:00:00+08:00",
                )

    def test_adopted_recommendation_without_linked_task_fails_closed(self):
        center = {"items": [], "recommendations": [{
            "recommendation_id": "r1", "member_id": "member-a",
            "status": "adopted",
            "metadata": {"source": "talent_center_worker_growth"},
        }]}
        with self.assertRaisesRegex(ValueError, "manual reconciliation"):
            adopt_worker_growth_recommendation(
                center, recommendation_id="r1", member_id="member-a",
                now="2026-11-18T10:00:00+08:00",
            )


if __name__ == "__main__":
    unittest.main()
