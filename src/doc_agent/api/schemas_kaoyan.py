from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProgramSearchResponse(BaseModel):
    """Programs matching the filters; undecidable ones are in ``unknown`` with reasons."""

    filters: dict[str, Any] = Field(default_factory=dict)
    count: int
    programs: list[dict[str, Any]] = Field(default_factory=list)
    unknown: list[dict[str, Any]] = Field(default_factory=list)
    excluded: int = 0
    public_plan_rule: str | None = None
    scope_note: str | None = None


class ProgramDetailResponse(BaseModel):
    """All facts of one program; each fact carries 口径 (definition) and source."""

    program_id: str
    school: str
    school_name: str
    college: str
    college_code: str | None = None
    code: str
    name: str
    degree_type: str | None = None
    study_mode: str
    is_boundary: bool = False
    pool_code: str | None = None
    plans: list[dict[str, Any]] = Field(default_factory=list)
    public_plan: list[dict[str, Any]] = Field(default_factory=list)
    public_plan_unknown: list[str] = Field(default_factory=list)
    score_lines: list[dict[str, Any]] = Field(default_factory=list)
    exam_subjects: list[dict[str, Any]] = Field(default_factory=list)
    directions: list[dict[str, Any]] = Field(default_factory=list)
    admission_stats: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None
    notes_source: str | None = None


class ScoreLinesResponse(BaseModel):
    year: int | None = None
    count: int
    programs: list[dict[str, Any]] = Field(default_factory=list)
    unknown: str | None = None


class DocumentMeta(BaseModel):
    """Source document metadata only; content is never served (名单类 documents included)."""

    doc_id: str
    school: str
    college: str | None = None
    title: str
    publish_date: str | None = None
    intake_year: int | None = None
    doc_type: str
    format: str | None = None
    page_url: str | None = None
    attachment_url: str | None = None
    pages: int | None = None
    contains_personal_data: bool = False
    content_available: bool = False
    status: str | None = None


class DocumentDetailResponse(DocumentMeta):
    notes: str | None = None
    fact_counts: dict[str, int] = Field(default_factory=dict)


class DocumentListResponse(BaseModel):
    count: int
    documents: list[DocumentMeta] = Field(default_factory=list)
