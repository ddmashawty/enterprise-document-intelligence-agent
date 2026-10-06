"""中山大学《硕士招生学科专业目录》PDF.

Rows: 学院行 "670 计算机学院 | 325"; 专业行 "081200 计算机科学与技术 | 65 | ①101…复试专业课: … | 备注";
方向行 "69 不分方向 (全日制) | | ①101…". The college context carries over page / table breaks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.ingest.tables import Table
from doc_agent.kaoyan.extract.base import (
    ExtractContext,
    Fact,
    FactSet,
    ProgramRef,
    leading_int,
    row_text,
)
from doc_agent.kaoyan.normalize import clean, split_subjects

_COLLEGE_RE = re.compile(r"^(\d{3})\s+(\S.*)$")
_PROGRAM_RE = re.compile(r"^(\d{4}[0-9A-Z]{2})\s+(\S.*)$")
_DIRECTION_RE = re.compile(r"^([0-9A-Z]{2})\s+(.+?)\s*[（(](全日制|非全日制)[）)]\s*$")
TM_ONLY = "仅招收推免生"


def exam_part(text: str) -> str:
    return clean(re.split(r"复试专业课", text, maxsplit=1)[0])


@dataclass
class _Block:
    college: str | None
    code: str
    name: str
    count: int | None
    count_text: str
    evidence: str
    subjects_text: str
    note: str
    page: int
    # (code, name, study mode, exam subjects text, raw cell)
    directions: list[tuple[str, str, str, str, str]] = field(default_factory=list)


class SysuCatalogPdf:
    name = "sysu_catalog_pdf"

    def matches(self, ctx: ExtractContext) -> bool:
        return ctx.school_id == "sysu" and ctx.doc_type == "catalog" and str(ctx.format).startswith("pdf")

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        facts = FactSet(ctx, self.name)
        college: str | None = None
        block: _Block | None = None
        for table in doc.tables:
            for r in range(table.n_rows):
                vals = table.row_values(r)
                if not vals or vals[0].startswith("学科代码"):
                    continue
                first = vals[0]
                subjects = next((v for v in vals[1:] if "①" in v), "")
                if (m := _PROGRAM_RE.match(first)) and not _DIRECTION_RE.match(first):
                    self._flush(block, ctx, facts)
                    count = leading_int(vals[1]) if len(vals) > 1 and "①" not in vals[1] else None
                    block = _Block(
                        college=college,
                        code=m.group(1),
                        name=m.group(2),
                        count=count,
                        count_text=vals[1] if count is not None else "",
                        evidence=row_text(table, r),
                        subjects_text=exam_part(subjects),
                        note=self._note(table, r),
                        page=table.page,
                    )
                elif (m := _COLLEGE_RE.match(first)) and not subjects:
                    self._flush(block, ctx, facts)
                    block = None
                    college = m.group(1)
                elif (m := _DIRECTION_RE.match(first)) and block is not None:
                    block.directions.append((m.group(1), m.group(2), m.group(3), exam_part(subjects), first))
        self._flush(block, ctx, facts)
        return facts

    @staticmethod
    def _note(table: Table, r: int) -> str:
        last = clean(table.cells[r][-1]) if table.n_cols else ""
        return last if last and "①" not in last and not _PROGRAM_RE.match(last) else ""

    def _flush(self, block: _Block | None, ctx: ExtractContext, facts: FactSet) -> None:
        if block is None or block.college is None:
            return
        modes = {d[2] for d in block.directions}
        mode = modes.pop() if len(modes) == 1 else None
        program = ProgramRef(block.college, block.code, mode)
        facts.plan(
            "catalog_total",
            program,
            block.count,
            evidence=block.evidence,
            definition=f"{ctx.year}年招生专业目录拟招生人数（含推免）",
            value_text=block.count_text,
            page=block.page,
        )
        if TM_ONLY in block.note:
            facts.no_exam(
                program,
                reason=f"目录注明“{TM_ONLY}”，无统考科目、无复试线",
                evidence=block.evidence,
                page=block.page,
            )
        else:
            text = block.subjects_text or next((d[3] for d in block.directions if d[3]), "")
            subjects = split_subjects(text)
            if subjects:
                facts.subjects(program, subjects, evidence=text, page=block.page)
        for code, name, d_mode, _, raw in block.directions:
            facts.direction(ProgramRef(block.college, block.code, d_mode), code, name, evidence=raw)
