from __future__ import annotations

from doc_agent.agent.guardrails import (
    filter_redundant_tool_calls,
    is_list_documents_spin,
    wants_compare,
    wants_excel,
    wants_export,
)


def test_wants_export_and_excel():
    assert wants_export("请导出 Markdown 报告")
    assert wants_excel("整理成表格并导出 Excel")
    assert not wants_excel("只要口头回答")


def test_wants_compare():
    assert wants_compare("对比手册和制度")
    assert not wants_compare("TopK 是多少")


def test_filter_list_documents_once():
    results = [{"tool": "list_documents", "args": {}, "output": "[]"}]
    calls = [
        {"name": "list_documents", "args": {}},
        {"name": "rag_search", "args": {"query": "x"}},
        {"name": "list_documents", "args": {}},
    ]
    filtered = filter_redundant_tool_calls(calls, results)
    assert [c["name"] for c in filtered] == ["rag_search"]


def test_list_documents_spin():
    results = [{"tool": "list_documents"} for _ in range(4)]
    assert is_list_documents_spin(results)
    assert not is_list_documents_spin([{"tool": "rag_search"}, {"tool": "list_documents"}])
