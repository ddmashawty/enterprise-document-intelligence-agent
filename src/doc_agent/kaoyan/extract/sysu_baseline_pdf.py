"""中山大学《复试基本分数线》PDF: 类别 | 学科门类/学位类别 | 总分 | 单科(=100) | 单科(>100).

One row may list several disciplines ("城乡规划[0853]、电子信息[0854]、…"); each
becomes its own school-level line. Only 学术学位 / 专业学位 rows are read.
"""

from __future__ import annotations

import re

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.kaoyan.extract.base import (
    ExtractContext,
    Fact,
    FactSet,
    cell,
    find_header,
    header_col,
    leading_int,
    row_text,
)

_DISCIPLINE_RE = re.compile(r"([^\[\]、，,]+?)\s*\[([0-9A-Z]+)\]")
# 单独考试 / special-plan rows reuse discipline codes but are separate admission tracks.
_CATEGORIES = ("学术学位", "专业学位")


class SysuBaselinePdf:
    name = "sysu_baseline_pdf"

    def matches(self, ctx: ExtractContext) -> bool:
        return (
            ctx.school_id == "sysu"
            and ctx.doc_type == "score_line"
            and str(ctx.format).startswith("pdf")
            and "基本分数线" in ctx.title
        )

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        facts = FactSet(ctx, self.name)
        for table in doc.tables:
            h = find_header(table, "学科门类", "总分")
            if h is None:
                continue
            c_kind = header_col(table, h, "类别", exact=True)
            c_name = header_col(table, h, "学科门类")
            c_total = header_col(table, h, "总分")
            c_100 = header_col(table, h, "满分=100")
            c_gt = header_col(table, h, "满分>100")
            for r in range(h + 1, table.n_rows):
                total = leading_int(cell(table, r, c_total))
                if total is None:
                    continue
                category = cell(table, r, c_kind)
                if c_kind is not None and category not in _CATEGORIES:
                    continue
                s100 = leading_int(cell(table, r, c_100))
                sgt = leading_int(cell(table, r, c_gt))
                academic = category == "学术学位"
                for name, code in _DISCIPLINE_RE.findall(cell(table, r, c_name)):
                    label = f"{name.strip()}[{code}]" + ("学硕" if academic else "")
                    facts.line(
                        "school_baseline",
                        None,
                        total,
                        (s100, s100, sgt, sgt),
                        evidence=row_text(table, r),
                        definition=f"学校{ctx.year}年复试基本分数线（{label}）",
                        discipline_code=code,
                        page=table.page,
                    )
        return facts
