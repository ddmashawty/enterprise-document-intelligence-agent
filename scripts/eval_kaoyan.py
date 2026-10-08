#!/usr/bin/env python3
"""Layered eval of the 考研 agent on data/gold/kaoyan_eval_v2.jsonl.

L0 (intent) needs nothing but the code. L1 (tools) needs a kaoyan DB; pass --db to
read another file, e.g. one built by seed_kaoyan.py + extract_kaoyan.py in CI.
Neither layer calls an LLM.

    python scripts/eval_kaoyan.py --layers L0,L1 --out docs/eval
    python scripts/eval_kaoyan.py --baseline docs/eval/baseline.json --max-drop 0.02
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

GOLD = ROOT / "data" / "gold" / "kaoyan_eval_v2.jsonl"


def _commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{sha}-dirty" if dirty else sha


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default=str(GOLD))
    parser.add_argument("--layers", default="L0,L1", help="comma list of L0, L1")
    parser.add_argument("--split", default="", help="comma list of splits; default all rows")
    parser.add_argument("--db", default="", help="kaoyan SQLite path for L1 (default: settings)")
    parser.add_argument("--out", default="", help="directory for <date>.md and <date>.json")
    parser.add_argument("--baseline", default="", help="report json to compare against")
    parser.add_argument("--max-drop", type=float, default=0.02)
    parser.add_argument("--write-baseline", default="", help="write summaries only, for later --baseline")
    args = parser.parse_args()

    if args.db:
        os.environ["KAOYAN_DB"] = str(Path(args.db).resolve())

    from doc_agent.config import get_settings
    from doc_agent.eval.runner import load_rows, regressions, render_markdown, run_l0, run_l1

    layers = [x.strip().upper() for x in args.layers.split(",") if x.strip()]
    splits = {x.strip() for x in args.split.split(",") if x.strip()}
    gold = Path(args.gold)
    rows = load_rows(gold, splits or None)

    report: dict = {
        "meta": {
            "date": dt.date.today().isoformat(),
            "commit": _commit(),
            "gold": gold.relative_to(ROOT).as_posix() if gold.is_relative_to(ROOT) else str(gold),
            "splits": sorted(splits),
            "rows": len(rows),
        },
        "layers": {},
    }
    if "L0" in layers:
        report["layers"]["L0"] = run_l0(rows)
    if "L1" in layers:
        db = get_settings().kaoyan_db_path
        if not db.exists():
            print(f"L1 needs a kaoyan DB; {db} not found (run seed_kaoyan.py and extract_kaoyan.py)",
                  file=sys.stderr)
            return 2
        report["layers"]["L1"] = run_l1(rows)

    for name, layer in report["layers"].items():
        print(name, json.dumps(layer["summary"], ensure_ascii=False))

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        stem = out / report["meta"]["date"]
        stem.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")
        stem.with_suffix(".md").write_text(render_markdown(report) + "\n", encoding="utf-8")
        print(f"wrote {stem}.md / .json")

    if args.write_baseline:
        summary = {**report, "layers": {k: {"summary": v["summary"]} for k, v in report["layers"].items()}}
        Path(args.write_baseline).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")
        print(f"wrote {args.write_baseline}")

    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        dropped = regressions(report, baseline, args.max_drop)
        if dropped:
            print("regression vs baseline:\n  " + "\n  ".join(dropped), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
