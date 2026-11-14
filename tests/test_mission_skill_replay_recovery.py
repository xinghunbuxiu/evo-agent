"""Startup recovery for interrupted Mission Skill Replay operations."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.mission_runtime import (
    _retain_mission_runs,
    load_mission_runs_strict,
    reconcile_skill_replays_on_startup,
    save_mission_runs,
)


class MissionSkillReplayRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_running_replay_is_marked_interrupted_and_never_reexecuted(self):
        save_mission_runs(self.workspace, {"items": [{
            "mission_run_id": "mission-a",
            "actions": [{
                "action_type": "skill_replay",
                "status": "running",
                "task_id": "task-a",
                "skill_id": "skill-a",
                "node_id": "node-a",
                "evidence_id": None,
            }],
        }]})

        result = reconcile_skill_replays_on_startup(workspace=self.workspace)
        action = load_mission_runs_strict(self.workspace)["items"][0]["actions"][0]

        self.assertEqual(result["replays_marked_interrupted"], 1)
        self.assertEqual(action["status"], "interrupted")
        self.assertEqual(action["recovery_status"], "needs_review")
        self.assertEqual(action["recovery_reason"], "admin_process_restarted_during_replay")
        self.assertEqual(action["task_id"], "task-a")
        self.assertNotIn("evidence_id", action)

        second = reconcile_skill_replays_on_startup(workspace=self.workspace)
        self.assertEqual(second["replays_marked_interrupted"], 0)

    def test_completed_and_failed_replays_are_not_changed(self):
        save_mission_runs(self.workspace, {"items": [{
            "mission_run_id": "mission-a",
            "actions": [
                {"action_type": "skill_replay", "status": "completed", "task_id": "task-a"},
                {"action_type": "skill_replay", "status": "failed", "task_id": "task-b"},
            ],
        }]})
        result = reconcile_skill_replays_on_startup(workspace=self.workspace)
        actions = load_mission_runs_strict(self.workspace)["items"][0]["actions"]
        self.assertEqual(result["replays_marked_interrupted"], 0)
        self.assertEqual([item["status"] for item in actions], ["completed", "failed"])

    def test_interrupted_replay_remains_in_mission_history_retention(self):
        old_run = {
            "mission_run_id": "old",
            "actions": [{
                "action_type": "skill_replay",
                "status": "interrupted",
                "recovery_status": "needs_review",
            }],
        }
        recent = [{"mission_run_id": f"recent-{index}", "actions": []} for index in range(50)]
        retained = _retain_mission_runs([*recent, old_run], limit=50)
        self.assertIn(old_run, retained)


if __name__ == "__main__":
    unittest.main()
