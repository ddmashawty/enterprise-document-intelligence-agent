import json
from pathlib import Path

from kaoyan.eval import runner
from kaoyan.eval.metrics import (
    contains,
    forbidden_items,
    intent_fields,
    match_fact,
    missing_items,
    normalize_text,
    tool_facts,
)

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "gold" / "kaoyan_eval_v2.jsonl"


def _program(lines=(), plans=()):
    return {"program_id": "jnu-010-081201", "lines": list(lines), "plans": list(plans)}


def _line(total, year=2026, scope="college", doc="jnu-003"):
    return {"scope": scope, "year": year, "total": total, "source": {"doc_id": doc}}


def _fact(value, table="score_lines", kind="college", year=2026, doc="jnu-003"):
    return {"table": table, "program_id": "jnu-010-081201", "kind": kind, "year": year, "value": value,
            "source_doc_id": doc}


def test_discipline_prefixes_count_as_codes_and_empty_metrics_are_not_scored():
    expected = {"operation": "lookup", "metrics": [], "schools": ["jnu"], "codes": ["0812"], "year": 2026}
    predicted = {"schools": ["jnu"], "codes": [], "prefixes": ["0812"], "year": 2026, "kinds": ["score_line"]}
    fields = intent_fields(expected, predicted, None)
    assert fields == {"schools": True, "codes": True, "year": True, "operation": True, "privacy": True}


def test_metrics_and_privacy_are_scored_when_gold_asks():
    expected = {"operation": "lookup", "metrics": ["plan"], "schools": [], "codes": [], "year": None}
    predicted = {"schools": [], "codes": [], "year": None, "kinds": ["score_line"], "privacy": False}
    fields = intent_fields(expected, predicted, "privacy")
    assert fields["metrics"] is False
    assert fields["privacy"] is False


def test_fact_match_needs_value_and_reports_source_separately():
    out = json.dumps({"programs": [_program(lines=[_line(264, doc="jnu-999")])]})
    facts = tool_facts([out, "not json"])
    assert match_fact(_fact(264), facts) == (True, False)
    assert match_fact(_fact(265), facts) == (False, False)
    assert match_fact(_fact(264, year=2025), facts) == (False, False)


def test_single_subject_lines_match_only_their_field():
    line = {**_line(305, scope="school_baseline"), "politics": 50, "foreign_lang": 50, "subject1": 70, "subject2": 70}
    facts = tool_facts([json.dumps({"programs": [_program(lines=[line])]})])
    politics = {**_fact(50, kind="school_baseline"), "field": "politics"}
    assert match_fact(politics, facts) == (True, True)
    assert match_fact({**politics, "field": "subject1"}, facts) == (False, False)
    assert match_fact(_fact(50, kind="school_baseline"), facts) == (False, False)
    assert match_fact(_fact(305, kind="school_baseline"), facts) == (True, True)


def test_tool_facts_reads_search_programs_fields():
    program = {
        "program_id": "scut-ft-140500",
        "score_lines": [_line(320, scope="school_baseline", doc="scut-040")],
        "admission_stats": [{"kind": "admit_count", "year": 2026, "value": 36, "source": {"doc_id": "scut-058"}}],
        "exam_subjects": [{"year": 2026, "subjects": [{"slot": 4, "code": "408"}], "source": {"doc_id": "scut-061"}}],
    }
    facts = tool_facts([json.dumps({"programs": [program]})])
    keys = {(f["table"], f["kind"], f["value"], f["source_doc_id"]) for f in facts}
    assert keys == {
        ("score_lines", "school_baseline", 320, "scut-040"),
        ("admission_stats", "admit_count", 36, "scut-058"),
        ("exam_subjects", "slot4", "408", "scut-061"),
    }


def test_l1_passes_fails_and_skips_compare_rows(monkeypatch):
    from kaoyan.agent import kaoyan_flow

    rows = [
        {"id": "ok", "turns": ["暨大 081201 2026 复试线"], "expected_facts": [_fact(264)],
         "expected_intent": {"operation": "lookup", "metrics": ["score_line"], "schools": ["jnu"],
                             "codes": ["081201"], "year": 2026}},
        {"id": "miss", "turns": ["暨大 081201 2026 复试线"], "expected_facts": [_fact(300)],
         "expected_intent": {"operation": "lookup", "metrics": ["score_line"], "schools": ["jnu"],
                             "codes": ["081201"], "year": 2026}},
        {"id": "cmp", "turns": ["对比四校 085404"], "expected_facts": [_fact(264)],
         "expected_intent": {"operation": "compare", "metrics": [], "schools": [], "codes": ["085404"],
                             "year": None}},
        {"id": "nofacts", "turns": ["华工名单"], "expected_facts": [],
         "expected_intent": {"operation": "lookup", "metrics": [], "schools": [], "codes": [], "year": None}},
    ]
    for row, split in zip(rows, ("dev", "adversarial", "dev", "dev"), strict=True):
        row["split"] = split
    rows[1]["trap"] = "pool"

    def fake_calls(intent):
        if "compare" in intent["kinds"]:
            return [("compare_programs", {"code": "085404"})]
        return [("get_score_lines", {"code": intent["codes"][0], "year": intent["year"]})]

    def fake_invoke(name, args):
        if name == "compare_programs":
            return json.dumps({"rows": [{"专业代码": "085404"}]})
        return json.dumps({"programs": [_program(lines=[_line(264)])]})

    monkeypatch.setattr(kaoyan_flow, "structured_calls", fake_calls)
    result = runner.run_l1(rows, invoke=fake_invoke)
    status = {r["id"]: r["status"] for r in result["rows"]}
    assert status == {"ok": "pass", "miss": "fail", "cmp": "unscorable"}
    assert result["summary"] == {"rows": 2, "unscorable": 1, "row_pass": 0.5, "fact_recall": 0.5,
                                 "source_match": 1.0}
    assert result["by_split"]["dev"]["row_pass"] == 1.0
    assert result["by_split"]["adversarial"]["row_pass"] == 0.0
    assert list(result["by_trap"]) == ["pool"]


def test_regressions_flag_drops_beyond_threshold():
    base = {"layers": {"L0": {"summary": {"rows": 10, "exact": 0.9, "codes": 1.0}}}}
    now = {"layers": {"L0": {"summary": {"rows": 10, "exact": 0.89, "codes": 0.95}}}}
    assert runner.regressions(now, base, 0.02) == ["L0.codes: 100.00% -> 95.00%"]


def test_regressions_check_each_trap():
    base = {"layers": {"L0": {"summary": {"exact": 0.8}, "by_trap": {"privacy": {"exact": 0.5}}}}}
    now = {"layers": {"L0": {"summary": {"exact": 0.8}, "by_trap": {"privacy": {"exact": 0.4}}}}}
    assert runner.regressions(now, base, 0.02) == ["L0[privacy].exact: 50.00% -> 40.00%"]


def test_test_split_is_skipped_by_default_and_reported_as_totals_only(tmp_path):
    gold = tmp_path / "gold.jsonl"
    rows = [
        {"id": "d", "split": "dev", "trap": "", "turns": ["中大 085400 2026 复试线"],
         "expected_intent": {"operation": "lookup", "metrics": ["score_line"], "schools": ["sysu"],
                             "codes": ["085400"], "year": 2026}},
        {"id": "t", "split": "test", "trap": "colloquial", "turns": ["华工今年招几个"],
         "expected_intent": {"operation": "lookup", "metrics": ["plan"], "schools": ["scnu"],
                             "codes": [], "year": None}},
    ]
    gold.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert [r["id"] for r in runner.load_rows(gold)] == ["d"]
    report = runner.run_l0(runner.load_rows(gold, {"dev", "test"}))
    assert report["summary"]["rows"] == 2
    assert report["by_split"]["test"]["rows"] == 1
    assert [r["id"] for r in report["rows"]] == ["d"]
    assert report["by_trap"] == {}


def _l0_report(fields_by_id):
    rows = [{"id": i, "fields": f, "exact": all(f.values())} for i, f in fields_by_id.items()]
    return {"layers": {"L0": {"rows": rows}}}


def test_known_failures_gate_new_and_fixed_parts_of_a_row():
    known = runner.known_failures(_l0_report({"a": {"codes": False, "year": False}, "b": {"codes": True}}))
    assert known == {"L0": {"a": ["codes", "year"]}}
    now = _l0_report({"a": {"codes": False, "year": True}, "b": {"codes": False}, "c": {"codes": True}})
    new, fixed = runner.failure_changes(now, known)
    assert new == ["L0 b: codes"]
    assert fixed == ["L0 a: year"]
    unscored = runner.failure_changes(_l0_report({"b": {"codes": True}}), known)
    assert unscored == ([], [])


def test_l0_runs_on_the_eval_set_without_a_database():
    report = runner.run_l0(runner.load_rows(GOLD))
    assert report["summary"]["rows"] == len(runner.load_rows(GOLD))
    assert report["summary"]["exact"] is not None
    assert "# 考研评测报告" in runner.render_markdown(
        {"meta": {"date": "d", "commit": "c", "gold": "g", "splits": [], "rows": 1}, "layers": {"L0": report}}
    )


def test_normalize_text_equivalences() -> None:
    assert normalize_text("2.5 万元") == normalize_text("25000元") == "25000元"
    assert normalize_text("16,000") == "16000"
    assert normalize_text("101、204") == "101,204"
    assert normalize_text("4 月 8 日") == "4月8日"
    assert normalize_text("加试两门") == normalize_text("加试2门") == normalize_text("加试 2 门")
    assert normalize_text("学制三年") == "学制3年" and normalize_text("二十年") == "二十年"
    assert normalize_text("不记入") == normalize_text("不计入")
    assert normalize_text("１∶１．２") == normalize_text("1:1.2") == "1:1.2"
    assert normalize_text("40%—50%") == normalize_text("40%-50%")
    assert normalize_text("一般") == "一般" and normalize_text("26.8万") == "268000"


def test_contains_and_alternatives() -> None:
    answer = "非全日制定向 2.5 万元/年，加试 2 门，机试成绩不计入"
    assert contains(answer, "25000") and contains(answer, "两门")
    assert contains(answer, ["不算分", "不记入"]) and not contains(answer, ["不算分", "免考"])
    assert missing_items(answer, ["3年", ["2.5万", "25000"]]) == ["3年"]
    assert forbidden_items(answer, ["机试成绩不记入", "8门"]) == ["机试成绩不记入"]
