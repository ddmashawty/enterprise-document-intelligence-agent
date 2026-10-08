from __future__ import annotations

from pathlib import Path
from typing import Any

from doc_agent.config import Settings, get_settings
from doc_agent.ingest.chunking import chunk_document
from doc_agent.ingest.loaders import ParsedDocument, iter_source_files, load_file
from doc_agent.ingest.ocr import NoOCR, get_ocr_backend
from doc_agent.ingest.redact import looks_personal, mask_notice_names, redact_document
from doc_agent.kaoyan.privacy import is_personal_file, is_within
from doc_agent.rag.store import get_store, reset_store


def load_document(path: Path, settings: Settings | None = None) -> ParsedDocument:
    """Load a file for indexing / tools, applying the privacy policy.

    Files under the kaoyan data dir get PDF tables extracted; files flagged
    ``contains_personal_data`` in sources.json, or with a name + exam-number table,
    are redacted (李某, id columns dropped) before anything downstream sees them.
    Other kaoyan notices still get "拟录取X等N人" lead names masked.
    """
    s = settings or get_settings()
    kaoyan_file = is_within(path, s.kaoyan_data_path)
    personal = kaoyan_file and is_personal_file(path, s.kaoyan_data_path)
    # Scanned rosters are only counted (kaoyan.roster), never OCR'd into the index.
    ocr = NoOCR() if personal else get_ocr_backend(s.ocr_backend, s)
    doc = load_file(path, tables=kaoyan_file, ocr=ocr)
    if personal or looks_personal(doc.tables):
        doc = redact_document(doc)
    elif kaoyan_file:
        doc = mask_notice_names(doc)
    return doc


def ingest_paths(
    paths: list[str | Path],
    *,
    reindex: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    s = settings or get_settings()
    store = get_store(s)
    if reindex:
        store.clear()
        reset_store()
        store = get_store(s)

    files: list[Path] = []
    for p in paths:
        files.extend(iter_source_files(s.resolve(p)))

    docs_ok = 0
    docs_failed: list[dict[str, str]] = []
    docs_needs_ocr: list[str] = []
    docs_redacted = 0
    all_chunks = []
    for f in files:
        try:
            doc = load_document(f, s)
            chunks = chunk_document(
                doc,
                chunk_size=s.chunk_size,
                overlap=s.chunk_overlap,
            )
        except Exception as exc:  # noqa: BLE001
            docs_failed.append({"path": str(f), "error": str(exc)})
            continue
        if doc.needs_ocr:
            docs_needs_ocr.append(str(f))
        if doc.meta.get("redacted"):
            docs_redacted += 1
        if chunks:
            all_chunks.extend(chunks)
            docs_ok += 1
        elif not doc.needs_ocr:
            docs_failed.append({"path": str(f), "error": "No extractable text"})

    added = store.upsert_chunks(all_chunks, reindex=False)
    return {
        "docs_indexed": docs_ok,
        "docs_failed": docs_failed,
        "docs_needs_ocr": docs_needs_ocr,
        "docs_redacted": docs_redacted,
        "chunks_added": added,
        "chunks_total": store.chunk_count,
        "collection": s.collection_name,
        "retrieval_backend": store.retrieval_backend,
        "files": [str(f) for f in files],
    }


def ingest_raw_dir(*, reindex: bool = False, settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    return ingest_paths([s.raw_path], reindex=reindex, settings=s)
