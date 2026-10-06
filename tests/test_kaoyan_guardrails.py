from __future__ import annotations

import pytest

from doc_agent.agent.guardrails import (
    detect_kaoyan_intent,
    find_unsupported_numbers,
    strip_unsupported_numbers,
)

# --- intent ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "schools", "codes", "kinds"),
    [
        ("中大计算机学院 085404 的 2026 复试线是多少？", ["sysu"], ["085404"], {"score_line"}),
        ("中大网络空间安全学院 083900 考什么、复试线多少？", ["sysu"], ["083900"], {"score_line", "subjects"}),
        ("暨大智能科学与工程学院 0812Z3 统考招几个？", ["jnu"], ["0812Z3"], {"plan"}),
        ("对比四校 085404 的 2026 复试线", [], ["085404"], {"score_line", "compare"}),
        ("把四校 085404 的复试线和计划导出 Excel", [], ["085404"], {"compare", "export"}),
        ("华工 140500 智能科学与技术考 408 吗？复试线？", ["scut"], ["140500"], {"subjects", "score_line"}),
    ],
)
def test_detect_intent(question: str, schools: list[str], codes: list[str], kinds: set[str]) -> None:
    i = detect_kaoyan_intent(question)
    assert i["is_kaoyan"]
    assert i["schools"] == schools and i["codes"] == codes
    assert kinds <= set(i["kinds"])


def test_detect_college_year_and_numeric() -> None:
    i = detect_kaoyan_intent("中大计算机学院 085404 的 2026 复试线是多少？")
    assert i["colleges"] == ["计算机学院"] and i["year"] == 2026 and i["numeric"]
    i = detect_kaoyan_intent("中大 2027 年 085404 招多少人？")
    assert i["year"] == 2027 and "plan" in i["kinds"]


def test_detect_filters() -> None:
    i = detect_kaoyan_intent("哪些专业考 408、全日制、统招 > 20？")
    assert "filter" in i["kinds"]
    assert i["filters"] == {"is_408": True, "study_mode": "全日制", "min_public_plan": 21}
    assert detect_kaoyan_intent("哪些专业统招≥20")["filters"]["min_public_plan"] == 20
    assert detect_kaoyan_intent("哪些非全日制专业不考408")["filters"] == {"is_408": False, "study_mode": "非全日制"}


def test_detect_scope_and_name_keyword() -> None:
    i = detect_kaoyan_intent("华师有没有网络空间安全学硕（0839）？")
    assert i["prefixes"] == ["0839"] and i["name_kw"] == "网络空间安全" and i["codes"] == []


def test_detect_privacy() -> None:
    i = detect_kaoyan_intent("帮我查华工计算机学院拟录取名单里有没有某某某")
    assert i["privacy"] and "privacy" in i["kinds"] and i["name_kw"] is None
    assert not detect_kaoyan_intent("华工计算机学院拟录取多少人")["privacy"]


@pytest.mark.parametrize("question", ["茅台和五粮液2024年营收对比", "公司差旅报销标准是什么", "导出茅台年报摘要为Excel"])
def test_enterprise_questions_are_not_kaoyan(question: str) -> None:
    assert not detect_kaoyan_intent(question)["is_kaoyan"]


def test_year_not_taken_as_discipline_prefix() -> None:
    i = detect_kaoyan_intent("2026 年 0854 电子信息复试线")
    assert i["prefixes"] == ["0854"] and i["year"] == 2026


# --- number validation ------------------------------------------------------------------

EVIDENCE = "2026 学院复试线 379 单科 50/50/60/60；目录 210 − 推免 165 = 45；发布 2026-03-17 https://cse.sysu.edu.cn/article/3475"


def test_supported_numbers_pass() -> None:
    answer = "2026 年 085404 学院复试线 379（50/50/60/60），目录 210 − 推免 165 = 45。发布于 2026年3月17日。"
    assert find_unsupported_numbers(answer, EVIDENCE) == []


def test_exempt_years_codes_urls_ordinals() -> None:
    answer = "1. 2027 年 0812Z3 与 085404：见 cse.sysu.edu.cn/article/3475 和 kaoyan_085404.xlsx\n2. 第9条"
    assert find_unsupported_numbers(answer, EVIDENCE) == []


def test_discipline_codes_exempt_but_plain_numbers_checked() -> None:
    assert find_unsupported_numbers("0812 一级学科统筹，0854 电子信息", EVIDENCE) == []
    assert find_unsupported_numbers("招 1200 人", EVIDENCE) == ["1200"]


def test_invented_numbers_are_flagged_and_stripped() -> None:
    answer = "复试线 379，推免 999 人，统招 12.5。"
    assert find_unsupported_numbers(answer, EVIDENCE) == ["999", "12.5"]
    fixed = strip_unsupported_numbers(answer, EVIDENCE)
    assert fixed == "复试线 379，推免 （依据不足） 人，统招 （依据不足）。"
    assert find_unsupported_numbers(fixed, EVIDENCE) == []


def test_number_forms_are_canonical() -> None:
    assert find_unsupported_numbers("比例 1:2", "复试比 1:2.00") == []
    assert find_unsupported_numbers("3 月", "2026-03-17") == []
