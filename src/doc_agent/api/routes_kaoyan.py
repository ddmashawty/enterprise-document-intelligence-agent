from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from doc_agent.api.errors import http_error
from doc_agent.api.schemas_kaoyan import (
    DocumentDetailResponse,
    DocumentListResponse,
    ProgramDetailResponse,
    ProgramSearchResponse,
    ScoreLinesResponse,
)
from doc_agent.config import get_settings
from doc_agent.kaoyan.db import get_kaoyan_store
from doc_agent.kaoyan.query import KaoyanQuery

router = APIRouter(prefix="/v1", tags=["kaoyan"])

_YEAR = Query(None, ge=2000, le=2100, description="intake year, e.g. 2026")


def kaoyan_query() -> KaoyanQuery:
    if not get_settings().kaoyan_db_path.exists():
        raise http_error(503, "kaoyan_db_missing", "data/kaoyan.db 不存在，请先运行 scripts/seed_kaoyan.py")
    return KaoyanQuery(get_kaoyan_store())


KaoyanQueryDep = Annotated[KaoyanQuery, Depends(kaoyan_query)]


def _school_or_404(q: KaoyanQuery, school: str | None) -> None:
    if school and not q.school_id(school):
        raise http_error(404, "school_not_found", f"未知学校: {school}", {"supported": sorted(q.schools)})


@router.get("/programs", response_model=ProgramSearchResponse)
def list_programs(
    q: KaoyanQueryDep,
    school: str | None = Query(None, description="sysu/scut/jnu/scnu 或 中大/华工/暨大/华师"),
    college: str | None = Query(None, description="学院名或代码"),
    code: str | None = Query(None, description="专业代码（6 位）或 4 位前缀"),
    name_kw: str | None = None,
    degree_type: str | None = Query(None, description="学硕 / 专硕"),
    study_mode: str | None = Query(None, description="全日制 / 非全日制"),
    exam_subject: str | None = None,
    is_408: bool | None = None,
    min_public_plan: int | None = Query(None, ge=0, description="统招 ≥ N"),
    year: int | None = _YEAR,
) -> ProgramSearchResponse:
    _school_or_404(q, school)
    result = q.search_programs(
        school=school, college=college, code=code, name_kw=name_kw, degree_type=degree_type,
        study_mode=study_mode, exam_subject=exam_subject, is_408=is_408,
        min_public_plan=min_public_plan, year=year, detail=True,
    )
    return ProgramSearchResponse(**result)


@router.get("/programs/{program_id}", response_model=ProgramDetailResponse)
def get_program(program_id: str, q: KaoyanQueryDep) -> ProgramDetailResponse:
    facts = q.program(program_id)
    if facts is None:
        raise http_error(404, "program_not_found", f"专业不存在: {program_id}")
    return ProgramDetailResponse(**facts)


@router.get("/score-lines", response_model=ScoreLinesResponse)
def score_lines(
    q: KaoyanQueryDep,
    school: str = Query(..., min_length=1, description="必填：sysu/scut/jnu/scnu 或简称"),
    code: str | None = None,
    college: str | None = None,
    year: int | None = Query(2026, ge=2000, le=2100),
    include_special: bool = True,
) -> ScoreLinesResponse:
    _school_or_404(q, school)
    result = q.get_score_lines(school=school, code=code, college=college, year=year, include_special=include_special)
    return ScoreLinesResponse(**result)


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(
    q: KaoyanQueryDep,
    school: str | None = None,
    doc_type: str | None = None,
    year: int | None = _YEAR,
) -> DocumentListResponse:
    _school_or_404(q, school)
    docs = q.list_sources(school=school, doc_type=doc_type, year=year)
    return DocumentListResponse(count=len(docs), documents=docs)


@router.get("/documents/{doc_id}", response_model=DocumentDetailResponse)
def get_document(doc_id: str, q: KaoyanQueryDep) -> DocumentDetailResponse:
    doc = q.document(doc_id)
    if doc is None:
        raise http_error(404, "document_not_found", f"文档不存在: {doc_id}")
    return DocumentDetailResponse(**doc)
