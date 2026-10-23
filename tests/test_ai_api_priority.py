"""Regression test for the configured AI API taking precedence over local CLI."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.external_learning_runtime import create_external_learning_runtime_bindings  # noqa: E402


class AIResearchPriorityTests(unittest.TestCase):
    def test_completed_api_candidate_prevents_cli_detection(self):
        bindings = create_external_learning_runtime_bindings(
            list_platform_strategy_promotions=lambda workspace, limit: [],
            load_review_queue=lambda workspace, tenant_id: [],
            load_enterprise_repo_index=lambda workspace, tenant_id: {"repos": {}},
            trim_candidate_text=lambda value, limit=280: str(value or "")[:limit],
            make_learning_task_id=lambda tenant_id, sample: "learning-test",
            build_diagnosis_signature=lambda diagnosis: {},
            build_review_item_signature=lambda item: {},
            score_signature_similarity=lambda left, right: (0.0, []),
        )
        api_candidate = {
            "source": "ai_assist",
            "title": "API research",
            "summary": "Research from configured API",
            "confidence": 0.72,
            "evidence": ["provider=test", "model=test-model"],
            "next_steps": ["validate against sample"],
            "metadata": {},
        }
        with patch(
            "admin.model_provider_runtime.run_configured_ai_assist",
            return_value={"status": "completed", "candidate": api_candidate, "detail": None},
        ) as api_assist, patch(
            "admin.external_learning_runtime.shutil.which",
            side_effect=AssertionError("CLI must not be detected after successful API research"),
        ):
            with tempfile.TemporaryDirectory() as directory:
                result = bindings["execute_learning_task"](
                    workspace=Path(directory),
                    tenant_manager=object(),
                    tenant_id="tenant-test",
                    sample={"source_dir": "/tmp/sample", "bundle_path": "/tmp/sample", "sample_signature": "sample"},
                    diagnosis={
                        "bundle_path": "/tmp/sample",
                        "research_state": "blocked",
                        "stable": False,
                        "analyze": {"issue_category": "execution_error"},
                        "reconstruct": {},
                    },
                    learning_plan={
                        "preferred_sources": ["ai_assist"],
                        "queries": ["diagnose execution failure"],
                        "policy": {"validation_required": True},
                        "validation_gate": "replay required",
                    },
                )

        api_assist.assert_called_once()
        self.assertEqual(result["source_runs"][0]["status"], "completed")
        self.assertEqual(result["candidate_approaches"][0]["title"], "API research")


if __name__ == "__main__":
    unittest.main()
