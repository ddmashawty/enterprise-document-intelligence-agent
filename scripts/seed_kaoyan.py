#!/usr/bin/env python3
"""Seed data/kaoyan.db from data/kaoyan/majors.csv + sources.json (idempotent, offline)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_agent.config import get_settings  # noqa: E402
from doc_agent.kaoyan.db import KaoyanStore  # noqa: E402
from doc_agent.kaoyan.seed import seed_kaoyan  # noqa: E402


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(settings.kaoyan_db_path), help="SQLite path")
    parser.add_argument("--data-dir", default=str(settings.kaoyan_data_path), help="Seed bundle directory")
    args = parser.parse_args()

    store = KaoyanStore(settings.resolve(args.db))
    report = seed_kaoyan(store, settings.resolve(args.data_dir))
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    print(f"db: {store.db_path}")
    return 0 if report.programs > 0 and report.seed_only_documents == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
