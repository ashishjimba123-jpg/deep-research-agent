"""Clients for LOCAL language-model servers. No hosted vendor API is used by default."""
from typing import Optional

import httpx

from .config import Settings


class LLMError(RuntimeError):
    """Raised with a message that is safe to show to the user."""


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 300.0):
        self.base_url, self.model, self.timeout = base_url, model, timeout

    async def chat(self, system: str, user: str, temperature: float = 0.2, max_tokens: int = 900) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"Cannot reach Ollama at {self.base_url}. Is it running? ({type(exc).__name__})") from exc
        if r.status_code == 404:
            raise LLMError(f"Ollama does not have the model '{self.model}'. Run: ollama pull {self.model}")
        if r.status_code != 200:
            raise LLMError(f"Ollama returned HTTP {r.status_code}.")
        return (r.json().get("message", {}).get("content") or "").strip()

    @staticmethod
    async def list_models(base_url: str) -> list:
        try:
            async with httpx.AsyncClient(timeout=2.5) as c:
                r = await c.get(f"{base_url}/api/tags")
            return [m["name"] for m in r.json().get("models", [])] if r.status_code == 200 else []
        except Exception:
            return []


class OpenAICompatClient:
    """Talks to any server exposing /chat/completions (LM Studio, llama.cpp, vLLM). A key is optional."""

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 300.0):
        self.base_url, self.model, self.api_key, self.timeout = base_url, model, api_key, timeout

    async def chat(self, system: str, user: str, temperature: float = 0.2, max_tokens: int = 900) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"Cannot reach the local model server at {self.base_url} ({type(exc).__name__}).") from exc
        if r.status_code != 200:
            raise LLMError(f"Model server returned HTTP {r.status_code}.")
        try:
            return (r.json()["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError("Unexpected response from the model server.") from exc


def make_llm(mode: str, model: Optional[str], settings: Settings):
    if mode == "ollama":
        return OllamaClient(settings.ollama_url, model or settings.ollama_model, settings.llm_timeout)
    if mode == "openai-compatible":
        return OpenAICompatClient(settings.llm_base_url, model or settings.llm_model, settings.llm_api_key, settings.llm_timeout)
    raise ValueError(f"mode {mode!r} does not use a language model")
