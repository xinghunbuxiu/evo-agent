import importlib.util
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "manage_tenant_memberships.py"
SPEC = importlib.util.spec_from_file_location("manage_tenant_memberships", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class TenantMembershipCliTests(unittest.TestCase):
    def test_set_remove_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            registry_path = Path(directory) / "memberships.json"
            audit_path = Path(directory) / "membership-audit.jsonl"
            with mock.patch("sys.argv", [
                "manage_tenant_memberships.py", "--file", str(registry_path),
                "set", "password:7", "tenant-a", "tenant_admin",
            ]):
                self.assertEqual(MODULE.main(), 0)
            self.assertEqual(json.loads(registry_path.read_text())["password:7"]["tenant-a"], "tenant_admin")
            self.assertEqual(registry_path.stat().st_mode & 0o777, 0o600)
            first = json.loads(audit_path.read_text().splitlines()[0])
            self.assertIn("actor_username", first)
            self.assertIsInstance(first["actor_uid"], int)
            self.assertEqual(first["event"], "change_requested")
            self.assertIsNone(first["previous_role"])
            self.assertEqual(first["new_role"], "tenant_admin")

            with unittest.mock.patch("sys.argv", [
                "manage_tenant_memberships.py", "--file", str(registry_path),
                "remove", "password:7", "tenant-a",
            ]):
                self.assertEqual(MODULE.main(), 0)
            self.assertEqual(json.loads(registry_path.read_text()), {})
            audit_records = [json.loads(line) for line in audit_path.read_text().splitlines()]
            self.assertEqual(len(audit_records), 4)
            self.assertEqual(audit_records[1]["event"], "change_applied")
            self.assertEqual(audit_records[2]["event"], "change_requested")

    def test_duplicate_registry_keys_are_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            registry_path = Path(directory) / "memberships.json"
            registry_path.write_text(
                '{"password:7":{"tenant-a":"viewer","tenant-a":"tenant_admin"}}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                MODULE._read_registry(registry_path)


if __name__ == "__main__":
    unittest.main()
