from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    paths: list[str] = Field(default_factory=lambda: ["data/raw"])
    reindex: bool = False


class IngestResponse(BaseModel):
    docs_indexed: int
    docs_failed: list[dict[str, str]] = Field(default_factory=list)
    chunks_added: int
    chunks_total: int
    collection: str
    retrieval_backend: str
    files: list[str] = Field(default_factory=list)


class ChatOptions(BaseModel):
    max_tool_calls: int | None = None
    temperature: float | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    options: ChatOptions | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    plan: list[str] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    status: str = ""
    iterations: int = 0


class HealthResponse(BaseModel):
    status: str
    llm: str
    retrieval_backend: str
    chunks: int
    version: str
