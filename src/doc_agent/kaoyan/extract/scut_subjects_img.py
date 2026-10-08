"""华南理工大学初试科目表格图片（学院调整招生专业通知 / 部分专业初试科目调整）.

Layout: 招生专业代码及名称 (merged over the subject rows, may list several programs) |
初试科目设置 (one subject per row) | 招生学院 (merged). Programs sharing a merged cell
share the subject list.
"""

from __future__ import annotations

import re

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.kaoyan.extract.base import (
    ExtractContext,
    Fact,
    FactSet,
    ProgramRef,
    cell,
    find_header,
    header_col,
)
from doc_agent.kaoyan.normalize import Subject, parse_subject

_CODE_RE = re.compile(r"(?<![0-9A-Z])((?:0[1-9]|1[0-4])\d{2}[0-9A-Z]{2})(?![0-9A-Z])")


class ScutSubjectsImage:
    name = "scut_subjects_img"

    def matches(self, ctx: ExtractContext) -> bool:
        return ctx.school_id == "scut" and ctx.doc_type == "subject_change" and str(ctx.format).startswith("img")

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        facts = FactSet(ctx, self.name)
        for table in doc.tables:
            h = find_header(table, "初试科目")
            if h is None:
                continue
            c_prog = header_col(table, h, "专业代码")
            c_subj = header_col(table, h, "初试科目")
            c_college = header_col(table, h, "学院")
            if c_prog is None or c_subj is None:
                continue
            assert table.origins is not None
            groups: dict[tuple[int, int], tuple[str, str, list[Subject]]] = {}
            for r in range(h + 1, table.n_rows):
                subject = parse_subject(cell(table, r, c_subj))
                if subject is None:
                    continue
                key = table.origins[r][c_prog]
                programs, college, subjects = groups.setdefault(
                    key, (cell(table, r, c_prog), cell(table, r, c_college) or (ctx.college_ref or ""), [])
                )
                if subject not in subjects:
                    subjects.append(subject)
            for programs, college, subjects in groups.values():
                evidence = f"{college} {programs}：{'、'.join(f'{s.code}{s.name}' for s in subjects)}"
                for code in dict.fromkeys(_CODE_RE.findall(programs)):
                    facts.subjects(ProgramRef(college or None, code), subjects, evidence=evidence)
        return facts
