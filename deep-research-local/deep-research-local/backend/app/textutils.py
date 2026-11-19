"""Dependency-free text helpers: cleaning, chunking, BM25 ranking, extractive summaries."""
import math
import re
from collections import Counter

STOP = set(
    "a an the and or but if then else of to in on at by for with from as is are was were be been being it its "
    "this that these those i you he she we they them his her our your their not no do does did have has had will "
    "would can could should may might about into over under between within without also more most other some such "
    "than too very just what which who whom whose when where why how".split()
)
_WORD = re.compile(r"[a-z0-9][a-z0-9\-']+")
_SENT = re.compile(r'(?<=[.!?])\s+(?=["“(\[]?[A-Z0-9])')
_BOILER = re.compile(
    r"(cookie|subscribe|sign up|sign in|log in|accept all|privacy policy|terms of (use|service)|"
    r"all rights reserved|©|share this|follow us|newsletter|advertisement)",
    re.I,
)


def tokenize(text: str) -> list:
    return [w for w in _WORD.findall(text.lower()) if w not in STOP]


def split_sentences(text: str) -> list:
    return [s.strip() for s in _SENT.split(text) if s.strip()]


def clean_text(text: str) -> str:
    """Drop menu/boilerplate lines and collapse whitespace."""
    lines = []
    for raw in text.replace("\r", "").split("\n"):
        line = re.sub(r"[ \t\u00a0]+", " ", raw).strip()
        if not line:
            lines.append("")
            continue
        if _BOILER.search(line) and len(line) < 160:
            continue
        if len(line) < 40 and not line.endswith((".", "!", "?", ":")):
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def chunk_passages(text: str, max_chars: int = 900) -> list:
    """Split text into passages of roughly max_chars, preferring paragraph and sentence boundaries."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces = []
    for p in paras:
        if len(p) <= max_chars:
            pieces.append(p)
            continue
        cur = ""
        for s in split_sentences(p):
            if cur and len(cur) + len(s) + 1 > max_chars:
                pieces.append(cur)
                cur = s
            else:
                cur = (cur + " " + s).strip()
        if cur:
            pieces.append(cur)
    merged, buf = [], ""
    for piece in pieces:
        if buf and len(buf) + len(piece) + 2 > max_chars:
            merged.append(buf)
            buf = piece
        else:
            buf = (buf + "\n\n" + piece) if buf else piece
    if buf:
        merged.append(buf)
    return [m for m in merged if len(m) >= 40]


def bm25_rank(query: str, docs: list, k: int = 5, k1: float = 1.5, b: float = 0.75) -> list:
    """Return [(index, score)] for the k best documents (score > 0), best first."""
    q = set(tokenize(query))
    toks = [tokenize(d) for d in docs]
    n = len(docs)
    if not n or not q:
        return []
    avg = (sum(len(t) for t in toks) / n) or 1.0
    df = Counter()
    for t in toks:
        df.update(set(t))
    scored = []
    for i, t in enumerate(toks):
        tf = Counter(t)
        dl = len(t) or 1
        s = 0.0
        for w in q:
            if w in tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * dl / avg))
        if s > 0:
            scored.append((i, s))
    scored.sort(key=lambda x: -x[1])
    return scored[:k]


def jaccard(a: str, b: str) -> float:
    sa, sb = set(tokenize(a)), set(tokenize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def extractive_sentences(question: str, passages: list, max_sentences: int = 4, per_source: int = 2, exclude=None) -> list:
    """passages: [(text, source_id)] -> [(sentence, source_id)] chosen for the question, in reading order."""
    exclude = exclude or set()
    cands = []  # (sentence, source_id, order)
    order = 0
    for text, sid in passages:
        for j, s in enumerate(split_sentences(text)):
            if 40 <= len(s) <= 400 and s not in exclude:
                cands.append((s, sid, order + j))
        order += 1000
    if not cands:
        return []
    ranked = bm25_rank(question, [c[0] for c in cands], k=len(cands))
    chosen, used = [], Counter()
    for idx, _score in ranked:
        s, sid, o = cands[idx]
        if used[sid] >= per_source:
            continue
        if any(jaccard(s, c[0]) > 0.6 for c in chosen):
            continue
        chosen.append((s, sid, o))
        used[sid] += 1
        if len(chosen) >= max_sentences:
            break
    chosen.sort(key=lambda c: c[2])
    return [(s, sid) for s, sid, _ in chosen]
