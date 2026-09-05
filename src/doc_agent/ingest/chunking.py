from __future__ import annotations

from dataclasses import dataclass

from doc_agent.ingest.loaders import DocumentPage, LoadedDocument


@dataclass
class TextChunk:
    chunk_id: str
    source: str
    page: int
    text: str
    doc_name: str


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


def chunk_document(
    doc: LoadedDocument,
    *,
    chunk_size: int,
    overlap: int,
) -> list[TextChunk]:
    from pathlib import Path

    doc_name = Path(doc.source).name
    out: list[TextChunk] = []
    counter = 0
    for page in doc.pages:
        parts = _split_text(page.text, chunk_size, overlap)
        for part in parts:
            counter += 1
            out.append(
                TextChunk(
                    chunk_id=f"{doc_name}::p{page.page}::c{counter}",
                    source=doc.source,
                    page=page.page,
                    text=part,
                    doc_name=doc_name,
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
