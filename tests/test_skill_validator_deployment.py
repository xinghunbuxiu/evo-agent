"""Deployment contract tests for the independent Validator socket boundary."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SkillValidatorDeploymentTests(unittest.TestCase):
    def test_validator_socket_group_is_separate_from_broker_group(self):
        unit = (ROOT / "deploy" / "evo-skill-validator.service.example").read_text(encoding="utf-8")
        runbook = (ROOT / "deploy" / "systemd" / "README.md").read_text(encoding="utf-8")

        self.assertIn("User=evo-validator", unit)
        self.assertIn("Group=evo-validator-client", unit)
        self.assertIn("RuntimeDirectory=evo-skill-validator", unit)
        self.assertIn("RuntimeDirectoryMode=0750", unit)
        self.assertNotIn("Group=evo-broker", unit)
        self.assertIn("evo-validator-client", runbook)
        self.assertIn("Do not authorize worker, runner or general-purpose user accounts", runbook)
        self.assertIn("The Validator\nshould not be able to open the Broker socket.", runbook)


if __name__ == "__main__":
    unittest.main()
