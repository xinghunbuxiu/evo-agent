import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from admin.tenant_access_runtime import tenant_role_for_user, user_can_access_tenant


class TenantAccessRuntimeTests(unittest.TestCase):
    def test_configured_membership_grants_only_the_named_tenant(self):
        config = '{"password:42": {"tenant-a": "tenant_admin", "tenant-b": "viewer"}}'
        user = {"id": 42, "auth_provider": "password"}
        self.assertEqual(tenant_role_for_user(user, "tenant-a", memberships_json=config), "tenant_admin")
        self.assertEqual(tenant_role_for_user(user, "tenant-b", memberships_json=config), "viewer")
        self.assertFalse(user_can_access_tenant(user, "tenant-c", memberships_json=config))
        self.assertFalse(user_can_access_tenant({"id": 42, "auth_provider": "gitee"}, "tenant-a", memberships_json=config))

    def test_missing_or_malformed_membership_fails_closed(self):
        user = {"id": 42}
        self.assertIsNone(tenant_role_for_user(user, "tenant-a", memberships_json=""))
        self.assertIsNone(tenant_role_for_user(user, "tenant-a", memberships_json="{"))
        duplicate_tenant = '{"password:42":{"tenant-a":"viewer","tenant-a":"tenant_admin"}}'
        self.assertIsNone(tenant_role_for_user({"id": 42, "auth_provider": "password"}, "tenant-a", memberships_json=duplicate_tenant))
        self.assertIsNone(tenant_role_for_user({"login": "alice", "id": 42}, "tenant-a", memberships_json='{"password:42":{"tenant-a":"tenant_admin"}}'))

    def test_unknown_roles_are_denied(self):
        config = '{"password:42": {"tenant-a": "owner"}}'
        self.assertIsNone(tenant_role_for_user({"id": 42, "auth_provider": "password"}, "tenant-a", memberships_json=config))

    def test_file_registry_is_used_when_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memberships.json"
            path.write_text('{"gitee:9":{"tenant-x":"viewer"}}', encoding="utf-8")
            with patch.dict(os.environ, {"EVO_TENANT_MEMBERSHIPS_FILE": str(path)}, clear=False):
                with patch.dict(os.environ, {"EVO_TENANT_MEMBERSHIPS_JSON": ""}, clear=False):
                    self.assertEqual(
                        tenant_role_for_user({"id": 9, "auth_provider": "gitee"}, "tenant-x"),
                        "viewer",
                    )

    def test_missing_configured_file_denies_instead_of_falling_back(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            with patch.dict(os.environ, {
                "EVO_TENANT_MEMBERSHIPS_FILE": str(missing),
                "EVO_TENANT_MEMBERSHIPS_JSON": '{"password:42":{"tenant-a":"tenant_admin"}}',
            }):
                self.assertIsNone(
                    tenant_role_for_user({"id": 42, "auth_provider": "password"}, "tenant-a")
                )


if __name__ == "__main__":
    unittest.main()
