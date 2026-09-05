#!/usr/bin/env python3
"""Smoke-test chat against gold questions (requires LLM_API_KEY)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_agent.agent.graph import run_agent  # noqa: E402
from doc_agent.config import get_settings  # noqa: E402
from doc_agent.rag.store import get_store  # noqa: E402


def main() -> int:
    settings = get_settings()
    if not settings.llm_configured:
        print("LLM_API_KEY missing", file=sys.stderr)
        return 2
    store = get_store()
    if store.chunk_count == 0:
        print("index empty; run scripts/ingest_demo.py first", file=sys.stderr)
        return 2

    gold_path = ROOT / "data" / "gold" / "sample_qa.json"
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    items = gold.get("items") or []
    ok = 0
    for item in items:
        q = item["question"]
        expected = item.get("expected_answer", "")
        print(f"\nQ: {q}")
        result = run_agent(q)
        answer = result.get("answer", "")
        print(f"A: {answer[:500]}")
        # lightweight heuristic: check a few keywords from expected
        keys = [
            t
            for t in expected.replace("，", " ")
            .replace("、", " ")
            .replace("：", " ")
            .split()
            if len(t) >= 2
        ]
        # Also accept shorter numeric/duration anchors for Chinese answers in tables.
        for anchor in ("3年", "10年", "TopK", "500", "公开", "内部", "秘密", "机密"):
            if anchor in expected and anchor not in keys:
                keys.append(anchor)
        hit = sum(1 for k in keys if k in answer)
        passed = hit >= max(1, (len(keys) + 2) // 3)
        print(f"pass={passed} keyword_hits={hit}/{len(keys)}")
        ok += int(passed)
    print(f"\nsummary: {ok}/{len(items)} passed")
    return 0 if ok >= max(1, len(items) - 1) else 1


if __name__ == "__main__":
    raise SystemExit(main())
