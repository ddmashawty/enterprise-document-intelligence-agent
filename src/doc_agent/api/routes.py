from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from doc_agent import __version__
from doc_agent.agent.graph import run_agent
from doc_agent.api.errors import http_error
from doc_agent.api.jobs import enqueue_chat_job, run_chat_job
from doc_agent.api.schemas import (
    AsyncChatResponse,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    SessionHistoryResponse,
    TaskListResponse,
    TaskResponse,
)
from doc_agent.config import get_settings
from doc_agent.ingest.pipeline import ingest_paths
from doc_agent.kaoyan.db import get_kaoyan_store
from doc_agent.memory import get_session_memory, get_task_store
from doc_agent.rag.store import get_store
from doc_agent.runtime_options import request_options

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    s = get_settings()
    store = get_store()
    kaoyan: dict[str, object] = {}
    if s.kaoyan_db_path.exists():
        ky = get_kaoyan_store()
        kaoyan = {"kaoyan_db": s.kaoyan_db, "programs": ky.count("programs"), "documents": ky.count("documents")}
    return HealthResponse(
        status="ok",
        llm="configured" if s.llm_configured else "missing",
        retrieval_backend=store.retrieval_backend,
        chunks=store.chunk_count,
        version=__version__,
        memory_db=s.memory_db,
        **kaoyan,
    )


@router.post("/v1/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest) -> IngestResponse:
    try:
        result = ingest_paths(req.paths or ["data/raw"], reindex=req.reindex)
        return IngestResponse(**result)
    except Exception as exc:  # noqa: BLE001
        raise http_error(500, "ingest_failed", str(exc)) from exc


def _chat_options(req: ChatRequest) -> tuple[int | None, float | None]:
    if not req.options:
        return None, None
    return req.options.max_tool_calls, req.options.temperature


@router.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    s = get_settings()
    if not s.llm_configured:
        raise http_error(503, "llm_not_configured", "LLM_API_KEY missing")
    if not req.message.strip():
        raise http_error(400, "empty_message", "message is empty")
    max_tools, temperature = _chat_options(req)
    try:
        with request_options(max_tool_calls=max_tools, temperature=temperature):
            result = run_agent(req.message.strip(), session_id=req.session_id)
        return ChatResponse(**result)
    except Exception as exc:  # noqa: BLE001
        raise http_error(500, "chat_failed", str(exc)) from exc


@router.post("/v1/chat/async", response_model=AsyncChatResponse)
def chat_async(req: ChatRequest, background_tasks: BackgroundTasks) -> AsyncChatResponse:
    s = get_settings()
    if not s.llm_configured:
        raise http_error(503, "llm_not_configured", "LLM_API_KEY missing")
    if not req.message.strip():
        raise http_error(400, "empty_message", "message is empty")
    max_tools, temperature = _chat_options(req)
    task_id, session_id = enqueue_chat_job(
        message=req.message.strip(),
        session_id=req.session_id,
        max_tool_calls=max_tools,
        temperature=temperature,
    )
    background_tasks.add_task(
        run_chat_job,
        task_id=task_id,
        session_id=session_id,
        message=req.message.strip(),
        max_tool_calls=max_tools,
        temperature=temperature,
    )
    return AsyncChatResponse(
        session_id=session_id,
        task_id=task_id,
        status="queued",
        poll_url=f"/v1/tasks/{task_id}",
    )


@router.get("/v1/tasks", response_model=TaskListResponse)
def list_tasks(session_id: str | None = None, limit: int = 20) -> TaskListResponse:
    limit = max(1, min(limit, 100))
    tasks = [
        TaskResponse(**t.to_dict())
        for t in get_task_store().list_tasks(session_id=session_id, limit=limit)
    ]
    return TaskListResponse(tasks=tasks, count=len(tasks))


@router.get("/v1/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    record = get_task_store().get_task(task_id)
    if not record:
        raise http_error(404, "task_not_found", f"task not found: {task_id}")
    return TaskResponse(**record.to_dict())


@router.get("/v1/sessions/{session_id}", response_model=SessionHistoryResponse)
def get_session(session_id: str) -> SessionHistoryResponse:
    store = get_task_store()
    mem = get_session_memory()
    turns = mem.history(session_id, limit=20)
    if not turns:
        turns = store.session_history(session_id, limit=20)
    tasks = [TaskResponse(**t.to_dict()) for t in store.list_tasks(session_id=session_id, limit=10)]
    return SessionHistoryResponse(session_id=session_id, turns=turns, tasks=tasks)
