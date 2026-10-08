#!/usr/bin/env python3
"""Smoke-test the 考研 agent against data/gold/kaoyan_qa.json (requires LLM_API_KEY + data/kaoyan.db).

A case passes when every must_include appears in the answer, no must_not_include does, and the
answer carries citations (export cases must also produce an .xlsx). Acceptance: numeric cases
>= 90%, expect_unknown cases 100%, privacy cases 100%, every answer cited.

    PYTHONPATH=src python scripts/smoke_kaoyan.py [--ids 1,5,17] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_agent.agent.graph import run_agent  # noqa: E402
from doc_agent.config import get_settings  # noqa: E402
from doc_agent.tools.kaoyan import kaoyan_available  # noqa: E402

GOLD = ROOT / "data" / "gold" / "kaoyan_qa.json"


def _normalize(text: str) -> str:
    return (
        text.replace(" ", "")
        .replace("\u3000", "")
        .replace("，", ",")
        .replace("、", ",")
        .replace("：", ":")
    )


def group(item: dict) -> str:
    if item.get("expect_unknown"):
        return "unknown"
    return {"privacy": "privacy", "export": "export"}.get(item["category"], "numeric")


def check(item: dict, result: dict) -> dict:
    ans = _normalize(result.get("answer", ""))
    missing = [k for k in item.get("must_include") or [] if _normalize(k) not in ans]
    forbidden = [k for k in item.get("must_not_include") or [] if _normalize(k) in ans]
    cited = bool(result.get("citations"))
    if item["category"] == "export":
        xlsx = [e for e in result.get("exports") or [] if str(e.get("path", "")).endswith(".xlsx")]
        missing = [k for k in missing if k != "xlsx"] + ([] if xlsx else ["<xlsx export>"])
    validation = (result.get("facts") or {}).get("validation") or {}
    usage = result.get("usage") or {}
    return {
        "id": item["id"],
        "category": item["category"],
        "group": group(item),
        "passed": not missing and not forbidden and cited,
        "missing": missing,
        "forbidden": forbidden,
        "cited": cited,
        "tools": [t.get("tool") for t in result.get("trace") or []],
        "regenerated": bool(validation.get("regenerated")),
        "unsupported": validation.get("unsupported") or [],
        "stripped": validation.get("stripped") or [],
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "llm_calls_with_usage": int(usage.get("llm_calls_with_usage") or 0),
    }


def summarize(rows: list[dict]) -> dict:
    def rate(g: str) -> tuple[int, int]:
        sel = [r for r in rows if r["group"] == g]
        return sum(r["passed"] for r in sel), len(sel)

    out = {g: rate(g) for g in ("numeric", "unknown", "privacy", "export")}
    cited = sum(r["cited"] for r in rows)
    n_ok, n = out["numeric"]
    accepted = (
        (n == 0 or n_ok / n >= 0.9)
        and out["unknown"][0] == out["unknown"][1]
        and out["privacy"][0] == out["privacy"][1]
        and cited == len(rows)
    )
    return {
        **{k: f"{a}/{b}" for k, (a, b) in out.items()},
        "cited": f"{cited}/{len(rows)}",
        "accepted": accepted,
        "seconds": round(sum(r.get("seconds") or 0 for r in rows), 1),
        "prompt_tokens": sum(r.get("prompt_tokens") or 0 for r in rows),
        "completion_tokens": sum(r.get("completion_tokens") or 0 for r in rows),
        "total_tokens": sum(r.get("total_tokens") or 0 for r in rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ids", default="", help="comma-separated gold ids to run (default: all)")
    parser.add_argument("--json", default="", help="write per-case results to this file")
    args = parser.parse_args()

    if not get_settings().llm_configured:
        print("LLM_API_KEY missing", file=sys.stderr)
        return 2
    if not kaoyan_available():
        print("data/kaoyan.db missing or empty; run scripts/seed_kaoyan.py first", file=sys.stderr)
        return 2

    items = json.loads(GOLD.read_text(encoding="utf-8"))["items"]
    if args.ids:
        wanted = {int(x) for x in args.ids.split(",") if x.strip()}
        items = [it for it in items if it["id"] in wanted]

    rows = []
    for item in items:
        t0 = time.perf_counter()
        result = run_agent(item["question"], persist=False)
        row = check(item, result)
        row["seconds"] = round(time.perf_counter() - t0, 1)
        row["answer"] = result.get("answer", "")
        rows.append(row)
        print(f"\n[{item['id']}] {item['question']}")
        print(f"A: {row['answer'][:600]}")
        print(
            f"pass={row['passed']} group={row['group']} cited={row['cited']} tools={row['tools']} "
            f"missing={row['missing']} forbidden={row['forbidden']} regenerated={row['regenerated']} "
            f"stripped={row['stripped']} {row['seconds']}s tokens={row['total_tokens']}"
        )

    summary = summarize(rows)
    print(f"\nsummary: {json.dumps(summary, ensure_ascii=False)}")
    if args.json:
        Path(args.json).write_text(
            json.dumps({"summary": summary, "cases": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
