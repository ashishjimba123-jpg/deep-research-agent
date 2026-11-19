"""Runtime settings, read from environment variables (no API keys required)."""
import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Where web results come from: auto (DuckDuckGo, then Wikipedia) | ddg | wikipedia | mock
    search_provider: str = "auto"
    # Local model servers. Nothing here talks to Kimi, Claude or ChatGPT.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    llm_base_url: str = "http://localhost:1234/v1"  # LM Studio, llama.cpp server, vLLM ...
    llm_model: str = "local-model"
    llm_api_key: str = ""  # local servers normally need none
    llm_timeout: float = 300.0
    cors_origins: tuple = ("*",)
    max_query_chars: int = 500
    fetch_timeout: float = 12.0
    max_page_bytes: int = 1_500_000
    fetch_concurrency: int = 4
    subquestion_concurrency: int = 3
    max_sessions: int = 3
    frontend_dir: str = ""


def get_settings() -> Settings:
    origins = tuple(o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip())
    return Settings(
        search_provider=os.environ.get("SEARCH_PROVIDER", "auto").lower(),
        ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
        llm_base_url=os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1").rstrip("/"),
        llm_model=os.environ.get("LLM_MODEL", "local-model"),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        llm_timeout=float(os.environ.get("LLM_TIMEOUT", "300")),
        cors_origins=origins or ("*",),
        max_sessions=_int("MAX_SESSIONS", 3),
        frontend_dir=os.environ.get("FRONTEND_DIR", ""),
    )
