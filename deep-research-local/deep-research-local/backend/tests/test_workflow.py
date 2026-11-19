import asyncio
import re

from app.config import Settings
from app.models import ResearchRequest
from app.reasoner import ExtractiveReasoner, parse_questions, sanitize_citations, topic_of
from app.search import MockSearch
from app.workflow import finish_report, run_research, SourceRegistry


def collect(req):
    async def go():
        return [e async for e in run_research(req, Settings(), MockSearch(), ExtractiveReasoner())]
    return asyncio.run(go())


def test_full_pipeline_event_order_and_citations():
    events = collect(ResearchRequest(query="What is a deep research agent?", depth="quick"))
    types = [e["type"] for e in events]
    assert types[0] == "session_start" and types[-1] == "research_complete"
    stages = [e["stage"] for e in events if e["type"] == "stage_start"]
    assert stages == ["clarification", "brief", "research", "report"]
    assert "research_finding" in types
    final = events[-1]
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", final["content"].split("## Sources")[0])}
    source_ids = {s["id"] for s in final["sources"]}
    assert cited and cited <= source_ids            # every citation maps to a real source
    assert "## Sources" in final["content"]


def test_no_results_gives_error():
    events = collect(ResearchRequest(query="zzzzqqqq xxxxyyyy", depth="quick"))
    assert events[-1]["type"] == "error"


def test_sanitize_citations_removes_invented_numbers():
    assert sanitize_citations("A [1] and B [9] and C [1, 7]", {1, 2}) == "A [1] and B  and C [1]"


def test_finish_report_strips_model_sources_and_appends_real():
    reg = SourceRegistry()
    reg.add("Doc A", "https://a.example/x")
    md, used = finish_report("# T\nClaim [1].\n\n## Sources\n1. Made up", reg)
    assert "Made up" not in md and "Doc A" in md and used[0]["id"] == 1


def test_parse_questions_json_and_lines():
    assert parse_questions('{"questions": ["What is X?", "How does X work?"]}', 5) == ["What is X?", "How does X work?"]
    assert parse_questions("1. What is X and why?\n2) How does X work in practice?", 5)[0].startswith("What is X")


def test_topic_of_strips_question_words():
    assert topic_of("What is retrieval-augmented generation?") == "retrieval-augmented generation"


def test_extractive_plan_respects_n():
    qs = asyncio.run(ExtractiveReasoner().plan("What is FastAPI?", None, 3))
    assert len(qs) == 3 and "FastAPI" in qs[0]


def test_findings_do_not_repeat_the_same_sentence():
    events = collect(ResearchRequest(query="What is retrieval-augmented generation?", depth="standard"))
    texts = [e["content"] for e in events if e["type"] == "research_finding" and "No relevant" not in e["content"]]
    sentences = [s.strip() for t in texts for s in re.split(r"(?<=\])\s+", t) if s.strip()]
    assert len(sentences) == len(set(sentences))
