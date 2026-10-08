#!/usr/bin/env python3
"""Count rows per program code in a scanned admission list (OCR). Prints counts only.

    python scripts/roster_stats.py --doc scut-044 --pages 1-5

The file is local-only (personal data, >3MB); download it per raw/manifest.csv first.
Counts are school-wide rows per program code — print-only, not written to kaoyan.db,
because they mix colleges / joint programs and need a human to assign the 口径.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_agent.config import get_settings
from doc_agent.ingest.ocr import get_ocr_backend
from doc_agent.kaoyan.index import source_documents
from doc_agent.kaoyan.roster import roster_counts


def _pages(spec: str | None) -> list[int] | None:
    if not spec:
        return None
    out: list[int] = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", required=True, help="doc_id in kaoyan.db (e.g. scut-044)")
    parser.add_argument("--pages", help="e.g. 1-5,9 (default: all)")
    parser.add_argument("--ocr", default="rapidocr", choices=["rapidocr", "vision"])
    args = parser.parse_args()

    paths = [p for p, entry in source_documents(settings.kaoyan_data_path).items() if entry.get("doc_id") == args.doc]
    if not paths:
        print(f"no local file entry in sources.json: {args.doc}", file=sys.stderr)
        return 1
    path = paths[0]
    if not path.exists():
        print(f"local-only file missing: {path.name} (download per raw/manifest.csv)", file=sys.stderr)
        return 1
    result = roster_counts(path, get_ocr_backend(args.ocr, settings), _pages(args.pages))
    print(json.dumps({"doc_id": args.doc, **result.summary()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
