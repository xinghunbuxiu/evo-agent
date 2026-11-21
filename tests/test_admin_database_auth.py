"""Security regression tests for password hashing and local auth-store migration."""
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.database import Database, hash_password, verify_password_hash


class AdminDatabaseAuthTests(unittest.TestCase):
    def test_new_password_hash_uses_random_salt_and_verifies(self):
        first = hash_password("correct horse battery staple")
        second = hash_password("correct horse battery staple")
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("pbkdf2_sha256$"))
        self.assertEqual(len(first.split("$")), 4)
        self.assertEqual(verify_password_hash("correct horse battery staple", first), (True, False))
        self.assertEqual(verify_password_hash("wrong password", first), (False, False))

    def test_legacy_sha256_hash_is_verified_and_marked_for_upgrade(self):
        password = "legacy-password"
        legacy = hashlib.sha256((password + "evo-salt-2024").encode("utf-8")).hexdigest()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PASSWORD_SALT", None)
            self.assertEqual(verify_password_hash(password, legacy), (True, True))
            self.assertEqual(verify_password_hash("incorrect", legacy), (False, False))

    def test_local_login_migrates_legacy_hash_after_successful_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            legacy_path = root / "legacy-users.json"
            current_path = root / "data" / "admin_users.json"
            password = "legacy-password"
            legacy_hash = hashlib.sha256((password + "evo-salt-2024").encode("utf-8")).hexdigest()
            legacy_path.write_text(json.dumps({
                "users": [{
                    "id": 7,
                    "username": "legacy-user",
                    "password_hash": legacy_hash,
                    "name": "Legacy User",
                    "login_type": "password",
                }]
            }), encoding="utf-8")
            database = Database(local_store_path=current_path, legacy_store_path=legacy_path)

            self.assertIsNone(database._verify_local_password("legacy-user", "wrong-password"))
            copied_before_login = json.loads(current_path.read_text(encoding="utf-8"))
            self.assertEqual(copied_before_login["users"][0]["password_hash"], legacy_hash)
            result = database._verify_local_password("legacy-user", password)

            self.assertEqual(result["id"], 7)
            migrated = json.loads(current_path.read_text(encoding="utf-8"))
            new_hash = migrated["users"][0]["password_hash"]
            self.assertTrue(new_hash.startswith("pbkdf2_sha256$"))
            self.assertEqual(verify_password_hash(password, new_hash), (True, False))
            self.assertEqual(
                json.loads(legacy_path.read_text(encoding="utf-8"))["users"][0]["password_hash"],
                legacy_hash,
            )
            if os.name == "posix":
                self.assertEqual(current_path.stat().st_mode & 0o777, 0o600)

    def test_new_local_account_can_be_created_and_authenticated(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "auth" / "users.json"
            database = Database(local_store_path=path, legacy_store_path=Path(temp) / "missing.json")
            self.assertTrue(database._create_local_user("new-user", "new-password"))
            self.assertFalse(database._create_local_user("new-user", "new-password"))
            result = database._verify_local_password("new-user", "new-password")
            self.assertEqual(result["login"], "new-user")
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(stored["users"][0]["password_hash"].startswith("pbkdf2_sha256$"))

    def test_corrupt_local_store_fails_closed_instead_of_resetting_accounts(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "users.json"
            path.write_text("{invalid", encoding="utf-8")
            database = Database(local_store_path=path, legacy_store_path=Path(temp) / "missing.json")
            with self.assertRaises(RuntimeError):
                database._load_local_store()


    def test_concurrent_local_registrations_do_not_lose_updates(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "users.json"
            legacy = Path(temp) / "missing.json"
            databases = [
                Database(local_store_path=path, legacy_store_path=legacy, backend="local")
                for _ in range(8)
            ]
            registrations = list(zip(databases, [f"user-{index}" for index in range(8)]))
            with ThreadPoolExecutor(max_workers=len(databases)) as executor:
                results = list(executor.map(
                    lambda item: item[0]._create_local_user(item[1], "password-123"),
                    registrations,
                ))
            self.assertEqual(results.count(True), len(databases))
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(stored["users"]), len(databases))
            self.assertEqual(len({user["id"] for user in stored["users"]}), len(databases))

    def test_backend_is_selected_once_and_local_can_be_explicit(self):
        with patch("admin.database.MYSQL_AVAILABLE", True), patch.dict(os.environ, {"EVO_AUTH_BACKEND": "local"}):
            database = Database(local_store_path=Path(tempfile.gettempdir()) / "unused-auth.json")
        self.assertEqual(database.backend, "local")

    def test_local_backend_ignores_invalid_mysql_port_configuration(self):
        with patch.dict(os.environ, {"DB_PORT": "not-a-port", "EVO_AUTH_BACKEND": "local"}):
            database = Database(local_store_path=Path(tempfile.gettempdir()) / "unused-auth.json")
        self.assertEqual(database.backend, "local")
        self.assertIsNone(database.port)

    def test_backend_defaults_to_mysql_only_when_driver_is_available(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EVO_AUTH_BACKEND", None)
            with patch("admin.database.MYSQL_AVAILABLE", True):
                self.assertEqual(Database().backend, "mysql")
            with patch("admin.database.MYSQL_AVAILABLE", False):
                self.assertEqual(Database().backend, "local")

    def test_invalid_backend_configuration_is_rejected(self):
        with patch.dict(os.environ, {"EVO_AUTH_BACKEND": "fallback"}):
            with self.assertRaisesRegex(ValueError, "EVO_AUTH_BACKEND"):
                Database()

    def test_mysql_registration_failure_never_writes_to_local_store(self):
        from admin.database import AuthStorageUnavailable
        with tempfile.TemporaryDirectory() as temp:
            local_path = Path(temp) / "users.json"
            database = Database(local_store_path=local_path, backend="mysql")
            with patch.object(database, "_get_connection", side_effect=RuntimeError("offline")):
                with self.assertRaises(AuthStorageUnavailable):
                    database.create_user("mysql-user", "password-123")
            self.assertFalse(local_path.exists())

    def test_mysql_login_failure_never_authenticates_from_local_store(self):
        from admin.database import AuthStorageUnavailable
        with tempfile.TemporaryDirectory() as temp:
            local_path = Path(temp) / "users.json"
            database = Database(local_store_path=local_path, backend="mysql")
            database._save_local_store({"users": [{
                "id": 1,
                "username": "local-only-user",
                "password_hash": hash_password("password-123"),
                "name": "Local User",
                "login_type": "password",
            }]})
            with patch.object(database, "_get_connection", side_effect=RuntimeError("offline")):
                with self.assertRaises(AuthStorageUnavailable):
                    database.verify_password("local-only-user", "password-123")

    def test_local_backend_never_attempts_mysql(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Database(local_store_path=Path(temp) / "users.json", backend="local")
            with patch.object(database, "_get_connection", side_effect=AssertionError("must not connect")):
                self.assertTrue(database.create_user("local-user", "password-123"))
                self.assertEqual(database.verify_password("local-user", "password-123")["login"], "local-user")


if __name__ == "__main__":
    unittest.main()
