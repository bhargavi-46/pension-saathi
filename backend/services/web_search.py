"""WebSearchService — fresh public-web knowledge, via a *dedicated* search API.

We deliberately DO NOT use Gemini's built-in grounding for this. Web search is
a search problem — the right tool is a search API. Using the LLM as a search
engine mixes retrieval with generation, wastes tokens, and gives us no direct
control over freshness or citations.

Supported providers (auto-picked from whichever key is set, or pinned with
WEB_SEARCH_PROVIDER):
    - tavily : search API purpose-built for LLM agents (TAVILY_API_KEY)
    - serper : Google results via serper.dev (SERPER_API_KEY)
    - brave  : Brave Search API (BRAVE_SEARCH_API_KEY)

If no key is set the service returns a small mock result set so callers keep
working end-to-end (matches the "always demoable" pattern used elsewhere).
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()


# ------------------------------------------------------------------- Tavily
class _TavilyProvider:
    name = "tavily"

    def __init__(self) -> None:
        self.api_key = os.getenv("TAVILY_API_KEY", "").strip()
        self.enabled = bool(self.api_key)

    def search(self, query: str, top_k: int) -> list[dict]:
        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self.api_key,
                "query": query,
                "max_results": top_k,
                "search_depth": "basic",
                "include_answer": False,
            },
            timeout=20,
        )
        r.raise_for_status()
        return [
            {"title": h.get("title", ""), "url": h.get("url", ""), "snippet": h.get("content", "")}
            for h in r.json().get("results", [])
        ]


# ------------------------------------------------------------------- Serper
class _SerperProvider:
    name = "serper"

    def __init__(self) -> None:
        self.api_key = os.getenv("SERPER_API_KEY", "").strip()
        self.enabled = bool(self.api_key)

    def search(self, query: str, top_k: int) -> list[dict]:
        r = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
            json={"q": query, "num": top_k, "gl": "in", "hl": "en"},
            timeout=20,
        )
        r.raise_for_status()
        return [
            {"title": h.get("title", ""), "url": h.get("link", ""), "snippet": h.get("snippet", "")}
            for h in r.json().get("organic", [])[:top_k]
        ]


# -------------------------------------------------------------------- Brave
class _BraveProvider:
    name = "brave"

    def __init__(self) -> None:
        self.api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
        self.enabled = bool(self.api_key)

    def search(self, query: str, top_k: int) -> list[dict]:
        r = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
            params={"q": query, "count": top_k, "country": "IN"},
            timeout=20,
        )
        r.raise_for_status()
        return [
            {"title": h.get("title", ""), "url": h.get("url", ""), "snippet": h.get("description", "")}
            for h in r.json().get("web", {}).get("results", [])[:top_k]
        ]


# --------------------------------------------------------------------- mock
class _MockProvider:
    name = "mock"
    enabled = True

    def search(self, query: str, top_k: int) -> list[dict]:
        # A stable, harmless result set so callers get something useful in a
        # zero-config demo. Not real answers — intentionally labelled as mock.
        stub = [
            {
                "title": "National Widow Pension Scheme (IGNWPS) — nsap.nic.in",
                "url": "https://nsap.nic.in/",
                "snippet": "Central social-welfare pension for BPL widows aged 40+. State-topped.",
            },
            {
                "title": "State widow pension schemes — India.gov.in",
                "url": "https://www.india.gov.in/",
                "snippet": "State-run widow pensions vary by state; check the social welfare portal.",
            },
            {
                "title": f"(mock search) — no WEB_SEARCH key set; query was: {query}",
                "url": "",
                "snippet": "Set TAVILY_API_KEY / SERPER_API_KEY / BRAVE_SEARCH_API_KEY for live results.",
            },
        ]
        return stub[:top_k]


class WebSearchService:
    """Picks the first configured provider, or mock if none is."""

    def __init__(self) -> None:
        tavily = _TavilyProvider()
        serper = _SerperProvider()
        brave = _BraveProvider()
        self._by_name = {p.name: p for p in (tavily, serper, brave)}
        self._mock = _MockProvider()

        pinned = os.getenv("WEB_SEARCH_PROVIDER", "").strip().lower()
        if pinned in self._by_name and self._by_name[pinned].enabled:
            self.provider = self._by_name[pinned]
        else:
            self.provider = next(
                (p for p in (tavily, serper, brave) if p.enabled), self._mock
            )
        self.mock = self.provider is self._mock
        print(f"[web-search] provider — {self.provider.name} (mock: {'on' if self.mock else 'off'})")

    def search(self, query: str, top_k: int = 5) -> dict:
        try:
            results = self.provider.search(query, top_k)
            return {"provider": self.provider.name, "query": query, "results": results}
        except Exception as e:
            print(f"[web-search] {self.provider.name} failed: {str(e)[:150]} — mock fallback")
            return {
                "provider": "mock",
                "query": query,
                "results": self._mock.search(query, top_k),
            }


web_search_service = WebSearchService()
