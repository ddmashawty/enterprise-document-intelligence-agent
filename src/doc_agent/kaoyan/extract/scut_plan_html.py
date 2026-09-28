"""华南理工大学统考计划.

* 学院通知附件（HTML）: 专业名称 [代码] | 统考招生计划数 | 备注 → ``college_exam_plan``. A row whose
  备注 names a separate sub-plan ("中法南特联培项目") is skipped; "含…" only annotates the main row.
* 学校《统考可用计划》（PDF / HTML）: 招生学院（系）名称 | 招生专业代码及名称 | 学习方式 | 统考可用计划 →
  ``available_exam``.
"""

from __future__ import annotations

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.ingest.tables import Table
from doc_agent.kaoyan.extract.base import (
    PROGRAM_ANY_RE,
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


class ScutPlan:
    name = "scut_plan_html"

    def matches(self, ctx: ExtractContext) -> bool:
        return ctx.school_id == "scut" and ctx.doc_type == "plan_quota"

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        facts = FactSet(ctx, self.name)
        for table in doc.tables:
            if (h := find_header(table, "招生学院", "统考可用计划")) is not None:
                self._available(table, h, ctx, facts)
            elif (h := find_header(table, "统考")) is not None and ctx.college_ref:
                self._college(table, h, ctx, facts)
        return facts

    def _available(self, table: Table, h: int, ctx: ExtractContext, facts: FactSet) -> None:
        c_college = header_col(table, h, "招生学院")
        c_program = header_col(table, h, "专业代码")
        c_mode = header_col(table, h, "学习方式")
        c_value = header_col(table, h, "统考可用计划")
        published = f"（{ctx.publish_date} 公布）" if ctx.publish_date else ""
        for r in range(h + 1, table.n_rows):
            m = PROGRAM_ANY_RE.search(cell(table, r, c_program))
            college = cell(table, r, c_college)
            if not m or not college:
                continue
            value_text = cell(table, r, c_value)
            facts.plan(
                "available_exam",
                ProgramRef(college, m.group(1), cell(table, r, c_mode) or None),
                leading_int(value_text),
                evidence=row_text(table, r),
                definition=f"学校“统考可用计划”{published}",
                value_text=value_text,
                page=table.page,
            )

    def _college(self, table: Table, h: int, ctx: ExtractContext, facts: FactSet) -> None:
        c_value = header_col(table, h, "统考")
        c_note = header_col(table, h, "备注")
        label = compact(table.cells[h][c_value]).removesuffix("数")
        for r in range(h + 1, table.n_rows):
            m = PROGRAM_ANY_RE.search(" ".join(table.cells[r][:c_value]))
            note = cell(table, r, c_note)
            if not m or (note and not note.startswith("含")):
                continue
            value_text = cell(table, r, c_value)
            facts.plan(
                "college_exam_plan",
                ProgramRef(ctx.college_ref, m.group(1)),
                leading_int(value_text),
                evidence=row_text(table, r),
                definition=f"学院通知“{label}”",
                value_text=value_text,
            )
