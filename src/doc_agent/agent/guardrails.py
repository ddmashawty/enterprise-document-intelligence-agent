from __future__ import annotations

import json
import re
from typing import Any

from doc_agent.rag.store import get_store


EXPORT_HINTS = ("导出", "excel", "Excel", "xlsx", "markdown", "Markdown", "报告文件", "落盘")
COMPARE_HINTS = ("对比", "比较", "分别列出", "vs", "VS")
EXCEL_HINTS = ("excel", "xlsx", "Excel", "电子表格")


def wants_export(goal: str) -> bool:
    return any(k in goal for k in EXPORT_HINTS)


def wants_excel(goal: str) -> bool:
    g = goal.lower()
    return any(k.lower() in g for k in EXCEL_HINTS) or ("表格" in goal and "导出" in goal)


def wants_compare(goal: str) -> bool:
    return any(k in goal for k in COMPARE_HINTS)


def infer_export_filename(goal: str) -> str:
    m = re.search(r"文件名\s*[：:]?\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)", goal)
    if m:
        return m.group(1)
    if wants_excel(goal):
        return "export_table"
    return "export_report"


def tool_call_count(results: list[dict[str, Any]], name: str) -> int:
    return sum(1 for r in results if r.get("tool") == name)


def recent_tools(results: list[dict[str, Any]], n: int = 5) -> list[str]:
    return [str(r.get("tool") or "") for r in results[-n:]]


def is_list_documents_spin(results: list[dict[str, Any]]) -> bool:
    recent = recent_tools(results, 4)
    if len(recent) < 3:
        return False
    return all(t == "list_documents" for t in recent)


def resolve_compare_doc_names(goal: str) -> list[str]:
    """Map Chinese aliases in the goal to ingested doc_name values."""
    docs = get_store().list_documents()
    names = [str(d.get("doc_name") or "") for d in docs if d.get("doc_name")]
    if len(names) < 2:
        return names

    picked: list[str] = []

    def add_matching(*needles: str) -> None:
        for name in names:
            if name in picked:
                continue
            if any(n in name for n in needles):
                picked.append(name)

    # Explicit pairs commonly used in verification
    if "手册" in goal or "参数" in goal:
        add_matching("手册", "参数")
    if "制度" in goal or "管理" in goal or "保存" in goal or "保密" in goal:
        add_matching("制度", "管理")
    if "茅台" in goal:
        add_matching("茅台")
    if "五粮液" in goal:
        add_matching("五粮液")
    if "宁德" in goal:
        add_matching("宁德")
    if "人权" in goal:
        add_matching("人权", "OHCHR")

    # Fallback: first two non-annual + any mentioned
    if len(picked) < 2:
        for name in names:
            if name not in picked:
                picked.append(name)
            if len(picked) >= 2:
                break
    return picked[:4]


def citations_to_markdown(goal: str, citations: list[dict[str, Any]], title: str) -> str:
    lines = [f"# {title}", "", f"> 用户目标：{goal}", "", "## 依据摘录", ""]
    for i, c in enumerate(citations[:8], start=1):
        doc = c.get("doc_name") or c.get("source") or "unknown"
        page = c.get("page", "?")
        text = (c.get("text") or "").strip().replace("\n", " ")[:400]
        lines.append(f"{i}. **{doc}** p.{page}")
        lines.append(f"   {text}")
        lines.append("")
    lines.append("## 说明")
    lines.append("本文件由 Agent 根据检索证据自动导出；请以原文为准。")
    return "\n".join(lines)


def citations_to_excel_rows(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for c in citations[:30]:
        rows.append(
            {
                "文档": c.get("doc_name") or c.get("source") or "",
                "页码": c.get("page", ""),
                "摘录": (c.get("text") or "").strip().replace("\n", " ")[:500],
                "分数": c.get("score", ""),
            }
        )
    if not rows:
        rows = [{"文档": "", "页码": "", "摘录": "无可用摘录", "分数": ""}]
    return rows


def filter_redundant_tool_calls(
    tool_calls: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop repeated list_documents and duplicate identical calls in one turn."""
    out: list[dict[str, Any]] = []
    listed = tool_call_count(results, "list_documents") > 0
    seen: set[str] = set()
    for call in tool_calls:
        name = call.get("name") or ""
        args = call.get("args") or {}
        key = f"{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}"
        if key in seen:
            continue
        if name == "list_documents" and listed:
            continue
        if name == "list_documents":
            listed = True
        seen.add(key)
        out.append(call)
    return out
