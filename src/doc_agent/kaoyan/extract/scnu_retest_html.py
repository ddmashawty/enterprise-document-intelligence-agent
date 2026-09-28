"""华南师范大学学院《硕士研究生招生复试方案》HTML — only the plan and score-line tables.

Plan table: 序号 | 学习方式 | 专业代码 | 专业名称 | 拟招生人数 | 已招收推免生数 | 复试差额比例, where a
bracket after the count says what the row is: "（含…联培专项…）" annotates the main plan,
"（退役大学生士兵计划）" is a special plan, anything else (e.g. 立功表彰免初试) is skipped.
Line table: … | 专业名称 [(退役大学生士兵计划)] | 政治 | 外国语 | 业务一 | 业务二 | 总分.
Candidate tables (考生姓名 / 初试成绩) are never read.
"""

from __future__ import annotations

import re

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.ingest.tables import Table
from doc_agent.kaoyan.extract.base import (
    ExtractContext,
    Fact,
    FactSet,
    ProgramRef,
    cell,
    find_header,
    header_col,
    leading_int,
    row_text,
    special_kind,
)
from doc_agent.kaoyan.extract.sysu_retest_html import (
    LINE_DEFINITIONS,
    SPECIAL_PLAN_DEFINITIONS,
)
from doc_agent.kaoyan.normalize import normalize_program_code

_BRACKET_RE = re.compile(r"[（(]\s*([^）)]*?)\s*[）)]")


def bracket(text: str) -> str:
    m = _BRACKET_RE.search(text)
    return m.group(1) if m else ""


class ScnuRetestHtml:
    name = "scnu_retest_html"

    def matches(self, ctx: ExtractContext) -> bool:
        return ctx.school_id == "scnu" and ctx.doc_type == "retest_rules" and ctx.format == "html"

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        facts = FactSet(ctx, self.name)
        for table in doc.tables:
            if find_header(table, "考生姓名") is not None or find_header(table, "初试成绩") is not None:
                continue
            if (h := find_header(table, "拟招生人数", "推免生数")) is not None:
                self._plans(table, h, ctx, facts)
            elif (h := find_header(table, "总分", "政治", "业务一")) is not None:
                self._lines(table, h, ctx, facts)
        return facts

    @staticmethod
    def _program(table: Table, r: int, c_code: int | None, c_mode: int | None, ctx: ExtractContext) -> ProgramRef | None:
        code = normalize_program_code(cell(table, r, c_code))
        if not code:
            return None
        return ProgramRef(ctx.college_ref, code, cell(table, r, c_mode) or None)

    def _plans(self, table: Table, h: int, ctx: ExtractContext, facts: FactSet) -> None:
        c_mode = header_col(table, h, "学习方式")
        c_code = header_col(table, h, "专业代码")
        c_plan = header_col(table, h, "拟招生人数")
        c_tm = header_col(table, h, "推免生数")
        for r in range(h + 1, table.n_rows):
            program = self._program(table, r, c_code, c_mode, ctx)
            if program is None:
                continue
            plan_text = cell(table, r, c_plan)
            note = bracket(plan_text)
            evidence = row_text(table, r)
            special = special_kind(note)
            if special:
                facts.plan(
                    special,
                    program,
                    leading_int(plan_text),
                    evidence=evidence,
                    definition=SPECIAL_PLAN_DEFINITIONS[special],
                    value_text=plan_text,
                )
                continue
            if note and not note.startswith("含"):
                continue
            facts.plan(
                "rules_total",
                program,
                leading_int(plan_text),
                evidence=evidence,
                definition=f"学院{ctx.year}复试方案“拟招生人数”",
                value_text=plan_text,
            )
            facts.plan(
                "tm",
                program,
                leading_int(cell(table, r, c_tm)),
                evidence=evidence,
                definition=f"学院{ctx.year}复试方案“已招收推免生数”",
            )

    def _lines(self, table: Table, h: int, ctx: ExtractContext, facts: FactSet) -> None:
        c_mode = header_col(table, h, "学习方式")
        c_code = header_col(table, h, "专业代码")
        c_name = header_col(table, h, "专业名称")
        cols = [header_col(table, h, n, exact=True) for n in ("总分", "政治", "外国语", "业务一", "业务二")]
        for r in range(h + 1, table.n_rows):
            program = self._program(table, r, c_code, c_mode, ctx)
            if program is None:
                continue
            total, *singles = (leading_int(cell(table, r, c)) for c in cols)
            scope = special_kind(bracket(cell(table, r, c_name))) or "college"
            facts.line(
                scope,
                program,
                total,
                singles,
                evidence=row_text(table, r),
                definition=LINE_DEFINITIONS[scope].format(year=ctx.year),
            )
