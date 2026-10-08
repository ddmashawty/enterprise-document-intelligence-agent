#!/usr/bin/env python3
"""Extract structured facts from local bundle documents into data/kaoyan.db (idempotent).

Run scripts/seed_kaoyan.py first: facts only attach to programs already in the DB.
Rule extractors are offline; ``--llm`` adds the evidence-checked LLM fallback for
text documents no rule covers (needs LLM_API_KEY in .env).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_agent.config import get_settings  # noqa: E402
from doc_agent.kaoyan.db import KaoyanStore  # noqa: E402
from doc_agent.kaoyan.extract.run import run_extraction  # noqa: E402


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(settings.kaoyan_db_path), help="SQLite path")
    parser.add_argument("--docs", nargs="*", help="Only these doc_ids (default: all local documents)")
    parser.add_argument("--llm", action="store_true", help="LLM fallback for uncovered text documents")
    parser.add_argument("--dry-run", action="store_true", help="Compare with the seed without writing")
    parser.add_argument("--verbose", action="store_true", help="Include per-document status")
    parser.add_argument("--ocr", choices=["none", "rapidocr", "vision"],
                        help="OCR backend for image / scanned documents (default: OCR_BACKEND)")
    args = parser.parse_args()
    if args.ocr:
        settings = settings.model_copy(update={"ocr_backend": args.ocr})

    store = KaoyanStore(settings.resolve(args.db))
    if store.count("programs") == 0:
        print("no programs in DB — run scripts/seed_kaoyan.py first", file=sys.stderr)
        return 1
    model = None
    if args.llm:
        from doc_agent.kaoyan.extract.llm_fallback import build_llm_model

        model = build_llm_model(settings)
    run = run_extraction(store, settings, doc_ids=args.docs, llm_model=model, write=not args.dry_run)
    summary = run.summary()
    if not args.verbose:
        summary.pop("docs", None)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"db: {store.db_path}{' (dry run)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
