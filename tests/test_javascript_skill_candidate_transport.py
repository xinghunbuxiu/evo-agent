"""The JavaScript reconstruct worker preserves an explicit Skill candidate artifact."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.capabilities import TaskResult
from workers.javascript_reverse import runtime


class JavaScriptSkillCandidateTransportTests(unittest.TestCase):
    def test_reconstruct_handler_preserves_candidate_from_capability_result(self):
        candidate = {
            "id": "skill_worker_candidate",
            "name": "Worker candidate",
            "domain": "python",
            "description": "Explicit executable artifact from the capability result",
            "code": "def run(context):\\n    return {'ok': True}\\n",
            "execution_contract": {
                "kind": "python_run_context",
                "replay_eligible": True,
            },
        }

        class DecisionEngine:
            def execute(self, **kwargs):
                self.asserted_kwargs = kwargs
                return TaskResult(
                    success=True,
                    capability_id="builtin.javascript",
                    task_type="reconstruct",
                    summary="reconstruct completed",
                    data={
                        "success": True,
                        "target_dir": "/tmp/project",
                        "evaluation_verdict": "pass",
                        "evaluation_metrics": {"has_target_dir": True},
                        "skill_candidate": candidate,
                    },
                )

        with tempfile.TemporaryDirectory() as tmp:
            engine = DecisionEngine()
            task = SimpleNamespace(
                id="task-reconstruct",
                tenant_id="tenant-a",
                payload={
                    "path": str(Path(tmp) / "bundle.zip"),
                    "source_dir": tmp,
                    "analysis_result": {"frameworks": ["vue"]},
                },
            )
            with mock.patch.object(runtime, "infer_pre_execution_hints", return_value={}):
                handler = runtime.create_reconstruct_handler(
                    workspace=Path(tmp),
                    task_queue=object(),
                    decision_engine=engine,
                    extract_task_diagnostics=lambda *_args, **_kwargs: {},
                )
                result = handler(task)

        self.assertEqual(result["skill_candidate"], candidate)
        self.assertEqual(result["evaluation_verdict"], "pass")
        self.assertEqual(engine.asserted_kwargs["tenant_id"], "tenant-a")
        self.assertEqual(engine.asserted_kwargs["task_type"], "reconstruct")


if __name__ == "__main__":
    unittest.main()
