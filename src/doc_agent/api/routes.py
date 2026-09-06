from __future__ import annotations

from fastapi import APIRouter, HTTPException

from doc_agent import __version__
from doc_agent.agent.graph import run_agent
from doc_agent.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    SessionHistoryResponse,
    TaskResponse,
)
from doc_agent.config import get_settings
from doc_agent.ingest.pipeline import ingest_paths
from doc_agent.memory import get_session_memory, get_task_store
from doc_agent.rag.store import get_store

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    s = get_settings()
    store = get_store()
    return HealthResponse(
        status="ok",
        llm="configured" if s.llm_configured else "missing",
        retrieval_backend=store.retrieval_backend,
        chunks=store.chunk_count,
        version=__version__,
        memory_db=s.memory_db,
    )


@router.post("/v1/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest) -> IngestResponse:
    try:
        result = ingest_paths(req.paths or ["data/raw"], reindex=req.reindex)
        return IngestResponse(**result)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    s = get_settings()
    if not s.llm_configured:
        raise HTTPException(status_code=503, detail="LLM_API_KEY missing")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message is empty")
    try:
        result = run_agent(req.message.strip(), session_id=req.session_id)
        return ChatResponse(**result)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/v1/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    record = get_task_store().get_task(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="task not found")
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
