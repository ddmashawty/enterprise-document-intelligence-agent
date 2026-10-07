"""华南理工大学《复试初试成绩基本要求》表格图片: 学科门类 | 学科专业 | 总分 | 单科(=100) | 单科(>100).

Rows saying 各学科专业 / 其他学科专业 apply to the whole 门类 (discipline code "08");
rows naming programs ("1251 工商管理", "125603 …、125604 …") get one line per code.
"""

from __future__ import annotations

import re

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.kaoyan.extract.base import (
    ExtractContext,
    Fact,
    FactSet,
    cell,
    compact,
    find_header,
    header_col,
    leading_int,
    row_text,
)

_CATEGORY_RE = re.compile(r"^(\d{2})\s*(\S*)")
_PROGRAM_RE = re.compile(r"(\d{4}(?:\d{2})?)\s*([^\d、，,]+)")


class ScutBaselineImage:
    name = "scut_baseline_img"

    def matches(self, ctx: ExtractContext) -> bool:
        return ctx.school_id == "scut" and ctx.doc_type == "score_line" and str(ctx.format).startswith("img")

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        facts = FactSet(ctx, self.name)
        for table in doc.tables:
            h = find_header(table, "学科门类", "总分")
            if h is None:
                continue
            c_cat = header_col(table, h, "学科门类")
            c_name = header_col(table, h, "学科专业")
            c_total = header_col(table, h, "总分")
            c_100 = header_col(table, h, "满分=100")
            c_gt = header_col(table, h, "满分>100")
            for r in range(h + 1, table.n_rows):
                total = leading_int(cell(table, r, c_total))
                m = _CATEGORY_RE.match(compact(cell(table, r, c_cat)))
                if total is None or not m:
                    continue
                s100, sgt = leading_int(cell(table, r, c_100)), leading_int(cell(table, r, c_gt))
                name = cell(table, r, c_name)
                programs = _PROGRAM_RE.findall(name)
                targets = [(code, f"{code}{label.strip()}") for code, label in programs] or [
                    (m.group(1), f"{m.group(1)}{m.group(2)}{compact(name)}")
                ]
                for code, label in targets:
                    facts.line(
                        "school_baseline",
                        None,
                        total,
                        (s100, s100, sgt, sgt),
                        evidence=row_text(table, r),
                        definition=f"学校{ctx.year}年复试初试成绩基本要求（{label}）",
                        discipline_code=code,
                    )
        return facts
