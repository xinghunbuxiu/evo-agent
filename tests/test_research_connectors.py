"""Tests for privacy-aware public web research connectors."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin import research_connectors  # noqa: E402


class _Response:
    def __init__(self, body):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit=-1):
        return self.body[:limit]


class ResearchConnectorTests(unittest.TestCase):
    def test_query_sanitizer_removes_paths_urls_emails_and_credentials(self):
        query = (
            "debug /Users/alice/private/app.js https://internal.example/path "
            "alice@example.com api_key=secret-value diagnose parser"
        )
        clean = research_connectors.sanitize_research_query(query)
        self.assertNotIn("/Users/alice", clean)
        self.assertNotIn("https://internal.example", clean)
        self.assertNotIn("alice@example.com", clean)
        self.assertNotIn("secret-value", clean)
        self.assertIn("diagnose parser", clean)

    def test_web_search_returns_url_title_snippet_as_evidence(self):
        html = """
        <div class="result">
          <a class="result__a" href="https://developer.mozilla.org/en-US/docs/Web/JavaScript">JavaScript Guide</a>
          <a class="result__snippet">Official language documentation</a>
        </div>
        """
        with patch.object(research_connectors, "urlopen", return_value=_Response(html)) as opener:
            result = research_connectors.search_web(["JavaScript guide"])

        opener.assert_called_once()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["results"][0]["title"], "JavaScript Guide")
        self.assertEqual(result["results"][0]["url"], "https://developer.mozilla.org/en-US/docs/Web/JavaScript")
        self.assertIn("Official language documentation", result["results"][0]["snippet"])

    def test_official_docs_rejects_non_allowlisted_domains(self):
        html = """
        <div class="result">
          <a class="result__a" href="https://developer.mozilla.org/en-US/docs/Web/JavaScript">MDN</a>
          <a class="result__snippet">Official docs</a>
        </div>
        <div class="result">
          <a class="result__a" href="https://example.com/javascript">Example Blog</a>
          <a class="result__snippet">Not official docs</a>
        </div>
        """
        with patch.object(research_connectors, "urlopen", return_value=_Response(html)):
            result = research_connectors.search_official_docs(["JavaScript guide"])

        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["url"], "https://developer.mozilla.org/en-US/docs/Web/JavaScript")


if __name__ == "__main__":
    unittest.main()
