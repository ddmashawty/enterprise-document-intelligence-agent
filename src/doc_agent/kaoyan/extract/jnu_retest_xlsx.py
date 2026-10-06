"""暨南大学各学院《复试方案及复试名单》xlsx — only the 复试方案 table is read.

Header: 专业代码 | 专业名称 | 统招计划（不含推免生） | 复试人数 | 复试资格线 | 复试比例 | …
A 4-digit code ("0812 | 计算机科学与技术") is a 一级学科 counted as a whole: its plan,
retest count and line apply to every program of the college under it. The 复试名单
sheets (names, scores) are never read, and evidence keeps only the first six columns.
"""

from __future__ import annotations

import re

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.kaoyan.extract.base import (
    POOL_CODE_RE,
    ExtractContext,
    Fact,
    FactSet,
    ProgramRef,
    cell,
    compact,
    find_header,
    header_col,
    leading_int,
    row_text,
)
from doc_agent.kaoyan.normalize import normalize_program_code

_LINE_PARTS = (r"总分\s*(\d+)", r"政治[^\d，,]*(\d+)", r"外语\s*(\d+)", r"业务一\s*(\d+)", r"业务二\s*(\d+)")


def parse_line_text(text: str) -> tuple[int | None, ...]:
    """'总分264，政治/联考35，外语35，业务一53，业务二53' → (264, 35, 35, 53, 53)."""
    out: list[int | None] = []
    for pattern in _LINE_PARTS:
        m = re.search(pattern, text)
        out.append(int(m.group(1)) if m else None)
    return tuple(out)


class JnuRetestXlsx:
    name = "jnu_retest_xlsx"

    def matches(self, ctx: ExtractContext) -> bool:
        return ctx.school_id == "jnu" and ctx.doc_type == "retest_rules" and ctx.format == "xlsx"

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        facts = FactSet(ctx, self.name)
        for table in doc.tables:
            h = find_header(table, "统招计划", "复试资格线")
            if h is None:
                continue
            c_code = header_col(table, h, "专业代码")
            c_plan = header_col(table, h, "统招计划")
            c_count = header_col(table, h, "复试人数")
            c_line = header_col(table, h, "复试资格线")
            for r in range(h + 1, table.n_rows):
                raw_code = compact(cell(table, r, c_code))
                pool = raw_code if POOL_CODE_RE.fullmatch(raw_code) else None
                code = pool or normalize_program_code(raw_code)
                if not code:
                    continue
                program = ProgramRef(ctx.college_ref, code)
                evidence = row_text(table, r, limit=6)
                if pool:
                    plan_def = f"{ctx.year}年{pool}一级学科统筹“统招计划”（二级学科不单列）"
                    count_def = f"{ctx.year}年{pool}一级学科复试人数"
                else:
                    plan_def = f"{ctx.year}年学院复试方案“统招计划”"
                    count_def = f"{ctx.year}年复试人数"
                facts.plan(
                    "public_exam",
                    program,
                    leading_int(cell(table, r, c_plan)),
                    evidence=evidence,
                    definition=plan_def,
                    pool_scope=pool,
                )
                facts.stat(
                    "retest_count",
                    program,
                    leading_int(cell(table, r, c_count)),
                    evidence=evidence,
                    definition=count_def,
                    pool_scope=pool,
                )
                line_text = cell(table, r, c_line)
                total, *singles = parse_line_text(line_text)
                facts.line(
                    "college",
                    program,
                    total,
                    singles,
                    evidence=evidence,
                    definition=f"学院公布的{ctx.year}年复试分数线",
                    raw_text=line_text,
                )
        return facts
