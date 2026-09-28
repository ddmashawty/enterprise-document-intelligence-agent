from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from openai import OpenAI

from doc_agent.config import Settings, get_settings


@dataclass
class Hit:
    chunk_id: str
    source: str
    page: int
    doc_name: str
    text: str
    score: float
    backend: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["metadata"]:
            data.pop("metadata")
        return data


class RemoteEmbeddings:
    def __init__(self, settings: Settings):
        if not settings.embedding_enabled:
            raise RuntimeError("Remote embedding is not configured")
        self.model = settings.embedding_model
        self.batch_size = max(1, int(settings.embedding_batch_size))
        self.client = OpenAI(
            api_key=settings.resolved_embedding_api_key,
            base_url=settings.embedding_base_url.rstrip("/"),
            timeout=settings.request_timeout,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # Keep batches modest for local Ollama throughput/stability.
        batch_size = self.batch_size
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = self.client.embeddings.create(model=self.model, input=batch)
            ordered = sorted(resp.data, key=lambda x: x.index)
            vectors.extend([list(item.embedding) for item in ordered])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def get_remote_embeddings(settings: Settings | None = None) -> RemoteEmbeddings | None:
    s = settings or get_settings()
    if not s.embedding_enabled:
        return None
    return RemoteEmbeddings(s)
