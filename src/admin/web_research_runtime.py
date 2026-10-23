"""Evidence-preserving web research for external learning."""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

_OFFICIAL_HOSTS = {"developer.mozilla.org", "nodejs.org", "docs.github.com"}


class _Results(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if self.current is not None:
            self.depth += 1
            return
        if tag == "a" and "result__a" in classes:
            url = attrs.get("href") or ""
            parsed = urlparse(url)
            if (parsed.hostname or "").endswith("duckduckgo.com"):
                url = parse_qs(parsed.query).get("uddg", [url])[0]
            self.current = {"title": "", "url": url, "snippet": ""}
            self.items.append(self.current)
            self.field = "title"
            self.depth = 1
        elif "result__snippet" in classes and self.items:
            self.current = self.items[-1]
            self.field = "snippet"
            self.depth = 1

    def handle_data(self, data):
        if self.current is not None:
            self.current[self.field] += data

    def handle_endtag(self, tag):
        if self.current is None:
            return
        self.depth -= 1
        if self.depth <= 0:
            self.current = None


def _search(query, timeout):
    url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
    request = Request(url, headers={"User-Agent": "EvoResearch/1.0", "Accept": "text/html"})
    with urlopen(request, timeout=timeout) as response:
        html = response.read().decode("utf-8", errors="replace")
    if "anomaly-modal" in html.lower():
        raise RuntimeError("search_provider_blocked")
    parser = _Results()
    parser.feed(html)
    results = []
    seen = set()
    for item in parser.items:
        url = str(item["url"]).strip()
        parsed = urlparse(url)
        title = " ".join(str(item["title"]).split())[:180]
        snippet = " ".join(str(item["snippet"]).split())[:500]
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not title or url in seen:
            continue
        seen.add(url)
        results.append({"title": title, "url": url, "snippet": snippet})
    return results


def run_web_research(*, source, queries, limit=5, timeout_sec=10.0):
    if source not in {"web_search", "official_docs"}:
        return {"status": "error", "candidates": [], "detail": "unsupported_research_source"}
    queries = [str(q).strip() for q in queries if str(q).strip()][:3]
    if not queries:
        return {"status": "no_query", "candidates": [], "detail": "no_research_queries"}
    candidates, seen, errors = [], set(), []
    for query in queries:
        search_query = query
        if source == "official_docs":
            search_query += " (site:developer.mozilla.org OR site:nodejs.org OR site:docs.github.com)"
        try:
            results = _search(search_query, timeout_sec)
        except Exception as exc:
            errors.append(str(exc)[:180] or exc.__class__.__name__)
            continue
        for item in results:
            host = (urlparse(item["url"]).hostname or "").lower()
            if source == "official_docs" and not any(host == h or host.endswith("." + h) for h in _OFFICIAL_HOSTS):
                continue
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            candidates.append({
                "source": source, "title": item["title"],
                "summary": item["snippet"] or item["title"],
                "confidence": 0.65 if source == "official_docs" else 0.52,
                "evidence": [f"query={query}", f"url={item['url']}", "search_engine=duckduckgo_html"],
                "next_steps": ["核对来源原文", "对修复方案执行真实样本重放验证"],
                "metadata": {"url": item["url"], "query": query, "search_engine": "duckduckgo_html"},
            })
            if len(candidates) >= max(1, limit):
                break
        if len(candidates) >= max(1, limit):
            break
    if candidates:
        return {"status": "completed", "candidates": candidates, "detail": "; ".join(errors)[:240] or None}
    if errors:
        return {"status": "error", "candidates": [], "detail": "; ".join(errors)[:240]}
    return {"status": "no_match", "candidates": [], "detail": None}


__all__ = ["run_web_research"]
