from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from doc_agent.config import get_settings
from doc_agent.ingest.pipeline import load_document
from doc_agent.rag.store import get_store
from doc_agent.tools.compare import compare_docs, extract_fields
from doc_agent.tools.export import export_excel, export_markdown


@tool
def list_documents() -> str:
    """List documents already ingested into the local knowledge base."""
    docs = get_store().list_documents()
    if not docs:
        return "知识库为空，请先调用 ingest 导入文档。"
    return json.dumps(docs, ensure_ascii=False, indent=2)


@tool
def rag_search(query: str, top_k: int = 8, doc_name: str = "") -> str:
    """Search private documents and return relevant grounded snippets with citations.

    Optional doc_name pins search to one ingested file name (exact match), e.g.
    '600519_贵州茅台_贵州茅台2024年年度报告.pdf'.
    """
    hits = get_store().search(
        query,
        top_k=top_k,
        doc_name=doc_name or None,
    )
    if not hits:
        return "未检索到相关内容。请确认已 ingest，或换一种问法。"
    payload = [h.to_dict() for h in hits]
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def parse_document(path: str, max_chars: int = 6000) -> str:
    """Parse a local PDF, DOCX, TXT, Markdown, HTML, or spreadsheet file and return truncated plain text with page markers."""
    settings = get_settings()
    file_path = settings.resolve(path)
    if not file_path.exists():
        matches = list(settings.raw_path.rglob(Path(path).name))
        if not matches:
            return f"文件不存在: {path}"
        file_path = matches[0]
    try:
        doc = load_document(file_path, settings)
    except Exception as exc:  # noqa: BLE001
        return f"解析失败: {exc}"
    parts: list[str] = []
    total = 0
    for page in doc.pages:
        block = f"[page={page.page}]\n{page.text}"
        if total + len(block) > max_chars:
            remain = max_chars - total
            if remain > 0:
                parts.append(block[:remain] + "\n...[truncated]")
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts) if parts else "文档无可用文本"


@tool
def summarize_citations(question: str, citations_json: str) -> str:
    """Summarize already retrieved citation snippets for a question. Input citations as JSON list."""
    try:
        citations = json.loads(citations_json)
    except json.JSONDecodeError:
        return "citations_json 不是合法 JSON"
    if not isinstance(citations, list) or not citations:
        return "没有可汇总的引用片段"
    bullets = []
    for i, c in enumerate(citations[:8], start=1):
        doc = c.get("doc_name") or c.get("source") or "unknown"
        page = c.get("page", "?")
        text = (c.get("text") or "").strip().replace("\n", " ")
        bullets.append(f"{i}. ({doc} p.{page}) {text[:280]}")
    return (
        f"问题: {question}\n"
        f"可用证据片段:\n" + "\n".join(bullets) + "\n"
        "请仅基于以上证据作答，并标注引用来源。"
    )


def get_tool_list():
    return [
        list_documents,
        rag_search,
        parse_document,
        summarize_citations,
        compare_docs,
        extract_fields,
        export_markdown,
        export_excel,
    ]


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
