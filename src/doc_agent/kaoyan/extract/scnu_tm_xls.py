"""华南师范大学《推免硕士研究生招生专业目录》xls.

Header: 院系代码 | 院系名称 | 学院拟接收推免人数 | 专业代码 | 专业名称 | 专业拟招推免生人数 | 学习方式 |
研究方向代码 | 研究方向名称 — one row per direction; vertically merged cells arrive blank.
"""

from __future__ import annotations

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.kaoyan.extract.base import (
    ExtractContext,
    Fact,
    FactSet,
    ProgramRef,
    cell,
    find_header,
    header_col,
    leading_int,
)
from doc_agent.kaoyan.normalize import normalize_program_code


class ScnuTmXls:
    name = "scnu_tm_xls"

    def matches(self, ctx: ExtractContext) -> bool:
        return ctx.school_id == "scnu" and ctx.doc_type == "tm_catalog" and str(ctx.format).startswith("xls")

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        facts = FactSet(ctx, self.name)
        for raw in doc.tables:
            h = find_header(raw, "专业拟招推免生人数", "专业代码")
            if h is None:
                continue
            c_college = header_col(raw, h, "院系代码")
            c_code = header_col(raw, h, "专业代码")
            c_tm = header_col(raw, h, "专业拟招推免生人数")
            c_mode = header_col(raw, h, "学习方式")
            c_dir_code = header_col(raw, h, "研究方向代码")
            c_dir_name = header_col(raw, h, "研究方向名称")
            program_cols = c_dir_code if c_dir_code is not None else raw.n_cols
            table = raw.ffill(range(program_cols))
            seen: set[ProgramRef] = set()
            for r in range(h + 1, table.n_rows):
                code = normalize_program_code(cell(table, r, c_code))
                college = cell(table, r, c_college)
                if not code or not college:
                    continue
                program = ProgramRef(college, code, cell(table, r, c_mode) or None)
                head = " | ".join(table.cells[r][:program_cols])
                if program not in seen:
                    seen.add(program)
                    facts.plan(
                        "tm",
                        program,
                        leading_int(cell(table, r, c_tm)),
                        evidence=head,
                        definition=f"{ctx.year}年推免硕士招生专业目录中的推免数",
                    )
                dir_code = cell(table, r, c_dir_code)
                dir_name = cell(table, r, c_dir_name)
                facts.direction(program, dir_code or None, dir_name, evidence=f"{head} | {dir_code} | {dir_name}")
        return facts
