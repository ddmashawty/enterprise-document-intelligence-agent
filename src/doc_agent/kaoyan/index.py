"""考研 RAG index: bundle files → chunks carrying doc_id / school / year / doc_type."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from doc_agent.config import Settings, get_settings
from doc_agent.ingest.chunking import chunk_document
from doc_agent.ingest.loaders import iter_source_files
from doc_agent.ingest.pipeline import load_document
from doc_agent.kaoyan.privacy import is_within
from doc_agent.rag.store import get_store, reset_store


def source_documents(data_dir: Path) -> dict[Path, dict[str, Any]]:
    """Resolved local path → sources.json document entry."""
    sources = data_dir / "sources.json"
    if not sources.exists():
        return {}
    meta = json.loads(sources.read_text(encoding="utf-8"))
    return {
        (data_dir / d["local_path"]).resolve(): d
        for d in meta.get("documents") or []
        if d.get("local_path")
    }


def chunk_meta(entry: dict[str, Any]) -> dict[str, Any]:
    year = entry.get("intake_year")
    if not year and str(entry.get("publish_date") or "")[:4].isdigit():
        year = int(str(entry["publish_date"])[:4])
    return {
        "doc_id": entry.get("doc_id"),
        "school": entry.get("school"),
        "college": entry.get("college"),
        "year": int(year) if year else None,
        "doc_type": entry.get("doc_type"),
        "title": entry.get("title"),
        "url": entry.get("attachment_url") or entry.get("page_url"),
    }


def _school_from_path(path: Path, data_dir: Path) -> str | None:
    raw = data_dir / "raw"
    if not is_within(path, raw):
        return None
    parts = path.resolve().relative_to(raw.resolve()).parts
    return parts[0] if len(parts) > 1 else None


def ingest_kaoyan(
    settings: Settings | None = None,
    *,
    paths: list[str | Path] | None = None,
    reindex: bool = False,
) -> dict[str, Any]:
    """Index bundle files (default ``<kaoyan_data_dir>/raw``) into the kaoyan profile store.

    Personal-data files are redacted by ``load_document`` and their chunks carry
    ``redacted=True``; tables are chunked by rows with caption + header repeated.
    """
    s = settings or get_settings()
    store = get_store(s, profile="kaoyan")
    if reindex:
        store.clear()
        reset_store("kaoyan")
        store = get_store(s, profile="kaoyan")

    data_dir = s.kaoyan_data_path
    listed = source_documents(data_dir)
    targets = [s.resolve(p) for p in paths] if paths else [data_dir / "raw"]
    files: list[Path] = []
    for target in targets:
        files.extend(iter_source_files(target))

    missing = sorted(
        e["doc_id"]
        for p, e in listed.items()
        if not p.exists() and any(is_within(p, t) for t in targets)
    )
    docs_ok = 0
    docs_redacted = 0
    docs_failed: list[dict[str, str]] = []
    docs_needs_ocr: list[str] = []
    unlisted: list[str] = []
    all_chunks = []
    for f in files:
        entry = listed.get(f.resolve())
        if entry:
            meta = chunk_meta(entry)
        else:
            meta = {"school": _school_from_path(f, data_dir)}
            unlisted.append(str(f))
        try:
            doc = load_document(f, s)
            meta["redacted"] = bool(doc.meta.get("redacted"))
            chunks = chunk_document(
                doc,
                chunk_size=s.chunk_size,
                overlap=s.chunk_overlap,
                meta=meta,
                table_rows=True,
            )
        except Exception as exc:  # noqa: BLE001
            docs_failed.append({"path": str(f), "error": str(exc)})
            continue
        if doc.needs_ocr:
            docs_needs_ocr.append(str(f))
        if meta["redacted"]:
            docs_redacted += 1
        if chunks:
            all_chunks.extend(chunks)
            docs_ok += 1
        elif not doc.needs_ocr:
            docs_failed.append({"path": str(f), "error": "No extractable text"})

    added = store.upsert_chunks(all_chunks, reindex=False)
    return {
        "profile": "kaoyan",
        "docs_indexed": docs_ok,
        "docs_failed": docs_failed,
        "docs_needs_ocr": docs_needs_ocr,
        "docs_redacted": docs_redacted,
        "docs_missing": missing,
        "docs_unlisted": unlisted,
        "chunks_added": added,
        "chunks_total": store.chunk_count,
        "collection": store.settings.collection_name,
        "chroma_dir": str(store.settings.chroma_path),
        "retrieval_backend": store.retrieval_backend,
    }
