"""暨南大学《硕士研究生招生专业目录》HTML (one big table per year).

Rows: 学院行 "010信息科学技术学院 | 拟招生总人数： | 235 | 备注"; 专业行 "085404计算机技术(专业学位) | 54";
方向行 "01(全日制)不分方向 | 导师 | ①101… | 复试科目 | …". Programs under a 一级学科 counted as a
whole ("计算机科学与技术指标为24个，以上均按一级学科统筹") leave their own count empty; they get
the pooled count with ``pool_scope``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.kaoyan.extract.base import (
    FIRST_LEVEL_CODES,
    ExtractContext,
    Fact,
    FactSet,
    ProgramRef,
    row_text,
)
from doc_agent.kaoyan.normalize import clean, split_subjects

_COLLEGE_RE = re.compile(r"^(\d{3})(\D.*)$")
_PROGRAM_RE = re.compile(r"^(\d{4}[0-9A-Z]{2})(\D.*)$")
_DIRECTION_RE = re.compile(r"^([0-9A-Z]{2})[（(](全日制|非全日制)[）)](.*)$")
_POOL_RE = re.compile(r"([\u4e00-\u9fff]+?)指标为?(\d+)个")


@dataclass
class _Program:
    college: str
    code: str
    name: str
    count: int | None
    evidence: str
    # (code, name, study mode, exam subjects cell, raw first cell)
    directions: list[tuple[str, str, str, str, str]] = field(default_factory=list)


def pool_clauses(note: str) -> dict[str, tuple[int, str]]:
    """'计算机科学与技术指标为24个，以上均按一级学科统筹' → {'0812': (24, clause)}."""
    if "一级学科" not in note:
        return {}
    out: dict[str, tuple[int, str]] = {}
    for clause in re.split(r"[，,；;。]", note):
        m = _POOL_RE.search(clause)
        if m and (code := FIRST_LEVEL_CODES.get(m.group(1))):
            out[code] = (int(m.group(2)), clean(clause))
    return out


class JnuCatalogHtml:
    name = "jnu_catalog_html"

    def matches(self, ctx: ExtractContext) -> bool:
        return ctx.school_id == "jnu" and ctx.doc_type == "catalog" and ctx.format == "html"

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        facts = FactSet(ctx, self.name)
        for table in doc.tables:
            college: str | None = None
            pools: dict[str, tuple[int, str]] = {}
            program: _Program | None = None
            for r in range(table.n_rows):
                vals = table.row_values(r)
                if not vals:
                    continue
                first = vals[0]
                if (m := _COLLEGE_RE.match(first)) and len(vals) > 1 and "拟招生总人数" in vals[1]:
                    self._flush(program, pools, ctx, facts)
                    program = None
                    college = m.group(1)
                    pools = pool_clauses(" ".join(vals[3:]))
                elif college and (m := _PROGRAM_RE.match(first)):
                    self._flush(program, pools, ctx, facts)
                    count = int(vals[1]) if len(vals) > 1 and vals[1].isdigit() else None
                    name = re.sub(r"[（(]专业学位[）)]$", "", m.group(2)).strip()
                    program = _Program(college, m.group(1), name, count, row_text(table, r))
                elif program and (m := _DIRECTION_RE.match(first)):
                    subjects = next((v for v in vals[1:] if "①" in v), "")
                    program.directions.append((m.group(1), m.group(3).strip(), m.group(2), subjects, first))
            self._flush(program, pools, ctx, facts)
        return facts

    def _flush(
        self,
        program: _Program | None,
        pools: dict[str, tuple[int, str]],
        ctx: ExtractContext,
        facts: FactSet,
    ) -> None:
        if program is None:
            return
        modes = {d[2] for d in program.directions}
        mode = next(iter(modes)) if len(modes) == 1 else None
        ref = ProgramRef(program.college, program.code, mode)
        pool = program.code[:4]
        if program.count is not None:
            facts.plan(
                "catalog_total",
                ref,
                program.count,
                evidence=program.evidence,
                definition=f"{ctx.year}年招生专业目录拟招生人数（含推免）",
            )
        elif pool in pools:
            value, clause = pools[pool]
            facts.plan(
                "catalog_total",
                ref,
                value,
                evidence=f"{program.evidence} … {clause}",
                definition=f"{ctx.year}年招生专业目录{pool}一级学科合计（含推免，二级学科不单列）",
                value_text=clause,
                pool_scope=pool,
            )
        for d_mode in sorted(modes):
            texts = {d[3] for d in program.directions if d[2] == d_mode and d[3]}
            if len(texts) == 1:
                text = texts.pop()
                subjects = split_subjects(text)
                if subjects:
                    facts.subjects(ProgramRef(program.college, program.code, d_mode), subjects, evidence=text)
        for code, name, d_mode, _, raw in program.directions:
            facts.direction(ProgramRef(program.college, program.code, d_mode), code, name, evidence=raw)
