#!/usr/bin/env python3
"""Build the 考研 RAG index (data/chroma_kaoyan) from data/kaoyan/raw with sources.json metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_agent.config import get_settings  # noqa: E402
from doc_agent.kaoyan.index import ingest_kaoyan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="Files / dirs under the bundle (default: <KAOYAN_DATA_DIR>/raw)")
    parser.add_argument("--reindex", action="store_true", help="Drop the kaoyan index first")
    parser.add_argument("--no-embed", action="store_true", help="BM25 only, skip the embedding service")
    args = parser.parse_args()

    settings = get_settings()
    if args.no_embed:
        settings = settings.model_copy(update={"embedding_base_url": ""})
    report = ingest_kaoyan(settings, paths=args.paths or None, reindex=args.reindex)
    report["docs_needs_ocr"] = [Path(p).name for p in report["docs_needs_ocr"]]
    report["docs_unlisted"] = [Path(p).name for p in report["docs_unlisted"]]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["docs_indexed"] and not report["docs_failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
