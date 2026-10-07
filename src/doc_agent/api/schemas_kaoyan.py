from __future__ import annotations

from typing import Any, Literal

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


class CrawlRequest(BaseModel):
    """Polite crawl of official sites; ``dry_run`` (default) only lists what would be fetched."""

    schools: list[str] = Field(default_factory=list, description="空 = sites.json 里的全部学校")
    mode: Literal["probe", "list", "full"] = "probe"
    dry_run: bool = True
    max_pages: int | None = Field(None, ge=1, le=200, description="每校本次最多请求数（robots.txt 不计）")
    list_pages: int | None = Field(None, ge=1, le=20, description="list / full：每个列表最多翻几页")


class CrawlRunResponse(BaseModel):
    run_id: str
    status: str
    mode: str | None = None
    school_ids: list[str] = Field(default_factory=list)
    dry_run: bool | None = None
    max_pages: int | None = None
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
