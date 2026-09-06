#!/usr/bin/env python3
"""Phase-4 smoke: memory, export tools, reflect path (needs LLM + index)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_agent.agent.graph import run_agent  # noqa: E402
from doc_agent.config import get_settings  # noqa: E402
from doc_agent.memory import get_task_store  # noqa: E402
from doc_agent.rag.store import get_store  # noqa: E402
from doc_agent.tools.export import export_excel, export_markdown  # noqa: E402


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def main() -> int:
    settings = get_settings()
    fails = 0

    # Offline: export tools
    md = json.loads(
        export_markdown.invoke(
            {"title": "阶段4冒烟", "content": "| A | B |\n|---|---|\n| 1 | 2 |", "filename": "phase4_smoke"}
        )
    )
    fails += not _ok("export_markdown", Path(ROOT / md["path"]).exists(), md["path"])

    xlsx = json.loads(
        export_excel.invoke(
            {
                "title": "对比表",
                "rows_json": json.dumps(
                    [{"文档": "A", "营收": "1"}, {"文档": "B", "营收": "2"}],
                    ensure_ascii=False,
                ),
                "filename": "phase4_smoke",
            }
        )
    )
    fails += not _ok("export_excel", Path(ROOT / xlsx["path"]).exists(), xlsx["path"])

    if not settings.llm_configured:
        print("LLM_API_KEY missing — skip agent checks")
        return 1 if fails else 0
    if get_store().chunk_count == 0:
        print("index empty; run scripts/ingest_demo.py first")
        return 1

    sid = f"phase4-{uuid4().hex[:8]}"
    r1 = run_agent("演示产品手册里 TopK 默认是多少？", session_id=sid)
    fails += not _ok("chat+task_id", bool(r1.get("task_id")), r1.get("task_id", ""))
    fails += not _ok("answer mentions 5 or TopK", ("5" in r1.get("answer", "")) or ("TopK" in r1.get("answer", "")))

    task = get_task_store().get_task(r1["task_id"])
    fails += not _ok("sqlite task saved", task is not None and task.user_goal.startswith("演示产品"))

    r2 = run_agent(
        "把刚才关于 TopK 的结论导出为 Markdown 报告，文件名 phase4_topk",
        session_id=sid,
    )
    exports = r2.get("exports") or []
    # May or may not export depending on LLM; reflection path should still finish
    fails += not _ok("session follow-up status done", r2.get("status") == "done", r2.get("status", ""))
    if exports:
        _ok("export via agent", True, str(exports[0].get("path")))
    else:
        print("[WARN] agent did not call export_* (acceptable if answer notes 依据/路径); reflection=", r2.get("reflection"))

    hist = get_task_store().session_history(sid, limit=10)
    fails += not _ok("session turns persisted", len(hist) >= 2, f"turns={len(hist)}")

    print(f"\nphase4 smoke: {'OK' if fails == 0 else f'{fails} failure(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
