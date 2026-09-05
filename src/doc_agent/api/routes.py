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
)
from doc_agent.config import get_settings
from doc_agent.ingest.pipeline import ingest_paths
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
