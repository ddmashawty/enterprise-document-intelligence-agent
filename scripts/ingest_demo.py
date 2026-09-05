#!/usr/bin/env python3
"""Ingest demo documents under data/raw into the local index."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_agent.ingest.pipeline import ingest_paths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--paths",
        nargs="*",
        default=["data/raw"],
        help="Files or directories to ingest",
    )
    parser.add_argument("--reindex", action="store_true")
    args = parser.parse_args()
    result = ingest_paths(args.paths, reindex=args.reindex)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["docs_indexed"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
