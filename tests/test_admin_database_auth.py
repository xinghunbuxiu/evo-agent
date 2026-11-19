"""Security regression tests for password hashing and local auth-store migration."""
import hashlib
import json
import os
import sys
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
        self.assertEqual(len(first), 4)
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
            self.assertFalse(current_path.exists())
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

    def test_corrupt_local_store_fails_closed_instead_of_resetting_accounts(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "users.json"
            path.write_text("{invalid", encoding="utf-8")
            database = Database(local_store_path=path, legacy_store_path=Path(temp) / "missing.json")
            with self.assertRaises(RuntimeError):
                database._load_local_store()


if __name__ == "__main__":
    unittest.main()
