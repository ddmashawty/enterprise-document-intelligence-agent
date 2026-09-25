from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

# pypdf may spam fontTools warnings on complex PDFs
logging.getLogger("pypdf").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*fontTools.*")


@dataclass
class DocumentPage:
    source: str
    page: int
    text: str


@dataclass
class LoadedDocument:
    source: str
    pages: list[DocumentPage]

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())


def _clean(text: str) -> str:
    lines = [ln.strip() for ln in text.replace("\x00", "").splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def load_txt(path: Path) -> LoadedDocument:
    text = _clean(path.read_text(encoding="utf-8", errors="ignore"))
    return LoadedDocument(
        source=str(path),
        pages=[DocumentPage(source=str(path), page=1, text=text)],
    )


def load_pdf(path: Path) -> LoadedDocument:
    reader = PdfReader(str(path))
    pages: list[DocumentPage] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            raw = ""
        text = _clean(raw)
        if text:
            pages.append(DocumentPage(source=str(path), page=i, text=text))
    if not pages:
        raise ValueError(f"No extractable text in PDF: {path}")
    return LoadedDocument(source=str(path), pages=pages)


def _page_break_before(paragraph: Paragraph) -> bool:
    p_pr = paragraph._p.pPr
    return p_pr is not None and p_pr.find(qn("w:pageBreakBefore")) is not None


def _split_paragraph(paragraph: Paragraph) -> list[str]:
    """Split paragraph text on explicit or last-rendered page breaks."""
    parts = [""]
    for el in paragraph._p.iter():
        if el.tag == qn("w:lastRenderedPageBreak"):
            parts.append("")
        elif el.tag == qn("w:br") and el.get(qn("w:type")) == "page":
            parts.append("")
        elif el.tag == qn("w:tab"):
            parts[-1] += "\t"
        elif el.tag == qn("w:t") and el.text:
            parts[-1] += el.text
    return parts


def _table_text(table: Table) -> str:
    rows: list[str] = []
    for row in table.rows:
        cells = [_clean(cell.text) for cell in row.cells]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def load_docx(path: Path) -> LoadedDocument:
    document = Document(str(path))
    buf: list[str] = []
    pages: list[DocumentPage] = []

    def flush() -> None:
        text = _clean("\n".join(buf))
        buf.clear()
        if text:
            pages.append(
                DocumentPage(source=str(path), page=len(pages) + 1, text=text)
            )

    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            paragraph = Paragraph(child, document)
            if _page_break_before(paragraph) and buf:
                flush()
            parts = _split_paragraph(paragraph)
            for i, part in enumerate(parts):
                if i > 0:
                    flush()
                cleaned = part.strip()
                if cleaned:
                    buf.append(cleaned)
        elif child.tag == qn("w:tbl"):
            rendered = _table_text(Table(child, document))
            if rendered:
                buf.append(rendered)
    flush()
    if not pages:
        raise ValueError(f"No extractable text in Word document: {path}")
    return LoadedDocument(source=str(path), pages=pages)


def load_file(path: Path) -> LoadedDocument:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path)
    if suffix == ".docx":
        return load_docx(path)
    if suffix == ".doc":
        raise ValueError(f"Legacy .doc is not supported, save as .docx: {path.name}")
    if suffix in {".txt", ".md"}:
        return load_txt(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


_SOURCE_SUFFIXES = {".pdf", ".txt", ".md", ".docx", ".doc"}


def iter_source_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in _SOURCE_SUFFIXES:
            files.append(path)
    # de-dupe while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for f in files:
        rp = f.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        out.append(f)
    return out
