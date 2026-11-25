"""Tests for the single Admin workspace path contract."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.workspace import resolve_admin_workspace


class AdminWorkspaceResolutionTests(unittest.TestCase):
    def test_defaults_to_repository_root_without_environment_override(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            repo.mkdir()
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("EVO_ADMIN_WORKSPACE", None)
                self.assertEqual(resolve_admin_workspace(repo), repo.resolve())

    def test_uses_any_existing_explicit_workspace_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            workspace = Path(temp) / "business-workspace"
            repo.mkdir()
            workspace.mkdir()
            with patch.dict(os.environ, {"EVO_ADMIN_WORKSPACE": str(workspace)}):
                self.assertEqual(resolve_admin_workspace(repo), workspace.resolve())

    def test_rejects_nonexistent_explicit_workspace_instead_of_falling_back(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            repo.mkdir()
            missing = Path(temp) / "missing"
            with patch.dict(os.environ, {"EVO_ADMIN_WORKSPACE": str(missing)}):
                with self.assertRaisesRegex(ValueError, "EVO_ADMIN_WORKSPACE"):
                    resolve_admin_workspace(repo)

    def test_rejects_file_as_explicit_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            repo.mkdir()
            file_path = Path(temp) / "not-a-directory"
            file_path.write_text("x", encoding="utf-8")
            with patch.dict(os.environ, {"EVO_ADMIN_WORKSPACE": str(file_path)}):
                with self.assertRaisesRegex(ValueError, "existing directory"):
                    resolve_admin_workspace(repo)


if __name__ == "__main__":
    unittest.main()
