from __future__ import annotations

from fastapi import FastAPI

from doc_agent.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Enterprise Document Intelligence Agent",
        version="0.2.0",
        description="Phase-2 backend: hybrid RAG + memory + reflect + export/compare",
    )
    app.include_router(router)
    return app


app = create_app()
