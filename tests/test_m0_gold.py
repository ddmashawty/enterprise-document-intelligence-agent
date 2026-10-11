import json
from pathlib import Path

from doc_agent.agent.graph import token_usage

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "gold" / "kaoyan_eval_v2.jsonl"
CANDIDATES = ROOT / "data" / "gold" / "candidates_m0.jsonl"
REVIEW = ROOT / "data" / "gold" / "review_m0.json"
ADVERSARIAL = ROOT / "data" / "gold" / "adversarial_m1.json"
SUPPLEMENT = ROOT / "data" / "gold" / "supplement_m1.json"
SPLIT = ROOT / "data" / "gold" / "split_m1.json"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_token_usage_sums_messages_that_report_tokens():
    class Msg:
        def __init__(self, meta):
            self.usage_metadata = meta

    out = token_usage(
        [
            Msg({"input_tokens": 3, "output_tokens": 4}),
            Msg(None),
            Msg({"input_tokens": 1, "output_tokens": 2}),
        ]
    )
    assert out == {
        "llm_calls_with_usage": 2,
        "prompt_tokens": 4,
        "completion_tokens": 6,
        "total_tokens": 10,
    }


def test_v1_questions_land_in_dev_only():
    rows = [r for r in _rows(EVAL) if r["id"].startswith("v1-")]
    assert len(rows) == 18
    assert {r["split"] for r in rows} == {"dev"}
    assert len({r["id"] for r in rows}) == 18
    assert all(r["reviewed_by"] and r["reviewed_at"] for r in rows)
    no_facts = {r["id"] for r in rows if not r["expected_facts"]}
    assert no_facts == {"v1-11", "v1-14"}
    assert all(r["judge_rubric"] for r in rows if r["id"] == "v1-11")
    for r in rows:
        assert r["program_ids"] == list(dict.fromkeys(f["program_id"] for f in r["expected_facts"]))
    privacy = next(r for r in rows if r["id"] == "v1-17")
    assert privacy["expected_refusal"] == "privacy"
    unknown = next(r for r in rows if r["id"] == "v1-05")
    assert unknown["expected_refusal"] == "unknown_data"


def test_m0_candidates_are_unreviewed_templates():
    rows = _rows(CANDIDATES)
    assert 1 <= len(rows) <= 60
    assert {r["category"] for r in rows} <= {"score_line", "plan"}
    assert all(r["split"] == "candidate" for r in rows)
    assert all(r["reviewed_by"] == "" for r in rows)
    assert all(r["expected_facts"] and r["expected_facts"][0]["value"] for r in rows)
    assert "score_line" in {r["category"] for r in rows}
    assert "plan" in {r["category"] for r in rows}


def test_every_candidate_has_one_review_decision():
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    ids = [d["id"] for d in review["decisions"]]
    assert sorted(ids) == sorted(r["id"] for r in _rows(CANDIDATES))
    assert all(d["action"] in {"accept", "edit", "drop"} for d in review["decisions"])
    assert all(d["evidence"] for d in review["decisions"])
    assert all(d.get("reason") for d in review["decisions"] if d["action"] != "accept")


def test_reviewed_rows_check_the_numbers_they_claim():
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    kept = sum(d["action"] != "drop" for d in review["decisions"]) + len(review.get("additions") or [])
    rows = [r for r in _rows(EVAL) if r["id"].startswith("rv-")]
    assert len(rows) == kept
    assert len({r["id"] for r in _rows(EVAL)}) == len(_rows(EVAL))
    assert all(isinstance(r["judge_rubric"], str) for r in _rows(EVAL))
    for r in rows:
        assert r["split"] in {"dev", "test"}
        assert r["reviewed_by"] and r["reviewed_at"]
        for fact in r["expected_facts"]:
            assert str(fact["value"]) in r["must_include"], r["id"]


def test_adversarial_rows_cover_every_trap():
    spec = json.loads(ADVERSARIAL.read_text(encoding="utf-8"))
    rows = [r for r in _rows(EVAL) if r["id"].startswith("adv-")]
    assert [r["id"] for r in rows] == [item["id"] for item in spec["items"]]
    traps = {"out_of_scope", "privacy", "year", "cross_school", "upper_bound", "pool", "boundary", "no_exam"}
    assert {r["trap"] for r in rows} == traps
    assert all(sum(r["trap"] == t for r in rows) >= 10 for t in traps)
    for r in rows:
        assert r["split"] == "adversarial"
        assert r["expected_refusal"] in {None, "out_of_scope", "privacy", "unknown_data"}
        assert r["judge_rubric"], r["id"]
        assert r["expected_facts"] or r["expected_refusal"], r["id"]
        assert r["expected_intent"]["follow_up"] == (len(r["turns"]) > 1)
        assert (r["trap"] == "out_of_scope") == (r["expected_refusal"] == "out_of_scope")
        if r["expected_refusal"] == "privacy":
            assert r["trap"] == "privacy"
        assert r["reviewed_by"] and r["reviewed_by"] == spec["reviewed_by"]
    anonymous = {r["id"] for r in rows if r["trap"] == "privacy" and not r["expected_refusal"]}
    assert anonymous == {"adv-priv-07", "adv-priv-09"}


def test_supplement_rows_cite_a_fact_or_a_document():
    spec = json.loads(SUPPLEMENT.read_text(encoding="utf-8"))
    rows = [r for r in _rows(EVAL) if r["id"].startswith("sup-")]
    assert [r["id"] for r in rows] == [item["id"] for item in spec["items"]] == [f"sup-{i:02d}" for i in range(1, 41)]
    assert {r["trap"] for r in rows} == {
        "colloquial", "missing_field", "policy", "prediction", "false_premise", "aggregate", "routing"}
    assert {r["school"][0] for r in rows if len(r["school"]) == 1} == {"sysu", "scut", "jnu", "scnu"}
    for r, item in zip(rows, spec["items"], strict=True):
        assert r["split"] in {"dev", "test"}
        assert r["judge_rubric"] and item["user_label"], r["id"]
        assert r["reviewed_by"] == spec["reviewed_by"]
        assert r["expected_intent"]["follow_up"] == (len(r["turns"]) > 1)
        cited = r["expected_facts"] or item.get("sources")
        assert cited or r["expected_refusal"] or r["trap"] == "aggregate", r["id"]
        for fact in r["expected_facts"]:
            assert fact.get("field", "total") in {"total", "politics", "foreign_lang", "subject1", "subject2"}


def test_test_split_is_frozen():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_gold", ROOT / "scripts" / "build_gold_candidates.py")
    build_gold = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_gold)
    row_digest = build_gold.row_digest

    frozen = json.loads(SPLIT.read_text(encoding="utf-8"))
    rows = _rows(EVAL)
    assert "unsplit" not in {r["split"] for r in rows}
    test = {r["id"]: r for r in rows if r["split"] == "test"}
    assert set(test) == set(frozen["test"])
    assert not set(test) & set(frozen["excluded"])
    assert all(not i.startswith(("v1-", "adv-")) for i in test)
    changed = sorted(i for i, digest in frozen["test"].items() if row_digest(test[i]) != digest)
    assert not changed, f"test rows edited; justify in the PR, then run --rehash-test: {changed}"
    non_adv = [r for r in rows if r["split"] in {"dev", "test"} and not r["id"].startswith("v1-")]
    assert 0.25 <= len(test) / len(non_adv) <= 0.35
