from __future__ import annotations

from pathlib import Path
from typing import Any

from doc_agent.config import Settings, get_settings
from doc_agent.ingest.chunking import chunk_document
from doc_agent.ingest.loaders import iter_source_files, load_file
from doc_agent.rag.store import DocumentStore, get_store, reset_store


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
    all_chunks = []
    for f in files:
        try:
            doc = load_file(f)
            chunks = chunk_document(
                doc,
                chunk_size=s.chunk_size,
                overlap=s.chunk_overlap,
            )
            all_chunks.extend(chunks)
            docs_ok += 1
        except Exception as exc:  # noqa: BLE001
            docs_failed.append({"path": str(f), "error": str(exc)})

    added = store.upsert_chunks(all_chunks, reindex=False)
    return {
        "docs_indexed": docs_ok,
        "docs_failed": docs_failed,
        "chunks_added": added,
        "chunks_total": store.chunk_count,
        "collection": s.collection_name,
        "retrieval_backend": store.retrieval_backend,
        "files": [str(f) for f in files],
    }


def ingest_raw_dir(*, reindex: bool = False, settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    return ingest_paths([s.raw_path], reindex=reindex, settings=s)
