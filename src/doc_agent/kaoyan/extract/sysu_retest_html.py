"""中山大学学院《复试录取实施细则》: 复试分数线表 + 拟招生人数表（总计划 / 已招推免生 / 公开招考计划）.

Also reads the same tables published as images (软件工程学院 / 电子与通信工程学院) once OCR
has rebuilt them.
"""

from __future__ import annotations

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
    study_mode_of,
)
from doc_agent.kaoyan.normalize import normalize_program_code

LINE_DEFINITIONS = {
    "college": "学院公布的{year}年复试分数线",
    "special_veteran": "退役大学生士兵专项计划复试线",
    "special_minority": "少数民族高层次骨干人才计划复试线",
}
SPECIAL_PLAN_DEFINITIONS = {
    "special_veteran": "退役大学生士兵专项计划",
    "special_minority": "少数民族高层次骨干人才计划",
}


class SysuRetestHtml:
    name = "sysu_retest_html"

    def matches(self, ctx: ExtractContext) -> bool:
        return ctx.school_id == "sysu" and ctx.doc_type == "retest_rules" and str(ctx.format).startswith(("html", "img"))

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        facts = FactSet(ctx, self.name)
        for table in doc.tables:
            if (h := find_header(table, "总分", "政治", "业务课一")) is not None:
                self._lines(table, h, ctx, facts)
            elif (h := find_header(table, "总计划", "已招推免")) is not None:
                self._plans(table, h, ctx, facts)
        return facts

    def _lines(self, table: Table, h: int, ctx: ExtractContext, facts: FactSet) -> None:
        c_code = header_col(table, h, "专业代码")
        c_name = header_col(table, h, "专业名称")
        cols = [header_col(table, h, n, exact=True) for n in ("总分", "政治", "外语", "业务课一", "业务课二")]
        c_note = next((c for hr in range(h, -1, -1) if (c := header_col(table, hr, "备注")) is not None), None)
        for r in range(h + 1, table.n_rows):
            code = normalize_program_code(cell(table, r, c_code))
            if not code:
                continue
            total, *singles = (leading_int(cell(table, r, c)) for c in cols)
            scope = special_kind(cell(table, r, c_note)) or "college"
            program = ProgramRef(ctx.college_ref, code, study_mode_of(cell(table, r, c_name)))
            facts.line(
                scope,
                program,
                total,
                singles,
                evidence=row_text(table, r),
                definition=LINE_DEFINITIONS[scope].format(year=ctx.year),
            )

    def _plans(self, table: Table, h: int, ctx: ExtractContext, facts: FactSet) -> None:
        c_code = header_col(table, h, "代码")
        c_name = header_col(table, h, "名称")
        c_total = header_col(table, h, "总计划")
        c_tm = header_col(table, h, "已招推免")
        c_public = header_col(table, h, "公开招考")
        c_note = header_col(table, h, "备注")
        for r in range(h + 1, table.n_rows):
            code = normalize_program_code(cell(table, r, c_code))
            if not code:
                continue
            program = ProgramRef(ctx.college_ref, code, study_mode_of(cell(table, r, c_name)))
            evidence = row_text(table, r)
            total = leading_int(cell(table, r, c_total))
            special = special_kind(cell(table, r, c_note))
            if special:
                facts.plan(special, program, total, evidence=evidence, definition=SPECIAL_PLAN_DEFINITIONS[special])
                continue
            facts.plan("rules_total", program, total, evidence=evidence, definition="学院复试细则“总计划”")
            facts.plan(
                "tm",
                program,
                leading_int(cell(table, r, c_tm)),
                evidence=evidence,
                definition=f"学院{ctx.year}复试细则“已招推免”",
            )
            facts.plan(
                "public_exam",
                program,
                leading_int(cell(table, r, c_public)),
                evidence=evidence,
                definition="学院复试细则“公开招考”",
            )
