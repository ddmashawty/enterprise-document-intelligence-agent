from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from doc_agent import __version__
from doc_agent.api.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from doc_agent.api.routes import router
from doc_agent.api.routes_kaoyan import router as kaoyan_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="广东四校计算机考研信息 Agent（Document Intelligence Agent）",
        version=__version__,
        description=(
            "考研信息查询：中大 / 华工 / 暨大 / 华师 计算机类专业的招生计划、复试线、初试科目，"
            "每条事实带年份、口径和官方来源；/v1/chat 为 Agent 问答（hybrid RAG + 结构化工具 + 数字校验），"
            "/v1/programs、/v1/score-lines、/v1/documents 为结构化查询。企业文档问答能力保留。"
        ),
    )
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(router)
    app.include_router(kaoyan_router)
    return app


app = create_app()
