from typing import Literal, Optional

from pydantic import BaseModel, Field

Mode = Literal["extractive", "ollama", "openai-compatible"]
Depth = Literal["quick", "standard", "deep"]


class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    mode: Mode = "extractive"
    model: Optional[str] = Field(default=None, max_length=100)
    depth: Depth = "standard"
    context: Optional[str] = Field(default=None, max_length=2000)  # answers to clarifying questions


class ClarifyRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    mode: Mode = "extractive"
    model: Optional[str] = Field(default=None, max_length=100)
