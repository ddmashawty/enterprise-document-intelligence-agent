"""暨南大学学院《推免生复试方案》PDF: 专业代码 | 专业名称 | 推免名额（"≤19"为上限）| ….

The table continues over pages without repeating the header. When the text says
several programs "属于一个一级学科" and they share one quota, that quota is the
一级学科 total (``pool_scope``), not a per-program number.
"""

from __future__ import annotations

from collections import defaultdict

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.kaoyan.extract.base import (
    ExtractContext,
    Fact,
    FactSet,
    ProgramRef,
    cell,
    find_header,
    header_col,
    row_text,
)
from doc_agent.kaoyan.normalize import CountValue, normalize_program_code, parse_count


class JnuTmPdf:
    name = "jnu_tm_pdf"

    def matches(self, ctx: ExtractContext) -> bool:
        return ctx.school_id == "jnu" and ctx.doc_type == "tm_policy" and str(ctx.format).startswith("pdf")

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        facts = FactSet(ctx, self.name)
        cols = (0, 2)
        rows: list[tuple[str, CountValue, str]] = []
        for table in doc.tables:
            h = find_header(table, "专业代码", "推免名额")
            if h is not None:
                cols = (header_col(table, h, "专业代码") or 0, header_col(table, h, "推免名额") or 2)
            for r in range((h + 1) if h is not None else 0, table.n_rows):
                code = normalize_program_code(cell(table, r, cols[0]))
                count = parse_count(cell(table, r, cols[1]))
                if code and not count.is_empty:
                    rows.append((code, count, row_text(table, r, limit=3)))

        pooled = self._pooled(rows, doc.text)
        for code, count, evidence in rows:
            pool = code[:4] if code[:4] in pooled else None
            definition = f"{ctx.year}推免生复试方案中的推免数（“≤N”为上限）"
            if pool:
                definition += f"；{pool}一级学科合计" + ("上限" if count.is_upper_bound else "")
            facts.plan(
                "tm",
                ProgramRef(ctx.college_ref, code),
                count.value,
                evidence=evidence,
                definition=definition,
                value_text=count.text,
                is_upper_bound=count.is_upper_bound,
                pool_scope=pool,
            )
        return facts

    @staticmethod
    def _pooled(rows: list[tuple[str, CountValue, str]], text: str) -> set[str]:
        if "一级学科" not in text:
            return set()
        groups: dict[str, set[int | None]] = defaultdict(set)
        sizes: dict[str, int] = defaultdict(int)
        for code, count, _ in rows:
            groups[code[:4]].add(count.value)
            sizes[code[:4]] += 1
        return {p for p, values in groups.items() if sizes[p] > 1 and len(values) == 1}
