from __future__ import annotations

import json
import re

import pytest

from doc_agent.kaoyan.db import KaoyanStore
from doc_agent.kaoyan.query import KaoyanQuery, baseline_discipline
from doc_agent.tools import kaoyan as ky
from doc_agent.tools.registry import get_tool_list

PII_RE = re.compile(r"[\u4e00-\u9fff]某|\d{15}|考生编号")


@pytest.fixture()
def q(kaoyan_store: KaoyanStore) -> KaoyanQuery:
    return KaoyanQuery(kaoyan_store)


@pytest.fixture()
def tools(kaoyan_store: KaoyanStore, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(ky, "get_kaoyan_store", lambda: kaoyan_store)
    return {t.name: t for t in ky.KAOYAN_TOOLS}


def _plan(kind: str, year: int, value: int, *, upper: bool = False, pool: str | None = None, doc: str = "d1") -> dict:
    return {
        "kind": kind, "label": kind, "year": year, "value": value, "value_text": ("≤" if upper else "") + str(value),
        "upper_bound": upper, "pool_scope": pool, "definition": kind, "source": {"doc_id": doc},
    }


# --- 统招 rule (pure) ------------------------------------------------------------


def test_public_plan_explicit_and_derived() -> None:
    est, reasons = KaoyanQuery.public_plan(
        [_plan("public_exam", 2026, 49, doc="rules"), _plan("catalog_total", 2026, 210, doc="cat"),
         _plan("tm", 2026, 165, doc="rules")]
    )
    assert reasons == []
    assert {(e["basis"], e["value"], e["lower_bound"]) for e in est} == {
        ("public_exam", 49, False), ("catalog_total-tm", 45, False)
    }
    derived = next(e for e in est if e["formula"])
    assert derived["formula"] == "210 − 165 = 45" and len(derived["sources"]) == 2
    # explicit plan wins over the derived value when judging a threshold
    assert [e["value"] for e in KaoyanQuery.public_plan_basis(est)] == [49]


def test_public_plan_upper_bound_gives_lower_bound_only() -> None:
    est, _ = KaoyanQuery.public_plan([_plan("catalog_total", 2027, 54), _plan("tm", 2027, 41, upper=True)])
    (e,) = est
    assert (e["value"], e["lower_bound"], e["text"]) == (13, True, "≥13")


def test_public_plan_pool_and_missing_are_reasons() -> None:
    est, reasons = KaoyanQuery.public_plan(
        [_plan("catalog_total", 2027, 24, pool="0812"), _plan("public_exam", 2026, 10, pool="0812")]
    )
    assert est == []
    assert any("0812" in r for r in reasons) and len(reasons) == 2
    assert KaoyanQuery.public_plan([])[1] == ["没有公开招考/统考计划，也没有目录人数与推免数"]


def test_public_plan_basis_uses_latest_year_only() -> None:
    est, _ = KaoyanQuery.public_plan(
        [_plan("public_exam", 2026, 51), _plan("catalog_total", 2027, 62, doc="c"), _plan("tm", 2027, 25, doc="c")]
    )
    assert [(e["year"], e["value"]) for e in KaoyanQuery.public_plan_basis(est)] == [(2027, 37)]


def test_baseline_discipline() -> None:
    assert baseline_discipline("085404") == "0854"
    assert baseline_discipline("081200") == "08"
    assert baseline_discipline("140500") == "14"


# --- queries over the seeded DB -----------------------------------------------------


def test_filter_408_fulltime_public_over_20(q: KaoyanQuery) -> None:
    r = q.search_programs(is_408=True, study_mode="全日制", min_public_plan=21)
    got = {p["program_id"] for p in r["programs"]}
    assert {"sysu-670-085404", "jnu-052-085412", "scnu-019-081200", "scnu-019-085404", "scnu-041-085405",
            "scnu-041-085410", "scut-ft-140500"} <= got
    assert "jnu-010-085404" not in got
    unknown = {p["program_id"]: p for p in r["unknown"]}
    assert "统一认证" in " ".join(unknown["scut-cs-085404"]["reasons"])
    assert {e["value"] for e in unknown["scut-cs-085404"]["public_plan"]} == {35, 21}
    assert "≥13" in " ".join(unknown["jnu-010-085404"]["reasons"])
    assert "统招13" not in json.dumps(r, ensure_ascii=False).replace(" ", "")
    assert r["public_plan_rule"]


def test_no_exam_program_is_excluded_from_408_filter(q: KaoyanQuery) -> None:
    r = q.search_programs(school="中大", code="083900", is_408=True)
    assert r["count"] == 0 and r["unknown"] == [] and r["excluded"] == 1


def test_college_alias_and_code_prefix(q: KaoyanQuery) -> None:
    (row,) = q.find_programs(school="华工", college="计算机学院", code="085404")
    assert row["id"] == "scut-cs-085404"
    assert {r["code"][:4] for r in q.find_programs(school="scnu", code="0854")} == {"0854"}
    assert q.find_programs(school="华师", code="0839") == []
    hits = q.search_programs(school="华师", name_kw="网络空间安全")
    assert [p["program_id"] for p in hits["programs"]] == ["scnu-019-085404"]


def test_score_lines_scopes(q: KaoyanQuery) -> None:
    r = q.get_score_lines(school="sysu", code="085404", college="670")
    (p,) = r["programs"]
    scopes = {ln["scope"]: ln for ln in p["lines"]}
    assert scopes["college"]["total"] == 379 and scopes["college"]["singles"] == "50/50/60/60"
    assert scopes["school_baseline"]["total"] == 300 and scopes["school_baseline"]["label"] == "学校基本线"
    assert "special_veteran" in scopes
    assert scopes["college"]["source"]["url"].startswith("https://cse.sysu.edu.cn/article/3475")
    no_special = q.get_score_lines(school="sysu", code="085404", college="670", include_special=False)
    assert all(not ln["scope"].startswith("special_") for ln in no_special["programs"][0]["lines"])


def test_scut_only_school_baseline(q: KaoyanQuery) -> None:
    (p,) = q.get_score_lines(school="华工", code="085404")["programs"]
    assert {(ln["scope"], ln["total"]) for ln in p["lines"]} == {("school_baseline", 305)}


def test_no_exam_has_no_score_line(q: KaoyanQuery) -> None:
    (p,) = q.get_score_lines(school="sysu", code="083900")["programs"]
    assert p["lines"] == [] and "推免" in p["unknown"]
    (s,) = q.get_exam_subjects(school="sysu", code="083900")["programs"]
    assert s["exam_subjects"][0]["status"] == "no_exam"


def test_score_lines_missing_year_is_unknown(q: KaoyanQuery) -> None:
    (p,) = q.get_score_lines(school="sysu", code="085404", college="670", year=2027)["programs"]
    assert p["lines"] == [] and "2027" in p["unknown"]


def test_exam_subjects_unknown_and_known(q: KaoyanQuery) -> None:
    (scut,) = q.get_exam_subjects(school="scut", code="085404")["programs"]
    (grp,) = scut["exam_subjects"]
    assert grp["status"] == "unknown" and "统一认证" in grp["unknown_reason"] and grp["is_408"] is None
    (ft,) = q.get_exam_subjects(school="scut", code="140500")["programs"]
    assert ft["exam_subjects"][0]["codes"] == "101/201/301/408"
    (edge,) = q.get_exam_subjects(school="sysu", code="085400")["programs"]
    assert edge["is_boundary"] and "884" in edge["exam_subjects"][0]["codes"]


def test_seed_and_rule_duplicates_are_merged(q: KaoyanQuery) -> None:
    plans = q.plans("sysu-670-085404")
    keys = [(p["kind"], p["year"], p["value"], p["source"]["doc_id"]) for p in plans]
    assert len(keys) == len(set(keys))


def test_compare_rows_085404(q: KaoyanQuery) -> None:
    r = q.compare(code="085404", fields=["score_lines", "plans", "subjects"], year=2026)
    rows = {(row["学校"], row["学院"]): row for row in r["rows"]}
    totals = sorted(str(row["复试线"]).split("（")[0] for row in rows.values())
    assert totals == ["305", "318", "335", "340", "348", "379"]
    scut = rows[("华南理工大学", "计算机科学与工程学院")]
    assert scut["线的口径"].startswith("学校基本线")
    assert scut["初试科目"] == "未取得" and "统一认证" in scut["备注"]
    for row in rows.values():
        assert row["来源URL"] and row["doc_id"] and row["年份"] == 2026


def test_document_meta_hides_content(q: KaoyanQuery) -> None:
    doc = q.document("jnu-005")
    assert doc["contains_personal_data"] is True and doc["content_available"] is False
    assert "local_path" not in doc and "sha256" not in doc
    assert q.document("nope") is None
    assert all(d["school"] == "scut" for d in q.list_sources(school="华工"))
    assert all(d["doc_type"] == "retest_rules" for d in q.list_sources(doc_type="retest_rules"))


# --- tool wrappers -----------------------------------------------------------------


def test_tools_registered() -> None:
    names = {t.name for t in get_tool_list()}
    assert ky.KAOYAN_TOOL_NAMES <= names


def test_tool_outputs_and_citations(tools: dict) -> None:
    out = tools["get_score_lines"].invoke({"school": "中大", "code": "085404", "college": "计算机学院"})
    cites = ky.citations_from_output("get_score_lines", out)
    assert cites and all(c["doc_id"] and c["doc_name"] and c["text"] for c in cites)
    assert any("379" in c["text"] and c["url"].startswith("https://cse.sysu.edu.cn") for c in cites)
    assert ky.citations_from_output("rag_search", out) == []


def test_search_tool_arguments(tools: dict) -> None:
    data = json.loads(tools["search_programs"].invoke({"is_408": True, "study_mode": "全日制", "min_public_plan": 21}))
    assert data["count"] >= 7 and data["unknown"]
    data = json.loads(tools["search_programs"].invoke({"school": "华师", "code": "0839"}))
    assert data["count"] == 0


def test_compare_tool_and_export_rows(tools: dict) -> None:
    out = tools["compare_programs"].invoke({"code": "085404", "fields": "score_lines,plans"})
    rows = ky.export_rows(out)
    assert len(rows) == 6
    for col in ("学校", "学院", "专业代码", "年份", "复试线", "线的口径", "计划", "计划口径", "来源URL", "doc_id", "备注"):
        assert col in rows[0]
    view = ky.llm_view("compare_programs", out)
    assert '"programs"' not in view and "evidence" not in view
    md = ky.rows_to_markdown("t", rows)
    assert md.count("\n|") >= 7


def test_compare_by_program_ids(tools: dict) -> None:
    data = json.loads(tools["compare_programs"].invoke({"program_ids": "sysu-670-085404, scnu-019-085404"}))
    assert [r["专业代码"] for r in data["rows"]] == ["085404", "085404"]


def test_document_tools(tools: dict) -> None:
    doc = json.loads(tools["get_document"].invoke({"doc_id": "sysu-078"}))
    assert doc["page_url"] == "https://cse.sysu.edu.cn/article/3475"
    assert ky.citations_from_output("get_document", json.dumps(doc))[0]["doc_id"] == "sysu-078"
    missing = json.loads(tools["get_document"].invoke({"doc_id": "x"}))
    assert missing["error"] == "document_not_found"
    listed = json.loads(tools["list_sources"].invoke({"school": "jnu", "year": 2027}))
    assert listed["count"] > 0 and all(d["intake_year"] == 2027 for d in listed["documents"])


def test_privacy_outputs_only_statistics(tools: dict) -> None:
    out = tools["search_programs"].invoke({"school": "华工", "college": "计算机学院"})
    data = json.loads(out)
    stats = {s["kind"]: s["value"] for p in data["programs"] if p["code"] == "085404" for s in p["admission_stats"]}
    assert stats.get("admit_count") == 36
    assert not PII_RE.search(out)
    assert not PII_RE.search(json.dumps(ky.citations_from_output("search_programs", out), ensure_ascii=False))
