"""The research workflow: clarification -> brief -> research execution -> final report.

It is an async generator of event dicts. The same event types as the tutorial project are used:
session_start, stage_start, research_step, research_finding, research_complete (plus `error`).
"""
import asyncio
import re
import time
from typing import AsyncIterator

from .config import Settings
from .fetch import fetch_text
from .llm import LLMError, make_llm
from .models import ResearchRequest
from .reasoner import NO_INFO, ExtractiveReasoner, LLMReasoner, Passage, sanitize_citations, topic_of
from .textutils import bm25_rank, chunk_passages, clean_text, tokenize

# depth -> (number of sub-questions, sources per sub-question)
DEPTH = {"quick": (3, 3), "standard": (5, 4), "deep": (7, 5)}


def ev(type_: str, content: str = "", **extra) -> dict:
    return {"type": type_, "content": content, "ts": round(time.time(), 3), **extra}


def build_reasoner(mode: str, model, settings: Settings):
    if mode == "extractive":
        return ExtractiveReasoner()
    return LLMReasoner(make_llm(mode, model, settings))


class SourceRegistry:
    def __init__(self):
        self._by_url, self.items = {}, []

    def add(self, title: str, url: str) -> int:
        if url in self._by_url:
            return self._by_url[url]
        sid = len(self.items) + 1
        self.items.append({"id": sid, "title": title or url, "url": url})
        self._by_url[url] = sid
        return sid


def pick_passages(question: str, passages: list, k: int = 6, per_source: int = 3) -> list:
    ranked = bm25_rank(question, [p.text for p in passages], k=max(k * 3, 12))
    chosen, used = [], {}
    for idx, _ in ranked:
        p = passages[idx]
        if used.get(p.source_id, 0) >= per_source:
            continue
        chosen.append(p)
        used[p.source_id] = used.get(p.source_id, 0) + 1
        if len(chosen) >= k:
            break
    return chosen


def finish_report(body: str, registry: SourceRegistry):
    """Validate citations, drop any model-written source list, append the real one. Returns (markdown, used_sources)."""
    valid = {s["id"] for s in registry.items}
    body = sanitize_citations(body, valid)
    body = re.split(r"\n#{1,4}\s*(?:sources|references)\b", body, flags=re.I)[0].rstrip()
    cited = {int(n) for grp in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", body) for n in re.findall(r"\d+", grp)}
    used = [s for s in registry.items if s["id"] in cited] or list(registry.items)
    lines = ["", "", "## Sources"] + [f"{s['id']}. {s['title']} - {s['url']}" for s in used]
    return body + "\n".join(lines), used


async def run_research(req: ResearchRequest, settings: Settings, search, reasoner) -> AsyncIterator[dict]:
    n_questions, n_sources = DEPTH[req.depth]
    yield ev("session_start", "Starting research...", mode=req.mode, depth=req.depth,
             search=getattr(search, "name", ""), engine=getattr(reasoner, "name", ""))

    # 1. Clarification (answers, if any, arrive as req.context; the questions come from /research/clarify)
    yield ev("stage_start", "Checking whether the request needs clarification", stage="clarification")
    yield ev("research_step", "Using your clarifications." if req.context else "Proceeding with the request as written.",
             stage="clarification")

    # 2. Research brief
    yield ev("stage_start", "Writing the research brief", stage="brief")
    try:
        questions = await reasoner.plan(req.query, req.context, n_questions)
    except LLMError as exc:
        yield ev("error", str(exc))
        return
    yield ev("research_step", f"Planned {len(questions)} sub-questions.", stage="brief", questions=questions)

    # 3. Research execution (sub-questions run concurrently; events are streamed as they happen)
    yield ev("stage_start", "Researching the sub-questions", stage="research")
    registry = SourceRegistry()
    topic_terms = set(tokenize(topic_of(req.query)))  # passages must mention the real topic
    findings = [None] * len(questions)
    queue: asyncio.Queue = asyncio.Queue()
    DONE = object()
    q_sem = asyncio.Semaphore(settings.subquestion_concurrency)
    f_sem = asyncio.Semaphore(settings.fetch_concurrency)

    async def worker(i: int, q: str):
        try:
            async with q_sem:
                await queue.put(ev("research_step", f"Searching: {q}", stage="research", index=i))
                results = await search.search(q, n_sources)

                async def read_one(r):
                    text = r.content
                    if not text:
                        async with f_sem:
                            text = await fetch_text(r.url, settings)
                    text = clean_text(text or r.snippet or "")
                    if len(text) < 60:
                        return []
                    sid = registry.add(r.title, r.url)
                    await queue.put(ev("research_step", f"Reading: {r.title}", stage="research", index=i,
                                       url=r.url, source_id=sid))
                    return [Passage(p, sid) for p in chunk_passages(text)]

                lists = await asyncio.gather(*[read_one(r) for r in results])
                passages = [p for lst in lists for p in lst]
                if topic_terms:
                    passages = [p for p in passages if topic_terms & set(tokenize(p.text))]
                top = pick_passages(q, passages)
                text = await reasoner.summarize(q, top) if top else NO_INFO
                text = sanitize_citations(text, {p.source_id for p in top})
                sids = sorted({p.source_id for p in top})
                findings[i] = {"question": q, "text": text, "sources": sids}
                await queue.put(ev("research_finding", text, stage="research", index=i, question=q, sources=sids))
        except LLMError as exc:
            await queue.put(ev("error", str(exc)))
        except Exception as exc:  # one failed sub-question should not end the whole run
            findings[i] = {"question": q, "text": NO_INFO, "sources": []}
            await queue.put(ev("research_step", f"Could not research '{q}' ({type(exc).__name__}).", stage="research", index=i))
        finally:
            await queue.put(DONE)

    tasks = [asyncio.create_task(worker(i, q)) for i, q in enumerate(questions)]
    pending = len(tasks)
    try:
        while pending:
            item = await queue.get()
            if item is DONE:
                pending -= 1
            elif item["type"] == "error":
                yield item
                return
            else:
                yield item
    finally:
        for t in tasks:
            t.cancel()

    good = [f for f in findings if f and f["text"] != NO_INFO]
    if not good:
        yield ev("error", "No usable sources were found. Check your internet connection, or set SEARCH_PROVIDER=mock "
                          "for the offline demo.")
        return

    # 4. Final report
    yield ev("stage_start", "Writing the final report", stage="report")
    try:
        body = await reasoner.report(req.query, good, registry.items)
    except LLMError as exc:
        yield ev("research_step", f"The model could not write the report ({exc}); using the extractive report instead.",
                 stage="report")
        body = await ExtractiveReasoner().report(req.query, good, registry.items)
    markdown, used = finish_report(body, registry)
    yield ev("research_complete", markdown, stage="report", sources=used, findings=good)
