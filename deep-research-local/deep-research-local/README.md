# Deep Research (local)

A working deep-research agent with a **FastAPI backend** and a **web frontend**. It does the same job as the
agent in the tutorial video (plan, search, read, write a cited report, stream progress live), but it needs
**no Kimi, Claude or ChatGPT API and no API keys at all**.

- **Search:** DuckDuckGo (via the `ddgs` package) with Wikipedia as a fallback. Both are free and keyless.
- **Thinking:** one of three engines you choose in the UI:
  1. **No model (extractive)** works immediately, offline from any AI service. It ranks and quotes sentences from
     the pages it reads (BM25 ranking) and cites every sentence.
  2. **Local model via Ollama** (for example `llama3.2` or `qwen2.5`) writes the plan, the findings and the report.
  3. **Local OpenAI-compatible server** such as LM Studio or a llama.cpp server on your own machine.

## Quick start

Requirements: Python 3.10+ (3.12 recommended) and an internet connection for web search.

```bash
./run.sh              # Linux / macOS   (Windows: double-click run.bat)
```

Open **http://localhost:8080**, type a question, press **Start research**. That is all: the default engine
needs no model.

### Better reports with a local model (optional, still free)

```bash
# install Ollama from https://ollama.com, then:
ollama pull llama3.2
./run.sh
```

The page detects Ollama automatically and selects it. Bigger models write better reports; small ones are faster.

### Docker

```bash
docker compose up --build                  # app only
docker compose --profile llm up --build    # app + Ollama
docker compose exec ollama ollama pull llama3.2
```

### Offline demo (no internet)

```bash
SEARCH_PROVIDER=mock ./run.sh
```

This searches a small built-in demo corpus (a few topics such as FastAPI, server-sent events and RAG), so you can
see the whole flow without a network. Real research needs real search.

## How it works

```
Browser (frontend/)  --POST /research/stream-->  FastAPI (backend/app/main.py)
        ^                                              |
        |  server-sent events                          v
        +------ session_start, stage_start,     workflow.py
                research_step, research_finding,   1 clarification  (optional questions, answers become context)
                research_complete, error           2 research brief (sub-questions)
                                                   3 research       (search -> fetch -> rank passages -> summarise,
                                                                     sub-questions run concurrently)
                                                   4 final report   (citations validated, real source list appended)
```

| Video / tutorial concept | Here |
|---|---|
| Four stages: clarify, brief, research, report | `workflow.py`, same event names |
| LangGraph state graph | a small explicit async pipeline (fewer dependencies) |
| GPT-4o / Claude / Kimi K2 | `reasoner.py` + `llm.py`: extractive, Ollama, or a local OpenAI-compatible server |
| Web search tool | `search.py`: DuckDuckGo, Wikipedia, mock |
| SSE streaming with keep-alive | `main.py` (`_sse`) |
| Health check for Cloud Run (GET and HEAD) | `/health` |
| Dockerfile for deployment | `Dockerfile`, `docker-compose.yml` |

Design choices worth knowing:

- **Citations cannot be invented.** After the model writes, `[n]` markers that do not match a real source are
  removed, and any "Sources" list written by the model is replaced by the real one built from pages that were read.
- **A failing sub-question does not stop the run.** If a local model server is unreachable the run stops with a
  clear message (for example "Cannot reach Ollama at ... Is it running?").
- **Clarifying questions** need a model: tick the box in the UI, answer the questions, and the answers are sent as
  `context`. The extractive engine skips this step.

## Configuration (environment variables, all optional)

| Variable | Default | Meaning |
|---|---|---|
| `SEARCH_PROVIDER` | `auto` | `auto` (DuckDuckGo then Wikipedia), `ddg`, `wikipedia`, `mock` |
| `OLLAMA_URL` / `OLLAMA_MODEL` | `http://localhost:11434` / `llama3.2` | Local Ollama server and default model |
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` | `http://localhost:1234/v1` / `local-model` / empty | Local OpenAI-compatible server |
| `LLM_TIMEOUT` | `300` | Seconds to wait for a model reply |
| `MAX_SESSIONS` | `3` | Concurrent research runs before the API answers HTTP 429 |
| `CORS_ORIGINS` | `*` | Comma-separated origins allowed to call the API |
| `FRONTEND_DIR` | `../frontend` | Folder served at `/` |
| `PORT` | `8080` | Used by `run.sh` |

## API

| Method and path | Purpose |
|---|---|
| `GET` or `HEAD /health` | Liveness check |
| `GET /models` | Available engines and detected Ollama models |
| `POST /research/clarify` | `{query, mode, model}` returns `{questions: [...]}` |
| `POST /research/stream` | `{query, mode, model?, depth?, context?}` returns an event stream |

Example:

```bash
curl -N -X POST http://localhost:8080/research/stream \
  -H 'Content-Type: application/json' \
  -d '{"query": "What is retrieval-augmented generation?", "depth": "quick"}'
```

Each event is `data: {json}` with a `type`: `session_start`, `stage_start`, `research_step`, `research_finding`,
`research_complete` (the Markdown report, sources and findings) or `error`. Interactive docs are at `/docs`.

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest -q
```

37 tests cover text ranking, the SSRF guard, the whole workflow, the HTTP and SSE API, citation sanitising and the
Ollama path (against a fake local Ollama server).

## What was and was not verified

Verified in the build environment: all 37 tests, the running server (health, streaming, frontend files) and the
JavaScript syntax check. **Not verified there:** live DuckDuckGo and Wikipedia searches, a real Ollama model, and
the page in a real browser, because that environment has no general internet access and no GPU. These parts are
standard library calls (`ddgs`, Wikipedia's public API, Ollama's `/api/chat`), but please run one real query after
installing and report anything that behaves differently. If DuckDuckGo blocks or rate-limits you, the Wikipedia
fallback is used automatically.

## Limits you should know about

- **Extractive mode quotes, it does not understand.** Reports are made of ranked sentences from the sources. They
  are cited and usually on topic but can lack context and read choppily. Use a local model for fluent reports.
- **Small local models are less reliable** at following instructions. The code asks for short outputs, validates
  citations and falls back to extractive behaviour where it can, but quality depends on the model you pull.
- **Web pages are untrusted input.** The agent only summarises text; it never executes anything it reads, but a page
  could still contain misleading statements or instructions aimed at the model. Verify important claims.
- **Network safety:** pages are fetched only from public addresses (private, loopback and link-local addresses are
  refused, redirects are re-checked). DNS rebinding is not fully prevented; run behind a firewall for public use.
- **No authentication.** Anyone who can reach the server can run research. Put it behind a reverse proxy with a
  login before exposing it to the internet.
- **Respect websites.** The fetcher identifies itself, reads one page per result and keeps only short passages, but
  you are responsible for following the terms of the sites you research and for copyright when you reuse text.

## Project layout

```
backend/app/   main.py (API, SSE)  workflow.py (4 stages)  reasoner.py (extractive + LLM)  llm.py (Ollama, local OpenAI-compatible)
               search.py (DuckDuckGo, Wikipedia, mock)  fetch.py (safe fetching)  textutils.py (BM25, chunking)  config.py  models.py
backend/tests/ 37 tests
frontend/      index.html  app.js  styles.css  (no build step)
Dockerfile  docker-compose.yml  run.sh  run.bat  .env.example
```

## Troubleshooting

- **"Cannot reach the backend"** in the page: start the server (`./run.sh`) or set the address under "Backend address".
- **"No usable sources were found":** no internet, or search was blocked. Try `SEARCH_PROVIDER=wikipedia`, or
  `SEARCH_PROVIDER=mock` to confirm the app itself works.
- **"Cannot reach Ollama":** start it (`ollama serve`) and pull a model (`ollama pull llama3.2`).
- **Slow runs:** use Quick depth, a smaller model, or the extractive engine.
