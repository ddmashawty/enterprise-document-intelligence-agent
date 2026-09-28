"""Extractor protocol and the ``Fact`` rows every extractor produces.

A fact names its program the way the source does (college code / slug / name,
program code, study mode as written); ``apply.py`` resolves it against the
``programs`` table, compares it with the seed and writes it. Every fact carries
``source_doc_id`` and a verbatim ``evidence_text`` excerpt of its source.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.ingest.tables import Table
from doc_agent.kaoyan.normalize import Subject, clean, parse_college

FactTable = Literal["plans", "score_lines", "exam_subjects", "directions", "admission_stats"]

PROGRAM_PREFIX_RE = re.compile(r"^(\d{4}[0-9A-Z]{2})\s*(.*)$")
PROGRAM_ANY_RE = re.compile(r"(?<![0-9A-Z])(\d{4}[0-9A-Z]{2})(?![0-9A-Z])")
POOL_CODE_RE = re.compile(r"^\d{4}$")

# 一级学科 names used in "按一级学科统筹" notes (教育部学科目录).
FIRST_LEVEL_CODES: dict[str, str] = {
    "理论经济学": "0201",
    "应用经济学": "0202",
    "数学": "0701",
    "物理学": "0702",
    "化学": "0703",
    "生物学": "0710",
    "统计学": "0714",
    "力学": "0801",
    "机械工程": "0802",
    "光学工程": "0803",
    "材料科学与工程": "0805",
    "电气工程": "0808",
    "电子科学与技术": "0809",
    "信息与通信工程": "0810",
    "控制科学与工程": "0811",
    "计算机科学与技术": "0812",
    "软件工程": "0835",
    "网络空间安全": "0839",
}


@dataclass(frozen=True)
class ExtractContext:
    """What sources.json says about the document being extracted."""

    doc_id: str
    school_id: str
    year: int | None
    doc_type: str | None = None
    format: str | None = None
    title: str = ""
    college: str | None = None
    publish_date: str | None = None
    local_path: str = ""
    contains_personal_data: bool = False

    @classmethod
    def from_entry(cls, entry: dict[str, Any]) -> ExtractContext:
        year = entry.get("intake_year")
        if not year and str(entry.get("publish_date") or "")[:4].isdigit():
            year = int(str(entry["publish_date"])[:4])
        return cls(
            doc_id=str(entry["doc_id"]),
            school_id=str(entry.get("school") or ""),
            year=int(year) if year else None,
            doc_type=entry.get("doc_type"),
            format=entry.get("format"),
            title=str(entry.get("title") or ""),
            college=entry.get("college"),
            publish_date=entry.get("publish_date"),
            local_path=str(entry.get("local_path") or ""),
            contains_personal_data=bool(entry.get("contains_personal_data")),
        )

    @property
    def college_ref(self) -> str | None:
        """College code ('670') or name ('计算机科学与工程学院'); None for school-level documents."""
        text = clean(self.college)
        if not text or "校级" in text:
            return None
        parsed = parse_college(text)
        return parsed.code or parsed.name


@dataclass(frozen=True)
class ProgramRef:
    """A program as written in the source.

    ``code`` is a 6-char program code, or a 4-digit 一级学科 code meaning every
    program of the college under it. ``study_mode`` is None when the source does
    not say; the resolver then accepts the college's only program with that code.
    """

    college: str | None
    code: str
    study_mode: str | None = None

    @property
    def is_pool(self) -> bool:
        return bool(POOL_CODE_RE.fullmatch(self.code))


@dataclass
class Fact:
    table: FactTable
    kind: str
    school_id: str
    year: int
    source_doc_id: str
    evidence_text: str
    program: ProgramRef | None = None
    page: int | None = None
    values: dict[str, Any] = field(default_factory=dict)
    extraction_method: str = "rule"
    extractor: str = ""


class FactSet(list[Fact]):
    """Builds facts sharing one document context."""

    def __init__(self, ctx: ExtractContext, extractor: str, method: str = "rule") -> None:
        super().__init__()
        self.ctx = ctx
        self.extractor = extractor
        self.method = method

    def _add(
        self,
        table: FactTable,
        kind: str,
        program: ProgramRef | None,
        evidence: str,
        values: dict[str, Any],
        *,
        year: int | None = None,
        page: int | None = None,
    ) -> None:
        y = year or self.ctx.year
        if y is None:
            raise ValueError(f"{self.ctx.doc_id}: no year for {table}/{kind}")
        self.append(
            Fact(
                table=table,
                kind=kind,
                school_id=self.ctx.school_id,
                year=y,
                source_doc_id=self.ctx.doc_id,
                evidence_text=clean(evidence),
                program=program,
                page=page,
                values=values,
                extraction_method=self.method,
                extractor=self.extractor,
            )
        )

    def plan(
        self,
        kind: str,
        program: ProgramRef,
        value: int | None,
        *,
        evidence: str,
        definition: str,
        value_text: str | None = None,
        is_upper_bound: bool = False,
        pool_scope: str | None = None,
        year: int | None = None,
        page: int | None = None,
    ) -> None:
        if value is None:
            return
        self._add(
            "plans",
            kind,
            program,
            evidence,
            {
                "value": value,
                "value_text": clean(value_text) if value_text is not None else str(value),
                "is_upper_bound": is_upper_bound,
                "pool_scope": pool_scope,
                "definition": definition,
            },
            year=year,
            page=page,
        )

    def line(
        self,
        scope: str,
        program: ProgramRef | None,
        total: int | None,
        singles: Sequence[int | None] = (None, None, None, None),
        *,
        evidence: str,
        definition: str,
        discipline_code: str | None = None,
        raw_text: str | None = None,
        year: int | None = None,
        page: int | None = None,
    ) -> None:
        if total is None:
            return
        politics, foreign_lang, subject1, subject2 = (list(singles) + [None] * 4)[:4]
        self._add(
            "score_lines",
            scope,
            program,
            evidence,
            {
                "discipline_code": discipline_code,
                "total": total,
                "politics": politics,
                "foreign_lang": foreign_lang,
                "subject1": subject1,
                "subject2": subject2,
                "raw_text": clean(raw_text) if raw_text else clean(evidence),
                "definition": definition,
            },
            year=year,
            page=page,
        )

    def stat(
        self,
        kind: str,
        program: ProgramRef,
        value: int | None,
        *,
        evidence: str,
        definition: str,
        pool_scope: str | None = None,
        year: int | None = None,
    ) -> None:
        if value is None:
            return
        self._add(
            "admission_stats",
            kind,
            program,
            evidence,
            {"value": value, "pool_scope": pool_scope, "definition": definition},
            year=year,
        )

    def subjects(
        self,
        program: ProgramRef,
        subjects: Sequence[Subject],
        *,
        evidence: str,
        year: int | None = None,
        page: int | None = None,
    ) -> None:
        for slot, s in enumerate(subjects, start=1):
            self._add(
                "exam_subjects",
                "known",
                program,
                evidence,
                {"slot": slot, "code": s.code, "name": s.name, "status": "known", "unknown_reason": None},
                year=year,
                page=page,
            )

    def no_exam(
        self,
        program: ProgramRef,
        *,
        reason: str,
        evidence: str,
        year: int | None = None,
        page: int | None = None,
    ) -> None:
        self._add(
            "exam_subjects",
            "no_exam",
            program,
            evidence,
            {"slot": None, "code": None, "name": None, "status": "no_exam", "unknown_reason": reason},
            year=year,
            page=page,
        )

    def direction(
        self,
        program: ProgramRef,
        code: str | None,
        name: str,
        *,
        evidence: str,
        note: str | None = None,
        year: int | None = None,
    ) -> None:
        if not clean(name):
            return
        self._add(
            "directions",
            "direction",
            program,
            evidence,
            {"code": code, "name": clean(name), "note": note},
            year=year,
        )


class Extractor(Protocol):
    name: str

    def matches(self, ctx: ExtractContext) -> bool: ...

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]: ...


# -- helpers shared by the rule extractors ------------------------------------


def compact(text: str | None) -> str:
    return re.sub(r"\s+", "", clean(text))


def leading_int(text: str | None) -> int | None:
    m = re.match(r"\s*(\d+)", clean(text))
    return int(m.group(1)) if m else None


def row_text(table: Table, r: int, limit: int | None = None) -> str:
    values = table.row_values(r)
    return " | ".join(values[:limit] if limit else values)


def study_mode_of(text: str | None) -> str | None:
    raw = clean(text)
    if "非全日制" in raw:
        return "非全日制"
    if "全日制" in raw:
        return "全日制"
    return None


def special_kind(text: str | None) -> str | None:
    """少干 / 少数民族骨干 → special_minority; 退役（大学生）士兵 → special_veteran."""
    raw = clean(text)
    if "少干" in raw or "少数民族" in raw:
        return "special_minority"
    if "退役" in raw:
        return "special_veteran"
    return None


def find_header(table: Table, *needles: str, max_rows: int = 8) -> int | None:
    """First row (within ``max_rows``) whose cells contain every needle (spaces ignored)."""
    wanted = [compact(n) for n in needles]
    for r in range(min(table.n_rows, max_rows)):
        cells = [compact(c) for c in table.cells[r]]
        if all(any(w in c for c in cells) for w in wanted):
            return r
    return None


def header_col(table: Table, header_row: int, *names: str, exact: bool = False) -> int | None:
    """Column whose header cell (spaces ignored) equals / contains one of ``names``."""
    cells = [compact(c) for c in table.cells[header_row]]
    for name in names:
        want = compact(name)
        for c, cell in enumerate(cells):
            if (cell == want) if exact else (want in cell):
                return c
    return None


def cell(table: Table, r: int, c: int | None) -> str:
    if c is None or c >= table.n_cols:
        return ""
    return clean(table.cells[r][c])
