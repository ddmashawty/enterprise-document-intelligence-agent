"""Personal-data redaction before indexing.

Name columns are masked to surname + "某" (李某), exam / ID number columns are
dropped, and page text is re-rendered from the redacted tables. As a safety net,
every name seen in a name column is also masked wherever it appears in the text,
and 15-digit exam numbers / 18-digit ID numbers are removed.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Callable, Iterable

from doc_agent.ingest.loaders import DocumentPage, ParsedDocument
from doc_agent.ingest.tables import Table, render_page

NAME_HEADER = re.compile(r"^(?:考生)?姓\s*名$")
ID_HEADER = re.compile(r"考生编号|考试编号|准考证号?|身份证号?|证件号码?|报名号|学号")
_HEADER_ROWS = 6
_COMPOUND_SURNAMES = (
    "欧阳", "司马", "上官", "诸葛", "东方", "皇甫", "尉迟", "公孙", "慕容", "令狐",
    "长孙", "宇文", "司徒", "夏侯", "轩辕", "端木", "独孤", "南宫", "西门", "百里",
)
_EXAM_NO = re.compile(r"(?<!\d)\d{15}(?!\d)")
_ID_NO = re.compile(r"(?<!\d)\d{17}[\dXx](?![\dXx])")
# public notices name the first person on a list: 拟录取张三等2582人为硕士研究生
_LEAD_NAME = re.compile(r"(拟录取|拟接收|拟推荐|录取|接收|同意)([\u4e00-\u9fff]{2,4}?)(等\s*\d+\s*[名人位])")


def mask_name(name: str) -> str:
    raw = re.sub(r"\s+", "", name or "")
    if not raw:
        return ""
    for surname in _COMPOUND_SURNAMES:
        if raw.startswith(surname) and len(raw) > len(surname):
            return surname + "某"
    return raw[0] + "某"


def _norm_header(cell: str) -> str:
    return re.sub(r"[\s（(][^）)]*[）)]|\s+", "", cell or "")


def find_header(table: Table) -> tuple[int, list[int], list[int]] | None:
    """(header row, name columns, id columns) if the table has a personal-data header."""
    for r, row in enumerate(table.cells[:_HEADER_ROWS]):
        names = [c for c, cell in enumerate(row) if NAME_HEADER.match(_norm_header(cell))]
        ids = [c for c, cell in enumerate(row) if ID_HEADER.search(cell or "")]
        if names or ids:
            return r, names, ids
    return None


def is_personal_table(table: Table) -> bool:
    header = find_header(table)
    return bool(header and header[1] and header[2])


def looks_personal(tables: Iterable[Table]) -> bool:
    return any(is_personal_table(t) for t in tables)


def redact_tables(tables: list[Table]) -> tuple[list[Table], set[str]]:
    """Mask name columns and drop id columns.

    Tables without their own header (a list continued on the next PDF page) reuse
    the last header layout with the same column count.
    """
    out: list[Table] = []
    names: set[str] = set()
    layouts: dict[int, tuple[list[int], list[int]]] = {}
    for table in tables:
        header = find_header(table)
        if header:
            start, name_cols, id_cols = header[0] + 1, header[1], header[2]
            layouts[table.n_cols] = (name_cols, id_cols)
        elif table.n_cols in layouts:
            start = 0
            name_cols, id_cols = layouts[table.n_cols]
        else:
            out.append(table)
            continue
        cells = [list(row) for row in table.cells]
        for r in range(start, len(cells)):
            for c in name_cols:
                value = cells[r][c]
                if value and not NAME_HEADER.match(_norm_header(value)):
                    names.add(re.sub(r"\s+", "", value))
                    cells[r][c] = mask_name(value)
        out.append(replace(table, cells=cells).drop_columns(id_cols))
    return out, names


_ROLE_WORD = re.compile(r"考生|学生|推免生|研究生|新生|人员|同学|同志")


def mask_lead_names(text: str) -> str:
    def sub(m: re.Match[str]) -> str:
        if _ROLE_WORD.search(m.group(2)):
            return m.group(0)
        return m.group(1) + mask_name(m.group(2)) + m.group(3)

    return _LEAD_NAME.sub(sub, text)


def text_redactor(names: Iterable[str] = ()) -> Callable[[str], str]:
    """Build a redact function for one document (names compiled into one pattern)."""
    known = sorted({n for n in names if len(n) >= 2}, key=len, reverse=True)
    pattern = re.compile("|".join(map(re.escape, known))) if known else None

    def redact(text: str) -> str:
        if not text:
            return text
        if pattern is not None:
            text = pattern.sub(lambda m: mask_name(m.group(0)), text)
        text = mask_lead_names(text)
        text = _ID_NO.sub("", text)
        return _EXAM_NO.sub("", text)

    return redact


def redact_text(text: str, names: Iterable[str] = ()) -> str:
    return text_redactor(names)(text)


def mask_notice_names(doc: ParsedDocument) -> ParsedDocument:
    """Mask "拟录取X等N人" lead names in documents that are not redacted as a whole."""
    pages = [DocumentPage(source=p.source, page=p.page, text=mask_lead_names(p.text)) for p in doc.pages]
    if all(a.text == b.text for a, b in zip(pages, doc.pages)):
        return doc
    meta = dict(doc.meta)
    if meta.get("prose"):
        meta["prose"] = {p: mask_lead_names(v) for p, v in meta["prose"].items()}
    tables = [replace(t, cells=[[mask_lead_names(c) for c in row] for row in t.cells]) for t in doc.tables]
    return ParsedDocument(source=doc.source, pages=pages, tables=tables, images=list(doc.images), meta=meta)


def redact_document(doc: ParsedDocument) -> ParsedDocument:
    """New document with redacted tables and pages; ``meta["redacted"] = True``."""
    tables, names = redact_tables(doc.tables)
    redact = text_redactor(names)
    # cells are chunked directly later, so the text safety net runs on every cell too
    tables = [replace(t, cells=[[redact(cell) for cell in row] for row in t.cells]) for t in tables]
    prose = {p: redact(v) for p, v in (doc.meta.get("prose") or {}).items()}
    pages: list[DocumentPage] = []
    for page in doc.pages:
        if page.page in prose:
            text = render_page(prose[page.page], [t for t in tables if t.page == page.page])
        else:
            text = redact(page.text)
        if text.strip():
            pages.append(DocumentPage(source=page.source, page=page.page, text=text))
    meta = dict(doc.meta)
    meta["prose"] = prose
    meta["redacted"] = True
    return ParsedDocument(source=doc.source, pages=pages, tables=tables, images=list(doc.images), meta=meta)
