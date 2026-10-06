#!/usr/bin/env python3
"""Evaluate rule extraction against the seed → docs/kaoyan_extraction_report.md (offline).

Builds a scratch DB (default data/kaoyan_eval.db, recreated each run), seeds it from
majors.csv + sources.json, runs every rule extractor on the local bundle documents
and compares each fact with the seed row of the same key.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_agent.config import get_settings  # noqa: E402
from doc_agent.kaoyan.db import KaoyanStore  # noqa: E402
from doc_agent.kaoyan.extract.evaluate import evaluate, render_markdown  # noqa: E402
from doc_agent.kaoyan.extract.run import run_extraction  # noqa: E402
from doc_agent.kaoyan.seed import seed_kaoyan  # noqa: E402


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/kaoyan_eval.db", help="Scratch SQLite path (recreated)")
    parser.add_argument("--out", default="docs/kaoyan_extraction_report.md", help="Markdown report path")
    args = parser.parse_args()

    db = settings.resolve(args.db)
    if db == settings.kaoyan_db_path.resolve():
        print("refusing to recreate the main kaoyan DB; pass a scratch --db", file=sys.stderr)
        return 2
    db.unlink(missing_ok=True)
    store = KaoyanStore(db)
    seed_kaoyan(store, settings.kaoyan_data_path)
    run = run_extraction(store, settings)
    report = evaluate(store, run, settings.kaoyan_data_path)

    out = settings.resolve(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(report), encoding="utf-8")
    for a in report.acceptance:
        print(f"{a.name}: {a.matched}/{a.seed} conflicts={a.conflicts} {'PASS' if a.passed else 'FAIL'}")
    print(f"seed {report.seed_total}, matched {report.matched_total}, conflicts {len(report.conflicts)}")
    print(f"report: {out}")
    return 0 if all(a.passed for a in report.acceptance) and not report.conflicts else 1


if __name__ == "__main__":
    raise SystemExit(main())
