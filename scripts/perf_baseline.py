#!/usr/bin/env python3
"""Performance baseline for ingest-free retrieval + health (no LLM required for search)."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_agent.config import get_settings  # noqa: E402
from doc_agent.rag.store import get_store  # noqa: E402


def _timed(fn, n: int = 5) -> list[float]:
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return samples


def main() -> int:
    store = get_store()
    settings = get_settings()
    if store.chunk_count == 0:
        print("index empty; run scripts/ingest_demo.py first", file=sys.stderr)
        return 2

    health_ms = _timed(lambda: (store.chunk_count, store.retrieval_backend), n=10)
    search_ms = _timed(
        lambda: store.search("TopK 默认值", top_k=settings.top_k),
        n=5,
    )
    report = {
        "chunks": store.chunk_count,
        "retrieval_backend": store.retrieval_backend,
        "health_probe_ms": {
            "p50": round(statistics.median(health_ms), 2),
            "mean": round(statistics.mean(health_ms), 2),
            "max": round(max(health_ms), 2),
        },
        "rag_search_topk_ms": {
            "p50": round(statistics.median(search_ms), 2),
            "mean": round(statistics.mean(search_ms), 2),
            "max": round(max(search_ms), 2),
        },
        "targets": {
            "rag_search_p50_ms": "< 1500 (local hybrid; depends on Ollama)",
            "note": "Full /v1/chat latency dominated by LLM; use smoke scripts for E2E.",
        },
    }
    out = ROOT / "docs" / "perf_baseline.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
