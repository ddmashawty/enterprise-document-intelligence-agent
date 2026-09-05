from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from doc_agent.config import Settings, get_settings
from doc_agent.ingest.chunking import TextChunk
from doc_agent.rag.embeddings import Hit, get_remote_embeddings


def _tokenize(text: str) -> list[str]:
    """Whitespace/latin words + CJK unigrams/bigrams for Chinese BM25."""
    text = text.lower()
    tokens: list[str] = re.findall(r"[a-z0-9_]+", text)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.extend(cjk)
    tokens.extend(a + b for a, b in zip(cjk, cjk[1:]))
    return tokens


class DocumentStore:
    """Phase-1 store: BM25 always; Chroma dense vectors when remote embedding configured."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.meta_path = self.settings.chroma_path / "chunks.jsonl"
        self.bm25_path = self.settings.chroma_path / "bm25_corpus.json"
        self.settings.chroma_path.mkdir(parents=True, exist_ok=True)
        self._chunks: list[dict[str, Any]] = []
        self._bm25: BM25Okapi | None = None
        self._tokenized: list[list[str]] = []
        self._load()

    def _load(self) -> None:
        self._chunks = []
        if self.meta_path.exists():
            with self.meta_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._chunks.append(json.loads(line))
        self._rebuild_bm25()

    def _rebuild_bm25(self) -> None:
        self._tokenized = [_tokenize(c.get("text", "")) for c in self._chunks]
        self._bm25 = BM25Okapi(self._tokenized) if self._tokenized else None

    def clear(self) -> None:
        self._chunks = []
        if self.meta_path.exists():
            self.meta_path.unlink()
        if self.bm25_path.exists():
            self.bm25_path.unlink()
        # Remove persistent chroma files so dimension/model switches stay clean.
        for p in self.settings.chroma_path.glob("*"):
            if p.name in {"chunks.jsonl", "bm25_corpus.json"}:
                continue
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                import shutil

                shutil.rmtree(p, ignore_errors=True)
        self._rebuild_bm25()

    def upsert_chunks(self, chunks: list[TextChunk], *, reindex: bool = False) -> int:
        if reindex:
            self.clear()

        existing_ids = {c["chunk_id"] for c in self._chunks}
        new_chunks = [c for c in chunks if c.chunk_id not in existing_ids]
        if not new_chunks:
            return 0

        embedder = get_remote_embeddings(self.settings)
        vectors = None
        if embedder is not None:
            vectors = embedder.embed_documents([c.text for c in new_chunks])
            self._upsert_chroma(new_chunks, vectors)

        with self.meta_path.open("a", encoding="utf-8") as f:
            for c in new_chunks:
                row = {
                    "chunk_id": c.chunk_id,
                    "source": c.source,
                    "page": c.page,
                    "doc_name": c.doc_name,
                    "text": c.text,
                }
                self._chunks.append(row)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._rebuild_bm25()
        return len(new_chunks)

    def _upsert_chroma(self, chunks: list[TextChunk], vectors: list[list[float]]) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        client = chromadb.PersistentClient(
            path=str(self.settings.chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(
            name=self.settings.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        collection.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=vectors,
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "source": c.source,
                    "page": c.page,
                    "doc_name": c.doc_name,
                }
                for c in chunks
            ],
        )

    def list_documents(self) -> list[dict[str, Any]]:
        docs: dict[str, dict[str, Any]] = {}
        for c in self._chunks:
            name = c["doc_name"]
            if name not in docs:
                docs[name] = {
                    "doc_name": name,
                    "source": c["source"],
                    "chunks": 0,
                    "pages": set(),
                }
            docs[name]["chunks"] += 1
            docs[name]["pages"].add(c["page"])
        out = []
        for d in docs.values():
            out.append(
                {
                    "doc_name": d["doc_name"],
                    "source": d["source"],
                    "chunks": d["chunks"],
                    "pages": len(d["pages"]),
                }
            )
        return sorted(out, key=lambda x: x["doc_name"])

    def search(self, query: str, top_k: int | None = None) -> list[Hit]:
        k = top_k or self.settings.top_k
        if not self._chunks:
            return []

        embedder = get_remote_embeddings(self.settings)
        if embedder is not None:
            dense = self._search_dense(query, k, embedder)
            if dense:
                return dense
        return self._search_bm25(query, k)

    def _search_bm25(self, query: str, k: int) -> list[Hit]:
        if not self._bm25:
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:k]
        hits: list[Hit] = []
        for idx, score in ranked:
            if score <= 0:
                continue
            c = self._chunks[idx]
            hits.append(
                Hit(
                    chunk_id=c["chunk_id"],
                    source=c["source"],
                    page=c["page"],
                    doc_name=c["doc_name"],
                    text=c["text"],
                    score=float(score),
                    backend="bm25",
                )
            )
        return hits

    def _search_dense(self, query: str, k: int, embedder: Any) -> list[Hit]:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        client = chromadb.PersistentClient(
            path=str(self.settings.chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        try:
            collection = client.get_collection(self.settings.collection_name)
        except Exception:  # noqa: BLE001
            return []
        qvec = embedder.embed_query(query)
        result = collection.query(query_embeddings=[qvec], n_results=k)
        hits: list[Hit] = []
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for i, chunk_id in enumerate(ids):
            meta = metas[i] or {}
            dist = float(dists[i]) if i < len(dists) else 1.0
            hits.append(
                Hit(
                    chunk_id=chunk_id,
                    source=str(meta.get("source", "")),
                    page=int(meta.get("page", 0) or 0),
                    doc_name=str(meta.get("doc_name", "")),
                    text=docs[i] or "",
                    score=1.0 - dist,
                    backend="chroma",
                )
            )
        return hits

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def retrieval_backend(self) -> str:
        if self.settings.embedding_enabled:
            return f"chroma+{self.settings.embedding_model}"
        return "bm25"


_store: DocumentStore | None = None


def get_store(settings: Settings | None = None) -> DocumentStore:
    global _store
    if _store is None:
        _store = DocumentStore(settings)
    return _store


def reset_store() -> None:
    global _store
    _store = None
