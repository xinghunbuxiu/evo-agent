"""Policy regression tests for Mission's external research routing."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.external_learning_runtime import create_external_learning_runtime_bindings  # noqa: E402


class _TenantManager:
    def __init__(self, *, allow_web_research):
        self.policy = {
            "source_priority": ["local_memory", "official_docs", "web_search", "ai_assist"],
            "allow_web_research": allow_web_research,
            "allow_ai_assist": False,
            "allow_enterprise_sources": False,
            "validation_required": True,
        }

    def get_external_learning_policy(self, tenant_id):
        return dict(self.policy)

    def get_git_knowledge_config(self, tenant_id):
        return {"repos": {}}


def _bindings():
    return create_external_learning_runtime_bindings(
        list_platform_strategy_promotions=lambda *args, **kwargs: [],
        load_review_queue=lambda *args, **kwargs: [],
        load_enterprise_repo_index=lambda *args, **kwargs: {"repos": {}},
        trim_candidate_text=lambda value, limit=280: str(value or "")[:limit],
        make_learning_task_id=lambda tenant_id, sample: "learning-test",
        build_diagnosis_signature=lambda diagnosis: {},
        build_review_item_signature=lambda item: {},
        score_signature_similarity=lambda left, right: (0.0, []),
    )


class ExternalLearningPolicyTests(unittest.TestCase):
    def test_disabled_web_research_excludes_web_and_official_docs_sources(self):
        plan = _bindings()["build_external_learning_plan"](
            tenant_manager=_TenantManager(allow_web_research=False),
            tenant_id="tenant-a",
            diagnosis={
                "research_state": "blocked",
                "stable": False,
                "analyze": {"issue_category": "execution_error"},
                "reconstruct": {},
                "bundle_path": "/private/project/source.js",
            },
        )

        self.assertIn("local_memory", plan["preferred_sources"])
        self.assertNotIn("web_search", plan["preferred_sources"])
        self.assertNotIn("official_docs", plan["preferred_sources"])
        self.assertNotIn("ai_assist", plan["preferred_sources"])

    def test_enabled_web_research_allows_configured_web_sources(self):
        plan = _bindings()["build_external_learning_plan"](
            tenant_manager=_TenantManager(allow_web_research=True),
            tenant_id="tenant-a",
            diagnosis={
                "research_state": "blocked",
                "stable": False,
                "analyze": {"issue_category": "execution_error"},
                "reconstruct": {},
                "bundle_path": "/private/project/source.js",
            },
        )

        self.assertIn("web_search", plan["preferred_sources"])
        self.assertIn("official_docs", plan["preferred_sources"])
        self.assertNotIn("ai_assist", plan["preferred_sources"])


if __name__ == "__main__":
    unittest.main()
