"""Web search without API keys: DuckDuckGo (via the `ddgs` package) and Wikipedia, plus an offline mock."""
import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import Settings
from .mock_data import MOCK_DOCS
from .textutils import bm25_rank

log = logging.getLogger("research.search")
UA = {"User-Agent": "DeepResearchLocal/1.0 (educational open-source project)"}


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    content: str = ""  # filled when the provider already has the full text (skips page fetching)


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, max_results: int) -> list: ...


class DuckDuckGoSearch:
    name = "duckduckgo"

    async def search(self, query: str, max_results: int) -> list:
        def _run():
            try:
                from ddgs import DDGS  # current package name
            except ImportError:  # older package name
                from duckduckgo_search import DDGS
            with DDGS() as d:
                return list(d.text(query, max_results=max_results))

        rows = await asyncio.to_thread(_run)
        out = []
        for r in rows:
            url = r.get("href") or r.get("url") or ""
            if url.startswith("http"):
                out.append(SearchResult(title=r.get("title", url), url=url, snippet=r.get("body", "")))
        return out


class WikipediaSearch:
    name = "wikipedia"
    API = "https://en.wikipedia.org/w/api.php"

    async def search(self, query: str, max_results: int) -> list:
        async with httpx.AsyncClient(timeout=12, headers=UA) as c:
            r = await c.get(
                self.API,
                params={"action": "query", "list": "search", "srsearch": query, "srlimit": max_results, "format": "json"},
            )
            r.raise_for_status()
            rows = r.json().get("query", {}).get("search", [])

            async def extract(title: str) -> str:
                rr = await c.get(
                    self.API,
                    params={"action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "plain",
                            "titles": title, "format": "json", "redirects": 1},
                )
                rr.raise_for_status()
                pages = rr.json().get("query", {}).get("pages", {})
                return (next(iter(pages.values()), {}).get("extract") or "")[:60000]

            texts = await asyncio.gather(*[extract(x["title"]) for x in rows], return_exceptions=True)
        out = []
        for row, text in zip(rows, texts):
            if isinstance(text, Exception) or not text:
                continue
            title = row["title"]
            snippet = re.sub(r"<[^>]+>", "", row.get("snippet", ""))
            out.append(SearchResult(title=f"{title} - Wikipedia",
                                    url="https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
                                    snippet=snippet, content=text))
        return out


class MockSearch:
    """Offline demo corpus. Enable with SEARCH_PROVIDER=mock."""
    name = "mock"

    async def search(self, query: str, max_results: int) -> list:
        texts = [d["title"] + ". " + d["text"] for d in MOCK_DOCS]
        out = []
        for idx, _score in bm25_rank(query, texts, k=max_results):
            d = MOCK_DOCS[idx]
            out.append(SearchResult(title=d["title"], url="mock://" + d["id"], snippet=d["text"][:160], content=d["text"]))
        return out


class CompositeSearch:
    """Try providers in order; return the first non-empty result list."""

    def __init__(self, providers: list):
        self.providers = providers
        self.name = "+".join(p.name for p in providers)

    async def search(self, query: str, max_results: int) -> list:
        last = None
        for p in self.providers:
            try:
                res = await p.search(query, max_results)
                if res:
                    return res
            except Exception as exc:  # network blocked, rate limit, package missing ...
                last = exc
                log.warning("search provider %s failed: %s", p.name, exc)
        if last:
            log.warning("all search providers failed or returned nothing (last error: %s)", last)
        return []


def get_search(settings: Settings):
    choice = settings.search_provider
    if choice == "mock":
        return MockSearch()
    if choice == "ddg":
        return DuckDuckGoSearch()
    if choice == "wikipedia":
        return WikipediaSearch()
    return CompositeSearch([DuckDuckGoSearch(), WikipediaSearch()])
