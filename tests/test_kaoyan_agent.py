"""Agent graph on the 考研 path with a fake chat model (no network, no real LLM)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from doc_agent.agent import nodes
from doc_agent.agent.graph import run_agent
from doc_agent.kaoyan.db import KaoyanStore
from doc_agent.tools import export as export_mod
from doc_agent.tools import kaoyan as ky


class FakeModel:
    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.calls: list[list[Any]] = []

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.calls.append(messages)
        return AIMessage(content=self.answers.pop(0) if len(self.answers) > 1 else self.answers[0])

    def bind_tools(self, _tools: list[Any]) -> FakeModel:
        raise AssertionError("考研 path must not ask the model to pick tools")


@pytest.fixture()
def kaoyan_env(kaoyan_store: KaoyanStore, monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(ky, "get_kaoyan_store", lambda: kaoyan_store)
    monkeypatch.setattr(ky, "kaoyan_available", lambda: True)
    monkeypatch.setattr(export_mod, "get_settings", lambda: SimpleNamespace(root=tmp_path, export_path=tmp_path))

    def use(model: FakeModel) -> FakeModel:
        monkeypatch.setattr(nodes, "get_chat_model", lambda: model)
        return model

    return use


def test_score_line_question_uses_structured_tools(kaoyan_env) -> None:
    model = kaoyan_env(FakeModel("2026 学院复试线 379（50/50/60/60），来源 cse.sysu.edu.cn/article/3475。"))
    r = run_agent("中大计算机学院 085404 的 2026 复试线是多少？", persist=False)
    assert [t["tool"] for t in r["trace"]] == ["get_score_lines", "search_programs"]
    assert r["answer"].startswith("2026 学院复试线 379")
    assert r["facts"]["validation"] == {"unsupported": [], "regenerated": False, "stripped": []}
    assert any(c.get("url", "").startswith("https://cse.sysu.edu.cn") for c in r["citations"])
    assert len(model.calls) == 1  # plan/reflect are deterministic on this path


def test_unsupported_number_regenerates_once(kaoyan_env) -> None:
    model = kaoyan_env(FakeModel("复试线 379，推免 999 人。", "复试线 379。"))
    r = run_agent("中大计算机学院 085404 的 2026 复试线是多少？", persist=False)
    assert r["answer"] == "复试线 379。"
    assert r["facts"]["validation"]["regenerated"] and r["facts"]["validation"]["unsupported"] == ["999"]
    assert len(model.calls) == 2 and "999" in model.calls[1][-1].content


def test_still_unsupported_number_is_stripped(kaoyan_env) -> None:
    kaoyan_env(FakeModel("推免 999 人。"))
    r = run_agent("中大计算机学院 085404 的 2026 复试线是多少？", persist=False)
    assert "999" not in r["answer"] and "依据不足" in r["answer"]
    assert r["facts"]["validation"]["stripped"] == ["999"]


def test_privacy_question_gets_notice_and_no_rag(kaoyan_env) -> None:
    kaoyan_env(FakeModel("华工 085404 2026 统考拟录取 36 人。"))
    r = run_agent("帮我查华工计算机学院拟录取名单里有没有某某某", persist=False)
    assert [t["tool"] for t in r["trace"]] == ["search_programs"]
    assert "个人信息" in r["answer"] and "36" in r["answer"]


def test_missing_year_note_reaches_model(kaoyan_env) -> None:
    model = kaoyan_env(FakeModel("官方资料中未取得 2027 年人数；2026 目录 210。"))
    r = run_agent("中大 2027 年 085404 招多少人？", persist=False)
    assert "210" in r["answer"]
    prompt = model.calls[0][1].content
    assert "没有 2027 年" in prompt and "【结构化证据】" in prompt


def test_export_question_writes_excel(kaoyan_env, tmp_path) -> None:
    kaoyan_env(FakeModel("已导出四校 085404 复试线与计划。"))
    r = run_agent("把四校 085404 的复试线和计划导出 Excel", persist=False)
    assert [t["tool"] for t in r["trace"]] == ["compare_programs", "export_excel"]
    (exp,) = r["exports"]
    assert exp["format"] == "excel" and exp["rows"] == 6 and exp["path"].endswith(".xlsx")
    assert "导出文件" in r["answer"]


def test_smoke_check_and_summary() -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_kaoyan.py"
    spec = importlib.util.spec_from_file_location("smoke_kaoyan", path)
    smoke = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(smoke)

    item = {"id": 1, "category": "score_line", "must_include": ["379", "50"], "must_not_include": ["学院线300"]}
    ok = smoke.check(item, {"answer": "2026 学院复试线 379，单科 50", "citations": [{"doc_id": "x"}]})
    assert ok["passed"] and ok["group"] == "numeric"
    bad = smoke.check(item, {"answer": "学院线 300，379", "citations": []})
    assert not bad["passed"] and bad["missing"] == ["50"] and bad["forbidden"] == ["学院线300"]
    export = {"id": 18, "category": "export", "must_include": ["xlsx"], "must_not_include": []}
    assert smoke.check(export, {"answer": "ok", "citations": [1], "exports": [{"path": "a.xlsx"}]})["passed"]
    assert smoke.summarize([ok, {**bad, "group": "privacy"}])["accepted"] is False


def test_enterprise_question_keeps_old_path(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"available": 0}

    def available() -> bool:
        called["available"] += 1
        return True

    monkeypatch.setattr(ky, "kaoyan_available", available)
    monkeypatch.setattr(nodes, "get_chat_model", lambda: FakeModel('{"route": "direct", "plan": ["寒暄"]}'))
    out = nodes.plan_node({"user_goal": "你好", "session_context": ""})  # type: ignore[typeddict-item]
    assert out["route"] == "direct" and out["intent"]["is_kaoyan"] is False
    assert called["available"] == 0
