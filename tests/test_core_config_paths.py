"""Regression tests for deterministic distributed-config path resolution."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import ConfigLoader


def _config(owner: str) -> dict:
    return {
        "version": "test",
        "platform": "evo",
        "api_base": "https://example.invalid/api",
        "repos": {
            name: {"owner": owner, "repo": name, "branch": "main"}
            for name in ("registry", "experiences", "knowledge")
        },
    }


class ConfigPathResolutionTests(unittest.TestCase):
    def _write_config(self, path: Path, owner: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_config(owner)), encoding="utf-8")

    def test_workspace_config_is_used_when_no_explicit_environment_path(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            config_path = workspace / ".config" / "evo.json"
            self._write_config(config_path, "workspace-owner")
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("EVO_CONFIG_PATH", None)
                self.assertEqual(ConfigLoader.find_config_file(workspace), config_path)
                loaded = ConfigLoader.load(workspace)
            self.assertEqual(loaded.registry.owner, "workspace-owner")

    def test_explicit_environment_path_has_highest_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace_path = root / "workspace" / ".config" / "evo.json"
            environment_path = root / "explicit.json"
            self._write_config(workspace_path, "workspace-owner")
            self._write_config(environment_path, "environment-owner")
            with patch.dict(os.environ, {"EVO_CONFIG_PATH": str(environment_path)}):
                loaded = ConfigLoader.load(root / "workspace")
            self.assertEqual(loaded.registry.owner, "environment-owner")
            self.assertEqual(loaded.to_dict()["repos"]["registry"]["owner"], "environment-owner")

    def test_environment_path_is_read_at_call_time_not_module_import_time(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first.json"
            second = Path(temp) / "second.json"
            self._write_config(first, "first-owner")
            self._write_config(second, "second-owner")
            with patch.dict(os.environ, {"EVO_CONFIG_PATH": str(first)}):
                self.assertEqual(ConfigLoader.find_config_file(), first)
            with patch.dict(os.environ, {"EVO_CONFIG_PATH": str(second)}):
                self.assertEqual(ConfigLoader.find_config_file(), second)


if __name__ == "__main__":
    unittest.main()
