from __future__ import annotations

from doc_agent.agent.guardrails import wants_excel, wants_export


def test_wants_export_and_excel():
    assert wants_export("请导出 Markdown 报告")
    assert wants_excel("整理成表格并导出 Excel")
    assert not wants_excel("只要口头回答")
