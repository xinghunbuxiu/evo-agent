"""Deployment contract tests for the independent Validator socket boundary."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SkillValidatorDeploymentTests(unittest.TestCase):
    def test_validator_socket_group_is_separate_from_broker_group(self):
        unit = (ROOT / "deploy" / "evo-skill-validator.service.example").read_text(encoding="utf-8")
        runbook = (ROOT / "deploy" / "systemd" / "README.md").read_text(encoding="utf-8")
        normalized_runbook = " ".join(runbook.lower().split())

        self.assertIn("User=evo-validator", unit)
        self.assertIn("Group=evo-validator-client", unit)
        self.assertIn("RuntimeDirectory=evo-skill-validator", unit)
        self.assertIn("RuntimeDirectoryMode=0750", unit)
        self.assertIn("StateDirectory=evo-skill-validator", unit)
        self.assertIn("StateDirectoryMode=0700", unit)
        self.assertIn("/var/lib/evo-skill-validator", unit)
        self.assertNotIn("Group=evo-broker", unit)
        self.assertIn("evo-validator-client", runbook)
        self.assertIn("replay_store_path", runbook)
        self.assertIn("/var/lib/evo-skill-validator/requests.sqlite3", runbook)
        self.assertIn("do not authorize worker, runner or general-purpose user accounts", normalized_runbook)
        self.assertIn("the validator should not be able to open the broker socket.", normalized_runbook)


if __name__ == "__main__":
    unittest.main()
