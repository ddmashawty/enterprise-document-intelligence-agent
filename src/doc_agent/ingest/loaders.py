from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path

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


def load_file(path: Path) -> LoadedDocument:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path)
    if suffix in {".txt", ".md"}:
        return load_txt(path)
    raise ValueError(f"Unsupported file type for phase-1: {path.suffix}")


def iter_source_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files: list[Path] = []
    for pattern in ("**/*.pdf", "**/*.txt", "**/*.md"):
        files.extend(sorted(root.glob(pattern)))
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
