from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from doc_agent.config import get_settings
from doc_agent.rag.store import get_store


def _split_names(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.replace("；", ",").replace(";", ",").split(",")]
    return [p for p in parts if p]


@tool
def compare_docs(query: str, doc_names: str, aspects: str = "", top_k: int = 4) -> str:
    """Compare multiple ingested documents on a query/aspects.

    doc_names: comma-separated exact file names (from list_documents).
    aspects: optional comma-separated focus points (e.g. 营收,净利润,风险).
    Returns grounded snippets grouped by document for downstream summarization/export.
    """
    names = _split_names(doc_names)
    if len(names) < 2:
        return "compare_docs 至少需要两个文档名（逗号分隔）。可先 list_documents。"

    aspect_list = _split_names(aspects) if aspects.strip() else []
    queries = [query.strip()] if query.strip() else []
    queries.extend(aspect_list)
    if not queries:
        queries = ["关键业务与财务要点"]

    store = get_store()
    available = {d.get("doc_name") for d in store.list_documents()}
    per_doc: dict[str, list[dict[str, Any]]] = {}
    missing: list[str] = []

    for name in names:
        resolved = name
        if available and name not in available:
            hit = next((a for a in available if a and (name in str(a) or str(a) in name)), None)
            if not hit:
                # alias: 手册 / 制度 / 茅台
                aliases = {
                    "手册": ("手册", "参数"),
                    "参数手册": ("手册", "参数"),
                    "制度": ("制度", "管理"),
                    "管理制度": ("制度", "管理"),
                }
                for key, needles in aliases.items():
                    if key in name:
                        hit = next(
                            (a for a in available if a and any(n in str(a) for n in needles)),
                            None,
                        )
                        if hit:
                            break
            if hit:
                resolved = str(hit)
            else:
                missing.append(name)
                continue
        name = resolved
        snippets: list[dict[str, Any]] = []
        seen: set[str] = set()
        for q in queries:
            hits = store.search(q, top_k=top_k, doc_name=name)
            for h in hits:
                key = f"{h.doc_name}:{h.page}:{h.text[:80]}"
                if key in seen:
                    continue
                seen.add(key)
                item = h.to_dict()
                item["matched_query"] = q
                snippets.append(item)
        per_doc[name] = snippets[: top_k * max(1, len(queries))]

    payload = {
        "query": query,
        "aspects": aspect_list,
        "documents": per_doc,
        "missing": missing,
        "note": "仅返回检索证据；请基于证据对比，勿编造缺失指标。",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def extract_fields(question: str, fields: str, citations_json: str = "") -> str:
    """Extract requested fields from citation snippets into a JSON object draft.

    fields: comma-separated field names.
    citations_json: optional JSON list of citation dicts; if empty, search with question.
    """
    field_list = _split_names(fields)
    if not field_list:
        return "fields 不能为空"

    citations: list[dict[str, Any]] = []
    if citations_json.strip():
        try:
            parsed = json.loads(citations_json)
            if isinstance(parsed, list):
                citations = parsed
        except json.JSONDecodeError:
            return "citations_json 不是合法 JSON"
    if not citations:
        hits = get_store().search(question, top_k=get_settings().top_k)
        citations = [h.to_dict() for h in hits]

    evidence = []
    for i, c in enumerate(citations[:10], start=1):
        evidence.append(
            {
                "i": i,
                "doc": c.get("doc_name") or c.get("source"),
                "page": c.get("page"),
                "text": (c.get("text") or "")[:400],
            }
        )

    draft = {
        "question": question,
        "fields": {f: {"value": None, "source": None, "note": "待模型依据 evidence 填写"} for f in field_list},
        "evidence": evidence,
        "instruction": "仅使用 evidence 填写 fields；无依据则 value=null 并说明依据不足。",
    }
    return json.dumps(draft, ensure_ascii=False, indent=2)
