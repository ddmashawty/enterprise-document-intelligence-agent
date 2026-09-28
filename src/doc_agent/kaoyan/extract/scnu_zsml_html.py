"""华南师范大学目录系统查询结果（Zsml_View）HTML.

Rows: 院系行 "019 | 计算机学院 | 141(30)"; 专业行 "081200 | 计算机科学与技术 | 48(17)"（总(推免)）;
方向行 "01 | 计算机软件 | ① 101|思想政治理论 ② 201|英语（一）… | 复试科目 | 备注".
A program row without "(推免)" whose 备注 says "不招推免生" gets 推免数 0 from that note.
Study mode comes from the query page (title says 非全日制 for part-time pages).
"""

from __future__ import annotations

import re

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.kaoyan.extract.base import (
    ExtractContext,
    Fact,
    FactSet,
    ProgramRef,
    row_text,
)
from doc_agent.kaoyan.normalize import (
    normalize_program_code,
    parse_total_tm,
    split_subjects,
)

_COLLEGE_RE = re.compile(r"^\d{3}$")
_DIRECTION_RE = re.compile(r"^[0-9A-Z]{2}$")


def subjects_text(text: str) -> str:
    """'① 101|思想政治理论 ② 201|英语（一）' → '① 101 思想政治理论 ② 201 英语（一）'."""
    return re.sub(r"(\d{3})\s*\|\s*", r"\1 ", text)


class ScnuZsmlHtml:
    name = "scnu_zsml_html"

    def matches(self, ctx: ExtractContext) -> bool:
        return (
            ctx.school_id == "scnu"
            and ctx.doc_type == "catalog"
            and ctx.format == "html"
            and "Zsml" in ctx.local_path
        )

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        facts = FactSet(ctx, self.name)
        mode = "非全日制" if "非全日制" in ctx.title else "全日制"
        for table in doc.tables:
            college: str | None = None
            program: ProgramRef | None = None
            subjects_done: set[ProgramRef] = set()
            tm_known: set[ProgramRef] = set()
            for r in range(table.n_rows):
                vals = table.row_values(r)
                if len(vals) < 2:
                    continue
                first = vals[0]
                if _COLLEGE_RE.fullmatch(first):
                    college = first
                    program = None
                elif college and (code := normalize_program_code(first)):
                    program = ProgramRef(college, code, mode)
                    total, tm = parse_total_tm(vals[2] if len(vals) > 2 else "")
                    evidence = row_text(table, r)
                    facts.plan(
                        "catalog_total",
                        program,
                        total,
                        evidence=evidence,
                        definition=f"{ctx.year}年招生专业目录拟招生人数（含推免）",
                        value_text=vals[2],
                    )
                    facts.plan(
                        "tm",
                        program,
                        tm,
                        evidence=evidence,
                        definition="招生专业目录“总(推免)”中的推免数",
                        value_text=vals[2],
                    )
                    if tm is not None:
                        tm_known.add(program)
                elif program and _DIRECTION_RE.fullmatch(first):
                    facts.direction(program, first, vals[1], evidence=row_text(table, r, limit=2))
                    note = next((v for v in vals[2:] if "不招推免生" in v), "")
                    if note and program not in tm_known:
                        facts.plan("tm", program, 0, evidence=note, definition="招生专业目录备注“不招推免生”")
                        tm_known.add(program)
                    exam = next((v for v in vals[2:] if "①" in v), "")
                    if exam and program not in subjects_done:
                        text = subjects_text(exam)
                        subjects = split_subjects(text)
                        if subjects:
                            facts.subjects(program, subjects, evidence=exam)
                            subjects_done.add(program)
        return facts
