"""The 'thinking' parts of the workflow: clarify, plan, summarise, write the report.

ExtractiveReasoner needs no model at all (it ranks and quotes sentences from the sources).
LLMReasoner uses a local model for the same four tasks and falls back to extractive behaviour on bad output.
"""
import json
import re
from dataclasses import dataclass

from .llm import LLMError
from .textutils import extractive_sentences


@dataclass
class Passage:
    text: str
    source_id: int


def topic_of(query: str) -> str:
    q = query.strip().rstrip("?.! ")
    q = re.sub(
        r"^(please\s+)?(research|explain|tell me about|what (is|are|was|were)|who (is|are)|how (does|do|did|to)|"
        r"give me (an )?overview of|summari[sz]e|compare)\s+",
        "", q, flags=re.I,
    )
    q = re.sub(r"^(the|a|an)\s+", "", q, flags=re.I)
    return q or query.strip()


_TEMPLATES = [
    "What is {t}?",
    "How does {t} work?",
    "What are the main benefits and advantages of {t}?",
    "What are the limitations, risks or criticisms of {t}?",
    "What are real-world examples or applications of {t}?",
    "What are the latest developments in {t}?",
    "How does {t} compare with alternatives?",
]


def sanitize_citations(text: str, valid_ids) -> str:
    """Remove citation numbers that do not match a real source, so the model cannot invent references."""
    valid = set(valid_ids)

    def fix(m):
        ids = [int(x) for x in re.findall(r"\d+", m.group(1))]
        keep = [i for i in ids if i in valid]
        return "[" + ", ".join(str(i) for i in keep) + "]" if keep else ""

    return re.sub(r"\[(\d+(?:\s*,\s*\d+)*)\]", fix, text)


def parse_questions(text: str, n: int) -> list:
    items = []
    m = re.search(r"\{.*\}|\[.*\]", text, re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                data = data.get("questions", [])
            items = [str(x) for x in data] if isinstance(data, list) else []
        except ValueError:
            items = []
    if not items:
        for line in text.splitlines():
            line = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", line).strip().strip('"')
            if len(line) > 10:
                items.append(line)
    seen, out = set(), []
    for it in items:
        key = it.lower()
        if key not in seen:
            seen.add(key)
            out.append(it.strip())
    return out[:n]


def _fmt_sentences(pairs) -> str:
    """Join (sentence, source_id) pairs, merging runs from the same source under one citation."""
    out, run, sid = [], [], None
    for s, i in pairs:
        if i != sid and run:
            out.append(" ".join(run) + f" [{sid}]")
            run = []
        run.append(s)
        sid = i
    if run:
        out.append(" ".join(run) + f" [{sid}]")
    return " ".join(out)


NO_INFO = "No relevant passages were found for this question."


class ExtractiveReasoner:
    name = "extractive"

    def __init__(self):
        self._used = set()  # sentences already used, so findings do not repeat each other

    async def clarify(self, query: str) -> list:
        return []  # asking good clarifying questions needs a language model

    async def plan(self, query: str, context, n: int) -> list:
        t = topic_of(query)
        qs = [tpl.format(t=t) for tpl in _TEMPLATES]
        if re.match(r"(?i)^(what|how|why|who|when|which|is|are|can|does|do|should)\b", query.strip()):
            first = query.strip().rstrip("?. ") + "?"  # keep the user's own wording as the first question
            qs = [first] + [q for q in qs[1:] if not (first.lower().startswith("how") and q.startswith("How does"))]
        qs = qs[:n]
        if context and n > 1:
            qs[-1] = f"{t}: {context.strip().splitlines()[0][:150]}"
        return qs

    async def summarize(self, question: str, passages: list) -> str:
        pairs = extractive_sentences(question, [(p.text, p.source_id) for p in passages], max_sentences=4,
                                     exclude=self._used)
        self._used.update(s for s, _ in pairs)
        return _fmt_sentences(pairs) if pairs else NO_INFO

    async def report(self, query: str, findings: list, sources: list) -> str:
        good = [f for f in findings if f["text"] and f["text"] != NO_INFO]
        lines = [f"# Research report: {query}", "", "## Key points"]
        seen_points = set()
        for f in good:
            m = re.match(r"(.+?[.!?])\s+(?=[A-Z0-9\[])|(.+)", f["text"], re.S)
            first = (m.group(1) or m.group(2)).strip() if m else f["text"]
            cites = re.findall(r"\[\d+\]", f["text"])
            if not re.search(r"\[\d+\]$", first) and cites:
                first += " " + cites[0]
            if first in seen_points:
                continue
            seen_points.add(first)
            lines.append(f"- {first}")
        lines += ["", "## Findings"]
        for f in findings:
            lines += [f"### {f['question']}", f["text"], ""]
        lines += [
            "## Limitations",
            "This report was assembled without a language model: sentences were ranked and quoted from the cited pages "
            "and may lack surrounding context. Open the sources to verify important claims.",
        ]
        return "\n".join(lines)


CLARIFY_SYS = (
    "You scope research requests. If the request is ambiguous, return JSON {\"questions\": [...]} with at most 3 short "
    "clarifying questions. If it is clear, return {\"questions\": []}. Output JSON only."
)
PLAN_SYS = (
    "You plan web research. Break the request into {n} focused, non-overlapping sub-questions that can each be answered "
    "by a web search. Output JSON only: {{\"questions\": [\"...\", \"...\"]}}"
)
SUMMARY_SYS = (
    "Answer the question using ONLY the numbered passages. Cite sources as [n] using the numbers shown in brackets. "
    "If the passages do not answer the question, say so. Write 100-200 words, no preamble, no bullet lists."
)
REPORT_SYS = (
    "Write a structured research report in Markdown from the findings. Start with a '# ' title, then '## Key takeaways' "
    "(3-5 bullets), then one '## ' section per theme, then '## Limitations'. Cite sources as [n] using only the numbers "
    "already present in the findings. Do not add a sources section. Do not invent facts or numbers."
)


class LLMReasoner:
    def __init__(self, llm):
        self.llm = llm
        self.name = f"llm:{getattr(llm, 'model', '?')}"
        self._fallback = ExtractiveReasoner()

    async def clarify(self, query: str) -> list:
        text = await self.llm.chat(CLARIFY_SYS, f"Request: {query}", max_tokens=300)
        return parse_questions(text, 3)

    async def plan(self, query: str, context, n: int) -> list:
        text = await self.llm.chat(
            PLAN_SYS.format(n=n), f"Request: {query}\nExtra context: {context or 'none'}", temperature=0.3, max_tokens=500
        )
        qs = parse_questions(text, n)
        return qs if len(qs) >= 2 else await self._fallback.plan(query, context, n)

    async def summarize(self, question: str, passages: list) -> str:
        if not passages:
            return NO_INFO
        budget, parts = 6000, []
        for p in passages:
            chunk = f"[{p.source_id}] {p.text[:900]}"
            if budget - len(chunk) < 0:
                break
            budget -= len(chunk)
            parts.append(chunk)
        try:
            text = await self.llm.chat(SUMMARY_SYS, f"Question: {question}\n\nPassages:\n\n" + "\n\n".join(parts), max_tokens=500)
        except LLMError:
            raise
        return text or await self._fallback.summarize(question, passages)

    async def report(self, query: str, findings: list, sources: list) -> str:
        body = "\n\n".join(f"### {f['question']}\n{f['text']}" for f in findings)[:9000]
        text = await self.llm.chat(REPORT_SYS, f"Research request: {query}\n\nFindings:\n\n{body}", temperature=0.3, max_tokens=1800)
        return text or await self._fallback.report(query, findings, sources)
