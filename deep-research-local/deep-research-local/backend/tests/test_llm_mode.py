"""Exercise the model-backed path against a fake local Ollama server (no real model needed)."""
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["SEARCH_PROVIDER"] = "mock"
os.environ["FRONTEND_DIR"] = "/nonexistent"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send({"models": [{"name": "fake:1b"}]})

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        system, user = data["messages"][0]["content"], data["messages"][1]["content"]
        if "scope research" in system:
            out = '{"questions": ["Which aspect interests you most?"]}'
        elif "plan web research" in system:
            out = '{"questions": ["What is a deep research agent?", "What are the limitations of research agents?"]}'
        elif "ONLY the numbered passages" in system:
            n = re.search(r"\[(\d+)\]", user).group(1)
            out = f"A deep research agent plans, searches and writes a report [{n}]. It also cites an invented source [99]."
        elif "structured research report" in system:
            out = "# Report\n\n## Key takeaways\n- Agents plan and search [1] and one fake cite [42].\n\n## Sources\n1. Totally made up"
        else:
            out = "ok"
        self._send({"message": {"role": "assistant", "content": out}})


def parse_sse(text):
    return [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: ")]


def test_ollama_mode_with_fake_server():
    srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["OLLAMA_URL"] = f"http://127.0.0.1:{srv.server_port}"
    client = TestClient(app)
    try:
        models = client.get("/models").json()
        ollama = next(m for m in models["modes"] if m["id"] == "ollama")
        assert ollama["available"] and "fake:1b" in ollama["models"]

        assert client.post("/research/clarify", json={"query": "Tell me about agents", "mode": "ollama"}).json()["questions"] == [
            "Which aspect interests you most?"]

        with client.stream("POST", "/research/stream", json={"query": "What is a deep research agent?", "mode": "ollama",
                                                              "model": "fake:1b", "depth": "quick"}) as r:
            events = parse_sse("".join(r.iter_text()))
        assert events[-1]["type"] == "research_complete", events[-1]
        plan = next(e for e in events if e.get("questions"))
        assert len(plan["questions"]) == 2                         # model's plan was used
        md = events[-1]["content"]
        assert "[99]" not in md and "[42]" not in md               # invented citations removed
        assert "Totally made up" not in md                         # model-written source list replaced
        assert "mock://" in md                                     # real sources appended
    finally:
        srv.shutdown()
