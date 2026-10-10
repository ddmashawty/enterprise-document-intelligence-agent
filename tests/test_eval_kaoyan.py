import json
from pathlib import Path

from doc_agent.eval import runner
from doc_agent.eval.metrics import intent_fields, match_fact, tool_facts

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
    from doc_agent.agent import kaoyan_flow

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


def test_regressions_flag_drops_beyond_threshold():
    base = {"layers": {"L0": {"summary": {"rows": 10, "exact": 0.9, "codes": 1.0}}}}
    now = {"layers": {"L0": {"summary": {"rows": 10, "exact": 0.89, "codes": 0.95}}}}
    assert runner.regressions(now, base, 0.02) == ["L0.codes: 100.00% -> 95.00%"]


def test_l0_runs_on_the_eval_set_without_a_database():
    report = runner.run_l0(runner.load_rows(GOLD))
    assert report["summary"]["rows"] == len(runner.load_rows(GOLD))
    assert report["summary"]["exact"] is not None
    assert "# 考研评测报告" in runner.render_markdown(
        {"meta": {"date": "d", "commit": "c", "gold": "g", "splits": [], "rows": 1}, "layers": {"L0": report}}
    )
