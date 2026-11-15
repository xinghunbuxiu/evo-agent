import unittest

from admin.mission_staffing_runtime import build_staffing_request, validate_staffing_assignment


class StaffingAssignmentContractTests(unittest.TestCase):
    def setUp(self):
        self.request = build_staffing_request(
            tenant_id="tenant-a",
            mission_run_id="mission-1",
            node={"id": "node-1", "task_type": "implementation"},
            workforce_decision={"recommended_role_id": "python", "required_capabilities": ["Python", "testing"]},
        )
        self.worker = {
            "worker_id": "worker-1",
            "owner_tenant_id": "tenant-a",
            "owner_member_id": "employee-1",
            "status": "available",
            "active_task_ids": [],
            "profile": {"handler_id": "python-worker"},
        }
        self.assignment = {
            "schema_version": "talent.staffing_assignment.v1",
            "decision_owner": "talent_center",
            "status": "approved",
            "tenant_id": "tenant-a",
            "mission_run_id": "mission-1",
            "node_id": "node-1",
            "request_id": self.request["request_id"],
            "employee_member_id": "employee-1",
            "worker_id": "worker-1",
        }

    def test_request_is_non_authorizing_and_normalizes_capabilities(self):
        self.assertFalse(self.request["dispatch_authorized"])
        self.assertEqual(self.request["required_capabilities"], ["python", "testing"])
        self.assertEqual(self.request["status"], "pending")

    def test_accepts_matching_talent_center_approval(self):
        self.assertEqual(
            validate_staffing_assignment(
                assignment=self.assignment,
                request=self.request,
                worker=self.worker,
                expected_handler_id="python-worker",
            ),
            (True, "staffing_assignment_validated"),
        )

    def test_rejects_unapproved_or_cross_node_assignment(self):
        bad = dict(self.assignment, status="pending")
        self.assertEqual(
            validate_staffing_assignment(assignment=bad, request=self.request, worker=self.worker,
                                         expected_handler_id="python-worker")[1],
            "staffing_assignment_not_approved",
        )
        bad = dict(self.assignment, node_id="node-2")
        self.assertEqual(
            validate_staffing_assignment(assignment=bad, request=self.request, worker=self.worker,
                                         expected_handler_id="python-worker")[1],
            "staffing_assignment_node_id_mismatch",
        )

    def test_rejects_worker_employee_or_handler_mismatch(self):
        worker = dict(self.worker, owner_member_id="employee-2")
        self.assertEqual(
            validate_staffing_assignment(assignment=self.assignment, request=self.request, worker=worker,
                                         expected_handler_id="python-worker")[1],
            "staffing_assignment_worker_employee_mismatch",
        )
        self.assertEqual(
            validate_staffing_assignment(assignment=self.assignment, request=self.request, worker=self.worker,
                                         expected_handler_id="other-handler")[1],
            "staffing_assignment_handler_mismatch",
        )


if __name__ == "__main__":
    unittest.main()
