"""Tests for web research result parsing and official-source filtering."""
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from admin.web_research_runtime import run_web_research  # noqa: E402


HTML = """
<html><body>
  <div class="result">
    <a class="result__a" href="https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API">MDN Fetch API</a>
    <a class="result__snippet">Official Fetch API <b>documentation</b> and examples.</a>
  </div>
  <div class="result">
    <a class="result__a" href="https://example.com/unofficial">Unofficial guide</a>
    <a class="result__snippet">A community-written overview.</a>
  </div>
</body></html>
"""


class WebResearchRuntimeTests(unittest.TestCase):
    def test_web_search_returns_url_and_query_as_evidence(self):
        with patch(
            "admin.web_research_runtime.urlopen",
            return_value=io.BytesIO(HTML.encode("utf-8")),
        ) as open_url:
            result = run_web_research(source="web_search", queries=["fetch API"])

        open_url.assert_called_once()
        self.assertEqual(result["status"], "completed")
        candidate = result["candidates"][0]
        self.assertEqual(candidate["source"], "web_search")
        self.assertEqual(candidate["title"], "MDN Fetch API")
        self.assertIn("url=https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API", candidate["evidence"])
        self.assertIn("query=fetch API", candidate["evidence"])
        self.assertIn("Official Fetch API documentation", candidate["summary"])

    def test_official_docs_rejects_non_official_hosts(self):
        with patch(
            "admin.web_research_runtime.urlopen",
            return_value=io.BytesIO(HTML.encode("utf-8")),
        ):
            result = run_web_research(source="official_docs", queries=["fetch API"])

        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["source"], "official_docs")
        self.assertEqual(
            result["candidates"][0]["metadata"]["url"],
            "https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API",
        )

    def test_empty_query_is_not_reported_as_connector_waiting(self):
        result = run_web_research(source="web_search", queries=[])
        self.assertEqual(result["status"], "no_query")
        self.assertEqual(result["candidates"], [])


if __name__ == "__main__":
    unittest.main()
