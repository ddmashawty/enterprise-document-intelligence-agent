from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from doc_agent.api.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from doc_agent.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Enterprise Document Intelligence Agent",
        version="0.3.0",
        description=(
            "Phase-3 backend: hybrid RAG + memory + reflect/export + async tasks"
        ),
    )
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(router)
    return app


app = create_app()
