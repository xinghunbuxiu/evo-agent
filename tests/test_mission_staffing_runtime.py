"""Regression tests for explicit Talent Center employee selection."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_staffing_runtime import resolve_selected_employee  # noqa: E402


class MissionStaffingRuntimeTests(unittest.TestCase):
    def test_resolves_only_explicitly_selected_active_employee(self):
        members = [{"member_id": "employee-a", "primary_role": "android"},
                   {"member_id": "employee-b", "primary_role": "android"}]
        selected = resolve_selected_employee(members=members, selected_member_id="employee-b")
        self.assertEqual(selected["member_id"], "employee-b")

    def test_does_not_guess_from_role_or_list_order(self):
        members = [{"member_id": "employee-a", "primary_role": "android"},
                   {"member_id": "employee-b", "primary_role": "android"}]
        self.assertIsNone(resolve_selected_employee(members=members, selected_member_id=""))

    def test_rejects_missing_archived_or_talent_development_selection(self):
        members = [{"member_id": "archived", "status": "archived"},
                   {"member_id": "coach", "primary_role": "talent_development"}]
        self.assertIsNone(resolve_selected_employee(members=members, selected_member_id="missing"))
        self.assertIsNone(resolve_selected_employee(members=members, selected_member_id="archived"))
        self.assertIsNone(resolve_selected_employee(members=members, selected_member_id="coach"))

    def test_rejects_ambiguous_duplicate_member_identity(self):
        members = [{"member_id": "employee-a"}, {"member_id": "employee-a"}]
        self.assertIsNone(resolve_selected_employee(members=members, selected_member_id="employee-a"))


if __name__ == "__main__":
    unittest.main()
