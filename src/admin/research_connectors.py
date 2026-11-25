"""Public web research connectors for external learning.

Search results are untrusted evidence, not instructions. Queries are sanitized before
leaving the process; callers must validate any candidate before promoting it.
"""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, urlparse, urlunparse
from urllib.request import Request, urlopen
import re

SEARCH_URL = "https://html.duckduckgo.com/html/"
OFFICIAL_DOC_DOMAINS = (
    "developer.mozilla.org",
    "docs.python.org",
    "nodejs.org",
    "docs.github.com",
    "learn.microsoft.com",
    "developer.apple.com",
    "developers.google.com",
    "docs.oracle.com",
    "kubernetes.io",
    "docs.docker.com",
)
MAX_RESULTS = 5


def sanitize_research_query(value: str) -> str:
    """Remove likely private local paths, URLs, email addresses and credentials."""
    query = str(value or "")
    query = re.sub(r"(?i)\b(?:https?://|www\.)\S+", " ", query)
    query = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", " ", query, flags=re.I)
    query = re.sub(r"(?<!\w)(?:/Users/|/home/|/private/|[A-Z]:\\)[^\s,;]+", " ", query)
    query = re.sub(r"(?i)\b(?:api[_ -]?key|token|password|secret)\s*[:=]\s*\S+", " ", query)
    query = re.sub(r"\b[a-f0-9]{32,}\b", " ", query, flags=re.I)
    return " ".join(query.split())[:400]


class _SearchResults(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self._current = None
        self._field = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._current = {"title": "", "url": attrs.get("href", ""), "snippet": ""}
            self.items.append(self._current)
            self._field = "title"
        elif self._current is not None and tag in {"a", "div", "td"} and (
            "result__snippet" in classes or "result-snippet" in classes
        ):
            self._field = "snippet"

    def handle_data(self, data):
        if self._current is not None and self._field in {"title", "snippet"}:
            self._current[self._field] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._field == "title":
            self._field = None


def _normalize_result_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            raw_url = target
            parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def search_public_web(queries: list[str], *, official_only: bool = False, limit: int = MAX_RESULTS) -> dict:
    """Search public web pages with DuckDuckGo HTML; no API key or paid service required."""
    clean_queries = [sanitize_research_query(q) for q in queries if sanitize_research_query(q)]
    if official_only:
        domains = " OR ".join(f"site:{domain}" for domain in OFFICIAL_DOC_DOMAINS)
        clean_queries = [f"{domains} {q}" for q in clean_queries]
    if not clean_queries:
        return {"status": "no_query", "results": [], "detail": "no_searchable_query"}

    results = []
    seen = set()
    try:
        for query in clean_queries[:3]:
            request = Request(
                SEARCH_URL + "?q=" + quote_plus(query),
                headers={"User-Agent": "EvoAgent/1.0 (public documentation research)"},
            )
            with urlopen(request, timeout=8) as response:
                parser = _SearchResults()
                parser.feed(response.read(1_500_000).decode("utf-8", errors="replace"))
            for item in parser.items:
                url = _normalize_result_url(item["url"])
                if not url or url in seen:
                    continue
                host = (urlparse(url).hostname or "").lower()
                if official_only and not any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_DOC_DOMAINS):
                    continue
                seen.add(url)
                results.append({
                    "title": " ".join(item["title"].split())[:200],
                    "url": url,
                    "snippet": " ".join(item["snippet"].split())[:500],
                    "query": query,
                })
                if len(results) >= max(1, min(int(limit), MAX_RESULTS)):
                    break
            if len(results) >= max(1, min(int(limit), MAX_RESULTS)):
                break
    except Exception as exc:  # noqa: BLE001 - connector failures are reported to Mission
        return {"status": "error", "results": results, "detail": f"{type(exc).__name__}: {str(exc)[:180]}"}

    return {
        "status": "completed" if results else "no_match",
        "results": results,
        "detail": None if results else "search_returned_no_results",
    }


def search_web(queries: list[str], *, limit: int = MAX_RESULTS) -> dict:
    return search_public_web(queries, official_only=False, limit=limit)


def search_official_docs(queries: list[str], *, limit: int = MAX_RESULTS) -> dict:
    return search_public_web(queries, official_only=True, limit=limit)
