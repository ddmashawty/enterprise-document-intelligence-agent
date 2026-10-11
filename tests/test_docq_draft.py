import csv
import json
from pathlib import Path

import pytest

from doc_agent.eval.drafts import check_item, too_short
from doc_agent.ingest.loaders import load_file

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "data" / "gold" / "docq_m1_draft.json"
DATA = ROOT / "data" / "kaoyan"


def _manifest() -> dict[str, dict]:
    with (DATA / "raw" / "manifest.csv").open(encoding="utf-8-sig", newline="") as f:
        return {r["doc_id"]: r for r in csv.DictReader(f) if r.get("doc_id")}


def _items() -> list[dict]:
    return json.loads(DRAFT.read_text(encoding="utf-8"))["items"]


@pytest.fixture(scope="module")
def texts() -> dict[str, str]:
    """Original text of every cited doc that exists locally; gitignored files are absent in CI."""
    manifest = _manifest()
    cited = {f["doc"] for item in _items() for f in [*item["evidence"], *item.get("rubric_evidence", [])]}
    out = {}
    for doc in cited:
        path = DATA / manifest[doc]["local_path"]
        if path.exists():
            out[doc] = load_file(path).text
    return out


def test_draft_items_pass_the_checks(texts: dict[str, str]) -> None:
    manifest = _manifest()
    tracked = {f["doc"] for item in _items() for f in item["evidence"] if manifest[f["doc"]]["commit_to_git"] == "True"}
    assert tracked <= set(texts)
    problems = [p for item in _items() for p in check_item(item, texts)]
    assert not problems, "\n".join(problems)


def test_draft_stays_unreviewed_and_out_of_the_eval_set() -> None:
    spec = json.loads(DRAFT.read_text(encoding="utf-8"))
    assert spec["reviewed_by"] == "" and spec["reviewed_at"] == ""
    ids = {item["id"] for item in spec["items"]}
    eval_ids = {json.loads(line)["id"] for line in (ROOT / "data" / "gold" / "kaoyan_eval_v2.jsonl").open(encoding="utf-8")}
    assert not ids & eval_ids


def test_draft_cites_no_personal_data_file() -> None:
    manifest = _manifest()
    cited = {d for item in _items() for d in item["sources"]}
    assert all(manifest[d]["contains_personal_data"] == "False" for d in cited)


def test_draft_quotes_tracked_originals_where_ci_can_check() -> None:
    manifest = _manifest()
    local_only = {
        f["doc"] for item in _items() for f in item["evidence"] if manifest[f["doc"]]["commit_to_git"] != "True"
    }
    assert local_only <= {"sysu-072"}


def test_check_item_flags_bad_drafts() -> None:
    item = {
        "id": "x", "sources": ["d1"], "must_include": ["60", ["8门", "八门"], "不计入", "200分"],
        "evidence": [{"doc": "d1", "text": "成绩8门以上 … 加试成绩不记入总分"}, {"doc": "d2", "text": "60分"}],
        "needs_user_check": "看一下",
    }
    problems = check_item(item, {"d1": "成绩 8 门以上，加试成绩不记入总分"})
    assert any("ellipsis" in p for p in problems)
    assert any("d2 is not in sources" in p for p in problems)
    assert any("['60'] needs a unit" in p for p in problems)
    assert any("'200分' is in no evidence" in p for p in problems)
    assert any("not found verbatim in d1" in p for p in problems)
    assert any("needs_user_check" in p for p in problems)
    assert not any(p.startswith("x: must_include") and ("8门" in p or "不计入" in p) for p in problems)


def test_too_short() -> None:
    assert too_short("3") and too_short("60") and too_short("2.5") and too_short("年")
    assert not too_short("3年") and not too_short("60分") and not too_short("8000") and not too_short("085411")
