import json
from pathlib import Path

import pytest

from frontend.kaoyan_view import MISSING, fact_lines, program_rows, unknown_rows

ROOT = Path(__file__).resolve().parents[1]
SRC = {"doc_id": "sysu-078", "title": "计算机学院2026年硕士研究生复试录取实施细则",
       "url": "https://cse.sysu.edu.cn/article/3475", "attachment_url": None}
CATALOG_SRC = {"doc_id": "sysu-072", "title": "中山大学2026年硕士研究生招生学科专业目录",
               "url": None, "attachment_url": "https://graduate.sysu.edu.cn/zsw/catalog.pdf"}

SYSU = {
    "program_id": "sysu-670-085404", "school": "sysu", "school_name": "中山大学", "college": "计算机学院",
    "college_code": "670", "code": "085404", "name": "计算机技术", "degree_type": "专硕", "study_mode": "全日制",
    "plans": [{"kind": "catalog_total", "label": "招生目录拟招生人数（含推免）", "year": 2026, "value": 210,
               "value_text": "210", "pool_scope": None, "definition": "2026年招生专业目录拟招生人数（含推免）",
               "verified": True, "source": CATALOG_SRC}],
    "public_plan": [
        {"value": 49, "text": "49", "label": "公开招考/统招计划", "year": 2026, "formula": None, "sources": [SRC]},
        {"value": 45, "text": "45", "label": "目录拟招生人数 − 推免数（派生）", "year": 2026,
         "formula": "210 − 165 = 45", "sources": [CATALOG_SRC, SRC]},
    ],
    "public_plan_unknown": [],
    "score_lines": [
        {"scope": "special_veteran", "label": "退役大学生士兵专项复试线", "year": 2026, "total": 323, "singles": "",
         "definition": "退役大学生士兵专项计划复试线", "verified": True, "source": SRC},
        {"scope": "college", "label": "学院复试线", "year": 2026, "total": 379, "singles": "50/50/60/60",
         "definition": "学院公布的2026年复试分数线", "verified": True, "source": SRC},
    ],
    "exam_subjects": [{"year": 2026, "status": "known", "codes": "101/204/302/408", "is_408": True,
                       "subjects": [{"code": "101", "name": "思想政治理论"}, {"code": "408", "name": "计算机学科专业基础"}],
                       "verified": True, "source": CATALOG_SRC}],
    "admission_stats": [],
}

SCUT = {
    "program_id": "scut-cs-085404", "school": "scut", "school_name": "华南理工大学", "college": "计算机科学与工程学院",
    "college_code": None, "code": "085404", "name": "计算机技术", "degree_type": "专硕", "study_mode": "全日制",
    "plans": [], "public_plan": [], "public_plan_unknown": [],
    "score_lines": [{"scope": "school_baseline", "label": "学校基本线", "year": 2026, "total": 305,
                     "singles": "50/50/70/70", "verified": True, "source": None}],
    "exam_subjects": [{"year": 2026, "status": "unknown", "unknown_reason": "目录系统需统一认证，未取得",
                       "subjects": [], "codes": "", "is_408": None, "verified": True, "source": None}],
}


def test_program_row_keeps_year_scope_and_sources() -> None:
    (row,) = program_rows({"programs": [SYSU]})
    assert row["学院"] == "670 计算机学院" and row["专业"] == "085404 计算机技术"
    assert row["复试线"] == "379（50/50/60/60）" and row["复试线口径"] == "2026 学院复试线"
    assert row["初试科目"] == "101/204/302/408（2026）" and row["408"] == "是"
    assert row["统招"] == "49（2026 公开招考/统招计划）；210 − 165 = 45（2026 目录拟招生人数 − 推免数（派生））"
    assert row["目录计划（含推免）"] == "210（2026）"
    assert row["复试线来源"] == SRC["url"] and row["计划来源"] == SRC["url"]
    assert row["科目来源"] == CATALOG_SRC["attachment_url"]


def test_unknown_facts_are_not_filled() -> None:
    (row,) = program_rows({"programs": [SCUT]})
    assert row["初试科目"].startswith("未知：") and row["408"] == "未知"
    assert row["复试线口径"] == "2026 学校基本线"
    assert row["统招"] == MISSING and row["目录计划（含推免）"] == MISSING
    assert row["复试线来源"] is None


def test_pool_total_is_labelled() -> None:
    jnu = {**SCUT, "plans": [{"kind": "catalog_total", "year": 2027, "value_text": "24", "pool_scope": "0812"}]}
    (row,) = program_rows({"programs": [jnu]})
    assert row["目录计划（含推免）"] == "24（2027，0812 合计）"


def test_unknown_rows_and_fact_lines() -> None:
    rows = unknown_rows({"unknown": [{**SCUT, "reasons": ["推免为上限 ≤41，统招只能得出 ≥13"]}]})
    assert rows == [{"学校": "华南理工大学", "学院": "计算机科学与工程学院", "专业": "085404 计算机技术",
                     "原因": "推免为上限 ≤41，统招只能得出 ≥13"}]
    lines = fact_lines(SYSU)
    assert any("**学院复试线** 379（50/50/60/60）" in x and "(https://cse.sysu.edu.cn/article/3475)" in x for x in lines)
    assert all("已核对" in x for x in lines)
    assert any("101思想政治理论、408计算机学科专业基础" in x for x in lines)


def test_demo_questions_follow_gold_file() -> None:
    pytest.importorskip("streamlit")
    from frontend.app import DEMO_QUESTIONS

    gold = json.loads((ROOT / "data" / "gold" / "kaoyan_qa.json").read_text(encoding="utf-8"))
    assert DEMO_QUESTIONS == [case["question"] for case in gold["items"]]
