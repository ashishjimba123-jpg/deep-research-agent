"""Deep Research (local): FastAPI backend. No Kimi / Claude / ChatGPT API is used."""
import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .llm import LLMError, OllamaClient
from .models import ClarifyRequest, ResearchRequest
from .search import get_search
from .workflow import build_reasoner, run_research

VERSION = "1.0.0"
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

app = FastAPI(title="Deep Research (local)", version=VERSION)
_settings = get_settings()
app.add_middleware(CORSMiddleware, allow_origins=list(_settings.cors_origins), allow_methods=["*"], allow_headers=["*"])
app.state.active = 0


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok", "version": VERSION}


@app.get("/models")
async def models():
    s = get_settings()
    ollama = await OllamaClient.list_models(s.ollama_url)
    return {
        "search": s.search_provider,
        "modes": [
            {"id": "extractive", "label": "No model (extractive, works offline)", "available": True, "models": []},
            {"id": "ollama", "label": "Local model via Ollama", "available": bool(ollama), "models": ollama,
             "default": s.ollama_model},
            {"id": "openai-compatible", "label": "Local OpenAI-compatible server (LM Studio, llama.cpp)",
             "available": True, "models": [], "default": s.llm_model},
        ],
    }


@app.post("/research/clarify")
async def clarify(req: ClarifyRequest):
    s = get_settings()
    reasoner = build_reasoner(req.mode, req.model, s)
    try:
        questions = await reasoner.clarify(req.query)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"questions": questions}


async def _sse(gen):
    """Format events as SSE and send a keep-alive comment while a long step is running."""
    it = gen.__aiter__()
    nxt = asyncio.ensure_future(it.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({nxt}, timeout=15)
            if not done:
                yield ": keep-alive\n\n"
                continue
            try:
                event = nxt.result()
            except StopAsyncIteration:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            nxt = asyncio.ensure_future(it.__anext__())
    finally:
        nxt.cancel()
        await asyncio.gather(nxt, return_exceptions=True)  # let the generator unwind before closing it
        await it.aclose()


@app.post("/research/stream")
async def research_stream(req: ResearchRequest):
    s = get_settings()
    if app.state.active >= s.max_sessions:
        raise HTTPException(status_code=429, detail="Too many research sessions are running. Try again in a minute.")
    reasoner = build_reasoner(req.mode, req.model, s)
    search = get_search(s)

    async def guarded():
        app.state.active += 1
        try:
            async for event in run_research(req, s, search, reasoner):
                yield event
        finally:
            app.state.active -= 1

    return StreamingResponse(
        _sse(guarded()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _frontend_dir() -> Path:
    if _settings.frontend_dir:
        return Path(_settings.frontend_dir)
    return Path(__file__).resolve().parents[2] / "frontend"


_fe = _frontend_dir()
if _fe.is_dir():  # serve the UI from the same origin, so no CORS or build step is needed
    app.mount("/", StaticFiles(directory=str(_fe), html=True), name="frontend")
