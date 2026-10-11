from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from kaoyan.config import get_settings
from kaoyan.rag.store import get_store
from kaoyan.tools.export import export_excel, export_markdown
from kaoyan.tools.kaoyan import KAOYAN_TOOLS


@tool
def rag_search(
    query: str,
    top_k: int = 8,
    doc_name: str = "",
    school: str = "",
    year: int = 0,
    doc_type: str = "",
) -> str:
    """Search the official 考研 documents and return grounded snippets with citations.

    Optional filters: doc_name pins one indexed file (exact match); school (sysu / scut /
    jnu / scnu or 中大 / 华工 / 暨大 / 华师); year (intake year, e.g. 2027); doc_type
    (catalog, retest_rules, score_line, tm_catalog, notice, brochure, ...).
    """
    hits = get_store(get_settings()).search(
        query,
        top_k=top_k,
        doc_name=doc_name or None,
        school=school or None,
        year=year or None,
        doc_type=doc_type or None,
    )
    if not hits:
        return "未检索到相关内容。请确认已运行 scripts/ingest_kaoyan.py，或换一种问法。"
    payload = [h.to_dict() for h in hits]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def get_tool_list():
    return [rag_search, export_markdown, export_excel, *KAOYAN_TOOLS]


def tools_by_name() -> dict[str, Any]:
    return {t.name: t for t in get_tool_list()}


def parse_export_payload(tool_name: str, output: Any) -> dict[str, Any] | None:
    if tool_name not in {"export_markdown", "export_excel"}:
        return None
    try:
        data = json.loads(str(output))
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data.get("path"):
        return data
    return None
