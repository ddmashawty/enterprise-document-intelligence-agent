import json
from pathlib import Path

from doc_agent.agent.graph import token_usage

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "gold" / "kaoyan_eval_v2.jsonl"
CANDIDATES = ROOT / "data" / "gold" / "candidates_m0.jsonl"
REVIEW = ROOT / "data" / "gold" / "review_m0.json"


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
    assert all(r["reviewed_by"] == "" for r in rows)
    assert all(r["expected_facts"] == [] for r in rows)
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
        assert r["split"] == "unsplit"
        assert r["reviewed_by"] and r["reviewed_at"]
        for fact in r["expected_facts"]:
            assert str(fact["value"]) in r["must_include"], r["id"]
