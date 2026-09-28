from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from doc_agent.config import Settings, get_settings
from doc_agent.ingest.chunking import CHUNK_META_FIELDS, TextChunk
from doc_agent.rag.embeddings import Hit, get_remote_embeddings
from doc_agent.rag.query_expand import (
    expand_queries,
    infer_doc_name,
    infer_school,
    kaoyan_prior,
    keyword_boost,
)


def _tokenize(text: str) -> list[str]:
    """Whitespace/latin words + CJK unigrams/bigrams for Chinese BM25."""
    text = text.lower()
    tokens: list[str] = re.findall(r"[a-z0-9_]+", text)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.extend(cjk)
    tokens.extend(a + b for a, b in zip(cjk, cjk[1:]))
    return tokens


def _chunk_meta(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in CHUNK_META_FIELDS if row.get(k)}


def _normalize_filters(school: str | None, year: int | str | None, doc_type: str | None) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if school:
        from doc_agent.kaoyan.normalize import resolve_school

        filters["school"] = resolve_school(school) or school
    if year:
        filters["year"] = int(year)
    if doc_type:
        filters["doc_type"] = doc_type
    return filters


def _matches(meta: dict[str, Any], doc_name: str | None, filters: dict[str, Any]) -> bool:
    if doc_name and meta.get("doc_name") != doc_name:
        return False
    return all(meta.get(k) == v for k, v in filters.items())


class DocumentStore:
    """Phase-1 store: BM25 always; Chroma dense vectors when remote embedding configured.

    ``profile="kaoyan"`` points at the 考研 index (own chroma dir / collection) and
    switches query expansion to the 考研 rules.
    """

    def __init__(self, settings: Settings | None = None, profile: str = "enterprise"):
        self.profile = profile
        self.settings = (settings or get_settings()).for_profile(profile)
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
                    **c.metadata(),
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
                    **c.metadata(),
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
                    "meta": _chunk_meta(c),
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
                    **d["meta"],
                }
            )
        return sorted(out, key=lambda x: x["doc_name"])

    def search(
        self,
        query: str,
        top_k: int | None = None,
        doc_name: str | None = None,
        *,
        school: str | None = None,
        year: int | str | None = None,
        doc_type: str | None = None,
    ) -> list[Hit]:
        """Hybrid search. ``school`` / ``year`` / ``doc_type`` filter on chunk metadata;
        in the kaoyan profile a query naming exactly one school is pinned to it."""
        k = top_k or self.settings.top_k
        if not self._chunks:
            return []

        if self.profile == "enterprise":
            doc_filter = doc_name or infer_doc_name(
                query, [d["doc_name"] for d in self.list_documents()]
            )
        else:
            doc_filter = doc_name
            school = school or infer_school(query)
        filters = _normalize_filters(school, year, doc_type)
        queries = expand_queries(query, profile=self.profile)
        # name-list chunks repeat program codes on every row; a wider pool lets the
        # metadata priors below reach the documents that actually answer the query
        pool = max(k * 4, 20) if self.profile == "enterprise" else max(k * 8, 60)
        fused: dict[str, dict[str, Any]] = {}

        embedder = get_remote_embeddings(self.settings)
        for qi, q in enumerate(queries):
            # Prefer the original query slightly over expansions.
            w = 1.0 if qi == 0 else 0.9
            if embedder is not None:
                for rank, hit in enumerate(self._search_dense(q, pool, embedder, doc_filter, filters)):
                    self._rrf_add(fused, hit, w / (60 + rank + 1), backend="hybrid")
            for rank, hit in enumerate(self._search_bm25(q, pool, doc_filter, filters)):
                self._rrf_add(fused, hit, w / (60 + rank + 1), backend="hybrid")

        if not fused:
            return []

        for item in fused.values():
            item["score"] += keyword_boost(query, item["hit"].text, profile=self.profile)
            if self.profile == "kaoyan":
                item["score"] *= kaoyan_prior(query, item["hit"].metadata)

        ranked = sorted(fused.values(), key=lambda x: x["score"], reverse=True)[:k]
        out: list[Hit] = []
        for item in ranked:
            h: Hit = item["hit"]
            out.append(
                Hit(
                    chunk_id=h.chunk_id,
                    source=h.source,
                    page=h.page,
                    doc_name=h.doc_name,
                    text=h.text,
                    score=float(item["score"]),
                    backend=item.get("backend", h.backend),
                    metadata=h.metadata,
                )
            )
        return out

    @staticmethod
    def _rrf_add(
        fused: dict[str, dict[str, Any]],
        hit: Hit,
        score: float,
        *,
        backend: str,
    ) -> None:
        cur = fused.get(hit.chunk_id)
        if cur is None:
            fused[hit.chunk_id] = {"hit": hit, "score": score, "backend": backend}
        else:
            cur["score"] += score
            # Keep the higher-scoring payload text/page from whichever side contributed.
            if hit.score > cur["hit"].score:
                cur["hit"] = hit

    def _search_bm25(
        self,
        query: str,
        k: int,
        doc_name: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[Hit]:
        if not self._bm25:
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        hits: list[Hit] = []
        for idx, score in ranked:
            if score <= 0:
                continue
            c = self._chunks[idx]
            if not _matches(c, doc_name, filters or {}):
                continue
            hits.append(
                Hit(
                    chunk_id=c["chunk_id"],
                    source=c["source"],
                    page=c["page"],
                    doc_name=c["doc_name"],
                    text=c["text"],
                    score=float(score),
                    backend="bm25",
                    metadata=_chunk_meta(c),
                )
            )
            if len(hits) >= k:
                break
        return hits

    def _search_dense(
        self,
        query: str,
        k: int,
        embedder: Any,
        doc_name: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[Hit]:
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
        kwargs: dict[str, Any] = {
            "query_embeddings": [qvec],
            "n_results": min(k, max(collection.count(), 1)),
        }
        filters = filters or {}
        conditions = ([{"doc_name": doc_name}] if doc_name else []) + [{k: v} for k, v in filters.items()]
        if len(conditions) == 1:
            kwargs["where"] = conditions[0]
        elif conditions:
            kwargs["where"] = {"$and": conditions}
        try:
            result = collection.query(**kwargs)
        except Exception:  # noqa: BLE001
            # Fallback without metadata filter if chroma rejects the where clause.
            kwargs.pop("where", None)
            result = collection.query(**kwargs)
        hits: list[Hit] = []
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for i, chunk_id in enumerate(ids):
            meta = metas[i] or {}
            if not _matches(meta, doc_name, filters):
                continue
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
                    metadata=_chunk_meta(meta),
                )
            )
        return hits

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def retrieval_backend(self) -> str:
        if self.settings.embedding_enabled:
            return f"hybrid({self.settings.embedding_model}+bm25)"
        return "bm25"


_stores: dict[tuple[str, str, str], DocumentStore] = {}


def get_store(settings: Settings | None = None, profile: str = "enterprise") -> DocumentStore:
    """Cached store per (profile, chroma dir, collection); default is the enterprise index."""
    s = (settings or get_settings()).for_profile(profile)
    key = (profile, str(s.chroma_path), s.collection_name)
    if key not in _stores:
        _stores[key] = DocumentStore(settings or get_settings(), profile=profile)
    return _stores[key]


def reset_store(profile: str | None = None) -> None:
    for key in [k for k in _stores if profile is None or k[0] == profile]:
        del _stores[key]
