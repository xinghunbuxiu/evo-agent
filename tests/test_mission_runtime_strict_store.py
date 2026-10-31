import tempfile
import unittest
from pathlib import Path

from admin.mission_runtime import load_mission_runs_strict


class MissionRunsStrictStoreTests(unittest.TestCase):
    def test_missing_store_is_an_empty_store(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(
                load_mission_runs_strict(Path(temp_dir)),
                {"updated_at": None, "items": []},
            )

    def test_valid_store_is_loaded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = workspace / ".admin" / "mission_runs.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                '{"updated_at":"2026-10-30T10:00:00","items":[{"mission_run_id":"run-a"}]}',
                encoding="utf-8",
            )
            state = load_mission_runs_strict(workspace)
            self.assertEqual(state["items"][0]["mission_run_id"], "run-a")

    def test_corrupt_json_is_not_converted_to_empty_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = workspace / ".admin" / "mission_runs.json"
            path.parent.mkdir(parents=True)
            path.write_text('{"items":[', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_mission_runs_strict(workspace)

    def test_invalid_store_shapes_are_rejected(self):
        invalid_payloads = ['[]', '{}', '{"items":{}}', '{"items":[null]}']
        for payload in invalid_payloads:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)
                path = workspace / ".admin" / "mission_runs.json"
                path.parent.mkdir(parents=True)
                path.write_text(payload, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_mission_runs_strict(workspace)


if __name__ == "__main__":
    unittest.main()
