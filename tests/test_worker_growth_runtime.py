import unittest

from admin.worker_growth_runtime import (
    apply_worker_growth_recommendation,
    build_worker_growth_recommendation,
    growth_recommendation_requires_training,
)


class WorkerGrowthRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.employee = {
            "member_id": "employee-1",
            "worker_id": "worker-1",
            "primary_role": "javascript_reverse",
        }
        self.mission = {"mission_run_id": "mission-1"}
        self.node = {"id": "node-1", "title": "Reverse parser"}
        self.runtime = {
            "child_members": [
                {
                    "member_id": "employee-1",
                    "training_plan": {"stage": "active_training"},
                }
            ],
            "task_center": {"recommendations": []},
        }

    def test_failed_worker_gets_targeted_remediation_recommendation(self):
        recommendation = build_worker_growth_recommendation(
            employee=self.employee,
            mission_run=self.mission,
            node=self.node,
            outcome={
                "status": "failed",
                "failure_reasons": ["parser misses nested calls", "fixture coverage is incomplete"],
                "independent_verification": {"status": "failed"},
            },
        )
        self.assertEqual(recommendation["training_mode"], "remediation")
        self.assertTrue(growth_recommendation_requires_training(recommendation))
        self.assertEqual(recommendation["priority"], "high")
        self.assertIn("nested calls", recommendation["objective"])

        apply_worker_growth_recommendation(runtime=self.runtime, recommendation=recommendation)
        member = self.runtime["child_members"][0]
        self.assertEqual(member["training_plan"]["stage"], "remediation_planned")
        self.assertEqual(len(self.runtime["task_center"]["recommendations"]), 1)

        apply_worker_growth_recommendation(runtime=self.runtime, recommendation=recommendation)
        self.assertEqual(len(self.runtime["task_center"]["recommendations"]), 1)

    def test_verified_success_gets_consolidation_not_failure_training(self):
        recommendation = build_worker_growth_recommendation(
            employee=self.employee,
            mission_run=self.mission,
            node=self.node,
            outcome={
                "status": "success",
                "independent_verification": {"status": "passed"},
            },
        )
        self.assertEqual(recommendation["training_mode"], "consolidation")
        self.assertFalse(growth_recommendation_requires_training(recommendation))
        self.assertEqual(recommendation["priority"], "normal")

    def test_worker_output_without_verifier_is_not_treated_as_success(self):
        recommendation = build_worker_growth_recommendation(
            employee=self.employee,
            mission_run=self.mission,
            node=self.node,
            outcome={
                "status": "success",
                "summary": "worker says it passed",
            },
        )
        self.assertEqual(recommendation["training_mode"], "remediation")

    def test_canonical_child_members_container_is_updated(self):
        recommendation = build_worker_growth_recommendation(
            employee=self.employee,
            mission_run=self.mission,
            node=self.node,
            outcome={"status": "failed"},
        )
        runtime = {
            "child_members": {
                "selected_member_id": "employee-1",
                "items": [{"member_id": "employee-1", "training_plan": {}}],
            },
            "task_center": {"recommendations": []},
        }
        apply_worker_growth_recommendation(runtime=runtime, recommendation=recommendation)
        self.assertEqual(
            runtime["child_members"]["items"][0]["training_plan"]["stage"],
            "remediation_planned",
        )
        self.assertEqual(len(runtime["task_center"]["recommendations"]), 1)

    def test_missing_employee_cannot_receive_growth_writeback(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            apply_worker_growth_recommendation(
                runtime=self.runtime,
                recommendation={"recommendation_id": "growth:x", "member_id": "missing"},
            )


if __name__ == "__main__":
    unittest.main()
