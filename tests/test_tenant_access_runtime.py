import unittest

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


if __name__ == "__main__":
    unittest.main()
