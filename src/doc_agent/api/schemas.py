from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    paths: list[str] = Field(default_factory=lambda: ["data/raw"])
    reindex: bool = False


class IngestResponse(BaseModel):
    docs_indexed: int
    docs_failed: list[dict[str, str]] = Field(default_factory=list)
    docs_needs_ocr: list[str] = Field(default_factory=list)
    docs_redacted: int = 0
    chunks_added: int
    chunks_total: int
    collection: str
    retrieval_backend: str
    files: list[str] = Field(default_factory=list)


class ChatOptions(BaseModel):
    max_tool_calls: int | None = Field(default=None, ge=1, le=10)
    temperature: float | None = Field(default=None, ge=0, le=2)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    options: ChatOptions | None = None


class ChatResponse(BaseModel):
    session_id: str
    task_id: str = ""
    answer: str
    plan: list[str] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    exports: list[dict[str, Any]] = Field(default_factory=list)
    reflection: str = ""
    status: str = ""
    iterations: int = 0


class AsyncChatResponse(BaseModel):
    session_id: str
    task_id: str
    status: str = "queued"
    poll_url: str = ""


class HealthResponse(BaseModel):
    status: str
    llm: str
    retrieval_backend: str
    chunks: int
    version: str
    memory_db: str = ""
    kaoyan_db: str | None = None
    programs: int | None = None
    documents: int | None = None


class TaskResponse(BaseModel):
    task_id: str
    session_id: str
    user_goal: str
    plan: list[str] = Field(default_factory=list)
    answer: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    reflection: str = ""
    exports: list[dict[str, Any]] = Field(default_factory=list)
    status: str = ""
    iterations: int = 0
    created_at: str = ""


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse] = Field(default_factory=list)
    count: int = 0


class SessionHistoryResponse(BaseModel):
    session_id: str
    turns: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[TaskResponse] = Field(default_factory=list)
