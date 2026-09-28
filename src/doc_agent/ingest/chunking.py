from __future__ import annotations

import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Mapping

from doc_agent.ingest.loaders import DocumentPage, LoadedDocument, ParsedDocument
from doc_agent.ingest.tables import Table

CHUNK_META_FIELDS = ("doc_id", "school", "college", "year", "doc_type", "title", "url", "redacted")

_MARKER_SPLIT = re.compile(r"\[\[TABLE:(\d+)\]\]")
_NUMERIC_CELL = re.compile(r"^[\d\s.,%()（）≤<=＜～~\-–—/:：]+$")
_LEADING_CODE = re.compile(r"^\d{3}")
_COLLEGE_ROW = re.compile(r"^\d{3}(?!\d)")
_PROGRAM_ROW = re.compile(r"^(?:\d{6}|\d{4}[A-Z]\d)")
_HEADER_SCAN_ROWS = 8
_MAX_HEADER_ROWS = 3


@dataclass
class TextChunk:
    chunk_id: str
    source: str
    page: int
    text: str
    doc_name: str
    doc_id: str | None = None
    school: str | None = None
    college: str | None = None
    year: int | None = None
    doc_type: str | None = None
    title: str | None = None
    url: str | None = None
    redacted: bool = False

    def metadata(self) -> dict[str, Any]:
        """Non-empty retrieval metadata (empty for enterprise chunks)."""
        return {k: v for k in CHUNK_META_FIELDS if (v := getattr(self, k))}


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


def _is_label_row(values: list[str]) -> bool:
    if len(set(values)) < 2:
        return False
    return not any(_NUMERIC_CELL.match(v) or _LEADING_CODE.match(v) for v in values)


def table_header_rows(table: Table) -> tuple[int, int]:
    """(first, end) row range of the column header, (0, 0) if none is found."""
    for r in range(min(_HEADER_SCAN_ROWS, table.n_rows)):
        if _is_label_row(table.row_values(r)):
            end = r + 1
            while end < min(r + _MAX_HEADER_ROWS, table.n_rows) and _is_label_row(table.row_values(end)):
                end += 1
            return r, end
    return 0, 0


def _table_blocks(table: Table, caption: list[str], chunk_size: int) -> list[str]:
    """Row-wise blocks; each repeats the caption, the header and the current college / program row."""
    h0, h1 = table_header_rows(table)
    header = [" | ".join(table.row_values(r)) for r in range(h0, h1)]
    header_set = set(header)
    prefix = [ln for ln in caption if ln] + header
    blocks: list[str] = []
    body: list[str] = []
    context: dict[str, str] = {}
    body_len = 0

    def flush() -> None:
        nonlocal body, body_len
        if body:
            blocks.append("\n".join(prefix + body))
        body, body_len = [], 0

    for r in range(table.n_rows):
        if h0 <= r < h1:
            continue
        values = table.row_values(r)
        if not values:
            continue
        line = " | ".join(values)
        if line in header_set:
            continue
        group = len(set(values)) <= max(2, table.n_cols // 2)
        if group and _COLLEGE_ROW.match(values[0]):
            flush()
            context = {"college": line}
        elif group and _PROGRAM_ROW.match(values[0]):
            if body_len + len(line) > chunk_size // 2:
                flush()
            context["program"] = line
        if body_len and len("\n".join(prefix)) + body_len + len(line) + 1 > chunk_size:
            flush()
        if not body:
            body = [v for v in context.values() if v != line]
            body_len = sum(len(v) + 1 for v in body)
        body.append(line)
        body_len += len(line) + 1
    flush()
    return blocks


_CAPTION_HINT = re.compile(r"[：:]$|如下|表|名单|分数线|计划|目录")


def _caption_line(text: str, limit: int = 60) -> str:
    """Last line before a table when it reads like a caption (…如下：, …名单)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines and len(lines[-1]) <= limit and _CAPTION_HINT.search(lines[-1]) and not re.search(r"\d{5,}", lines[-1]):
        return lines[-1]
    return ""


def _page_parts(doc: ParsedDocument, page: DocumentPage, *, chunk_size: int, overlap: int, title: str) -> list[str]:
    prose = (doc.meta.get("prose") or {}).get(page.page)
    tables = {t.index: t for t in doc.tables if t.page == page.page}
    if prose is None or not tables:
        return _split_text(page.text, chunk_size, overlap)
    parts: list[str] = []
    pieces = _MARKER_SPLIT.split(prose)
    for i, piece in enumerate(pieces):
        if i % 2 == 0:
            text = "\n".join(ln.strip() for ln in piece.splitlines() if ln.strip())
            parts.extend(_split_text(text, chunk_size, overlap))
            continue
        table = tables.pop(int(piece), None)
        if table is not None:
            caption = [title, table.title or _caption_line(pieces[i - 1])]
            parts.extend(_table_blocks(table, list(dict.fromkeys(caption)), chunk_size))
    for table in tables.values():
        parts.extend(_table_blocks(table, list(dict.fromkeys([title, table.title])), chunk_size))
    return parts


def chunk_document(
    doc: LoadedDocument,
    *,
    chunk_size: int,
    overlap: int,
    meta: Mapping[str, Any] | None = None,
    table_rows: bool = False,
) -> list[TextChunk]:
    """Split pages into chunks.

    ``meta`` (doc_id / school / year / ...) is copied onto every chunk and ``doc_id``
    becomes the chunk_id prefix. With ``table_rows`` tables are cut by rows and every
    block repeats the table caption and header.
    """
    doc_name = Path(doc.source).name
    extra = {f.name: (meta or {}).get(f.name) for f in fields(TextChunk) if f.name in CHUNK_META_FIELDS}
    extra = {k: v for k, v in extra.items() if v not in (None, "")}
    prefix = extra.get("doc_id") or doc_name
    by_rows = table_rows and isinstance(doc, ParsedDocument)
    out: list[TextChunk] = []
    counter = 0
    for page in doc.pages:
        if by_rows:
            parts = _page_parts(doc, page, chunk_size=chunk_size, overlap=overlap, title=str(extra.get("title") or ""))
        else:
            parts = _split_text(page.text, chunk_size, overlap)
        for part in parts:
            counter += 1
            out.append(
                TextChunk(
                    chunk_id=f"{prefix}::p{page.page}::c{counter}",
                    source=doc.source,
                    page=page.page,
                    text=part,
                    doc_name=doc_name,
                    **extra,
                )
            )
    return out


def chunk_pages(
    pages: list[DocumentPage],
    *,
    chunk_size: int,
    overlap: int,
) -> list[TextChunk]:
    doc = LoadedDocument(source=pages[0].source if pages else "", pages=pages)
    return chunk_document(doc, chunk_size=chunk_size, overlap=overlap)
