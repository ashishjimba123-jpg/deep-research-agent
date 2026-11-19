import json
import os

os.environ["SEARCH_PROVIDER"] = "mock"
os.environ["FRONTEND_DIR"] = "/nonexistent"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def parse_sse(text):
    return [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: ")]


def test_health_get_and_head():
    assert client.get("/health").json()["status"] == "ok"
    assert client.head("/health").status_code == 200


def test_models_lists_extractive():
    data = client.get("/models").json()
    assert any(m["id"] == "extractive" and m["available"] for m in data["modes"])


def test_validation_rejects_short_query():
    assert client.post("/research/stream", json={"query": "ab"}).status_code == 422


def test_stream_end_to_end():
    with client.stream("POST", "/research/stream", json={"query": "How do server-sent events work?", "depth": "quick"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    events = parse_sse(text)
    assert events[0]["type"] == "session_start" and events[-1]["type"] == "research_complete"
    assert "server-sent" in events[-1]["content"].lower() or "events" in events[-1]["content"].lower()


def test_clarify_extractive_returns_empty_list():
    r = client.post("/research/clarify", json={"query": "Tell me about FastAPI"})
    assert r.status_code == 200 and r.json() == {"questions": []}


def test_ollama_mode_without_server_reports_friendly_error():
    os.environ["OLLAMA_URL"] = "http://127.0.0.1:9"
    with client.stream("POST", "/research/stream", json={"query": "What is FastAPI?", "mode": "ollama", "depth": "quick"}) as r:
        events = parse_sse("".join(r.iter_text()))
    assert events[-1]["type"] == "error" and "Ollama" in events[-1]["content"]
