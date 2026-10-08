#!/usr/bin/env python3
"""Build the v2 eval skeleton without calling an LLM.

--migrate-v1 rewrites the v1-* rows of data/gold/kaoyan_eval_v2.jsonl from the old
18-question file and keeps every other row.
--candidates writes data/gold/candidates_m0.jsonl: at most one score line and one
plan question per program, capped at 60, from the local kaoyan.db.
--apply-review replaces the reviewed template rows of the eval file with the
accepted and edited candidates listed in data/gold/review_m0.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD_V1 = ROOT / "data" / "gold" / "kaoyan_qa.json"
EVAL_V2 = ROOT / "data" / "gold" / "kaoyan_eval_v2.jsonl"
CANDIDATES = ROOT / "data" / "gold" / "candidates_m0.jsonl"
REVIEW = ROOT / "data" / "gold" / "review_m0.json"
DB_PATH = ROOT / "data" / "kaoyan.db"
CANDIDATE_CAP = 60

_SCHOOLS = (
    ("华南师范大学", "scnu"),
    ("华南理工大学", "scut"),
    ("中山大学", "sysu"),
    ("暨南大学", "jnu"),
    ("华师", "scnu"),
    ("华工", "scut"),
    ("中大", "sysu"),
    ("暨大", "jnu"),
    ("暨南", "jnu"),
)
_ALL_SCHOOLS = ["sysu", "scut", "jnu", "scnu"]
_CATEGORY = {
    "score_line": "score_line",
    "no_exam": "tm",
    "unknown": "unknown_data",
    "subjects": "subjects",
    "pool": "plan",
    "conflict": "plan",
    "filter": "filter",
    "compare": "compare",
    "year": "year_mismatch",
    "scope": "unknown_data",
    "upper_bound": "plan",
    "boundary": "subjects",
    "privacy": "privacy",
    "export": "export",
}
_OPERATION = {
    "compare": "compare",
    "filter": "filter",
    "export": "export",
}
_PLAN_RANK = {
    "catalog_total": 0,
    "public_exam": 1,
    "college_exam_plan": 2,
    "available_exam": 3,
    "rules_total": 4,
}
_SCOPE_RANK = {"college": 0, "school_baseline": 1}


def _schools(question: str) -> list[str]:
    if "四校" in question:
        return list(_ALL_SCHOOLS)
    found = []
    for label, sid in _SCHOOLS:
        if label in question and sid not in found:
            found.append(sid)
    return found


def _codes(question: str) -> list[str]:
    six = re.findall(r"(?<![0-9A-Za-z])(\d{4}[0-9A-Z]{2})(?![0-9A-Za-z])", question)
    four = [c for c in re.findall(r"(?<![0-9A-Za-z])(\d{4})(?![0-9A-Za-z])", question) if not c.startswith("20")]
    out = []
    for code in six + four:
        if code not in out:
            out.append(code)
    return out


def _years(question: str) -> list[int]:
    return [int(y) for y in re.findall(r"20\d{2}", question)]


def migrate_v1_item(item: dict) -> dict:
    category = _CATEGORY[item["category"]]
    question = item["question"]
    years = _years(question)
    refusal = None
    if item["category"] == "privacy":
        refusal = "privacy"
    elif item.get("expect_unknown"):
        refusal = "unknown_data"
    notes = [f"migrated from kaoyan_qa.json id={item['id']}; split=dev because this set was used for tuning."]
    if item.get("must_not_match"):
        notes.append("must_not_match=" + json.dumps(item["must_not_match"], ensure_ascii=False))
    if item.get("export_columns"):
        notes.append("export_columns=" + "、".join(item["export_columns"]))
    return {
        "id": f"v1-{int(item['id']):02d}",
        "split": "dev",
        "category": category,
        "turns": [question],
        "school": _schools(question),
        "program_ids": [],
        "year": years[0] if len(years) == 1 else None,
        "expected_intent": {
            "operation": _OPERATION.get(category, "lookup"),
            "metrics": [],
            "schools": _schools(question),
            "codes": _codes(question),
            "year": years[0] if len(years) == 1 else None,
            "follow_up": False,
        },
        "expected_facts": [],
        "expected_refusal": refusal,
        "expected_sources": [s["url"] for s in item.get("sources") or [] if s.get("url")],
        "must_include": item.get("must_include") or [],
        "must_not_include": item.get("must_not_include") or [],
        "judge_rubric": "",
        "origin": "handwritten",
        "reviewed_by": "",
        "reviewed_at": "",
        "notes": " ".join(notes),
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def migrate_v1() -> list[dict]:
    payload = json.loads(GOLD_V1.read_text(encoding="utf-8"))
    rows = [migrate_v1_item(item) for item in payload["items"]]
    kept = [r for r in read_jsonl(EVAL_V2) if not r["id"].startswith("v1-")]
    write_jsonl(EVAL_V2, rows + kept)
    return rows


def reviewed_row(candidate: dict, decision: dict, reviewer: str, reviewed_at: str) -> dict:
    row = json.loads(json.dumps(candidate))
    row["id"] = decision.get("new_id") or candidate["id"].replace("cand-", "rv-", 1)
    row["split"] = "unsplit"
    for key in ("turns", "program_ids", "expected_facts", "must_include", "must_not_include"):
        if key in decision:
            row[key] = decision[key]
    if "codes" in decision:
        row["expected_intent"]["codes"] = decision["codes"]
    row["expected_sources"] = row["expected_sources"] + [
        u for u in decision.get("extra_sources") or [] if u not in row["expected_sources"]
    ]
    row["reviewed_by"] = reviewer
    row["reviewed_at"] = reviewed_at
    note = f"from {candidate['id']}; {decision['action']}; evidence: {decision['evidence']}"
    if decision.get("reason"):
        note += f"; {decision['reason']}"
    row["notes"] = note
    ordered = {}
    for key, value in row.items():
        ordered[key] = value
        if key == "must_not_include":
            ordered["judge_rubric"] = decision.get("judge_rubric", "")
    return ordered


def apply_review() -> list[dict]:
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    candidates = {r["id"]: r for r in read_jsonl(CANDIDATES)}
    decisions = review["decisions"]
    decided = {d["id"] for d in decisions}
    if decided != set(candidates):
        raise SystemExit(
            "review_m0.json and candidates_m0.jsonl disagree; "
            f"undecided: {sorted(set(candidates) - decided)}, unknown: {sorted(decided - set(candidates))}"
        )
    rows = [
        reviewed_row(candidates[d["id"]], d, review["reviewer"], review["reviewed_at"])
        for d in decisions
        if d["action"] in {"accept", "edit"}
    ]
    rows += [addition_row(a, review["reviewer"], review["reviewed_at"]) for a in review.get("additions") or []]
    kept = [r for r in read_jsonl(EVAL_V2) if not r["id"].startswith("rv-")]
    write_jsonl(EVAL_V2, kept + rows)
    return rows


def addition_row(addition: dict, reviewer: str, reviewed_at: str) -> dict:
    """A question written during review for a fact the template generator skips."""
    metric = "score_line" if addition["category"] == "score_line" else "plan"
    return {
        "id": addition["id"],
        "split": "unsplit",
        "category": addition["category"],
        "turns": addition["turns"],
        "school": addition["school"],
        "program_ids": addition["program_ids"],
        "year": addition["year"],
        "expected_intent": {
            "operation": "lookup",
            "metrics": [metric],
            "schools": addition["school"],
            "codes": addition["codes"],
            "year": addition["year"],
            "follow_up": False,
        },
        "expected_facts": addition["expected_facts"],
        "expected_refusal": None,
        "expected_sources": addition["expected_sources"],
        "must_include": addition["must_include"],
        "must_not_include": addition.get("must_not_include") or [],
        "judge_rubric": addition.get("judge_rubric", ""),
        "origin": "handwritten",
        "reviewed_by": reviewer,
        "reviewed_at": reviewed_at,
        "notes": f"review addition; evidence: {addition['evidence']}; {addition['reason']}",
    }


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _programs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT p.id AS program_id, p.school_id, p.code, p.name AS program_name,
                   s.short_name, c.name AS college_name
            FROM programs p
            JOIN schools s ON s.id = p.school_id
            JOIN colleges c ON c.id = p.college_id
            ORDER BY p.school_id, p.code, p.id
            """
        )
    )


def _best_score_line(conn: sqlite3.Connection, program_id: str) -> sqlite3.Row | None:
    rows = list(
        conn.execute(
            """
            SELECT sl.program_id, sl.year, sl.scope, sl.total, sl.source_doc_id,
                   sl.verified, d.page_url, d.title
            FROM score_lines sl
            LEFT JOIN documents d ON d.id = sl.source_doc_id
            WHERE sl.program_id = ? AND sl.total IS NOT NULL
              AND sl.scope IN ('college', 'school_baseline')
            """,
            (program_id,),
        )
    )
    if not rows:
        return None
    rows.sort(key=lambda r: (_SCOPE_RANK.get(r["scope"], 9), -r["year"], -r["verified"], r["source_doc_id"] or ""))
    return rows[0]


def _best_plan(conn: sqlite3.Connection, program_id: str) -> sqlite3.Row | None:
    rows = list(
        conn.execute(
            """
            SELECT pl.program_id, pl.year, pl.kind, pl.value, pl.pool_scope, pl.source_doc_id,
                   pl.verified, pl.definition, d.page_url, d.title
            FROM plans pl
            LEFT JOIN documents d ON d.id = pl.source_doc_id
            WHERE pl.program_id = ? AND pl.value IS NOT NULL
              AND pl.kind IN ('catalog_total', 'public_exam', 'college_exam_plan', 'available_exam', 'rules_total')
            """,
            (program_id,),
        )
    )
    if not rows:
        return None
    rows = [r for r in rows if not r["pool_scope"]]
    if not rows:
        return None
    rows.sort(key=lambda r: (_PLAN_RANK.get(r["kind"], 9), -r["year"], -r["verified"], r["source_doc_id"] or ""))
    return rows[0]


def _candidate(program: sqlite3.Row, fact: sqlite3.Row, metric: str) -> dict:
    year = int(fact["year"])
    if metric == "score_line":
        question = (
            f"{program['short_name']}{program['college_name']} {program['code']} "
            f"{program['program_name']}的 {year} 复试线是多少？"
        )
        kind = fact["scope"]
        value = int(fact["total"])
        table = "score_lines"
    else:
        question = (
            f"{program['short_name']}{program['college_name']} {program['code']} "
            f"{program['program_name']}的 {year} 招生计划是多少？"
        )
        kind = fact["kind"]
        value = int(fact["value"])
        table = "plans"
    url = fact["page_url"] or ""
    return {
        "id": f"cand-{program['program_id']}-{metric}-{year}",
        "split": "candidate",
        "category": metric,
        "turns": [question],
        "school": [program["school_id"]],
        "program_ids": [program["program_id"]],
        "year": year,
        "expected_intent": {
            "operation": "lookup",
            "metrics": [metric],
            "schools": [program["school_id"]],
            "codes": [program["code"]],
            "year": year,
            "follow_up": False,
        },
        "expected_facts": [
            {
                "table": table,
                "program_id": program["program_id"],
                "kind": kind,
                "year": year,
                "value": value,
                "source_doc_id": fact["source_doc_id"],
            }
        ],
        "expected_refusal": None,
        "expected_sources": [url] if url else [],
        "must_include": [str(value), str(year)],
        "must_not_include": [],
        "origin": "db_template",
        "reviewed_by": "",
        "reviewed_at": "",
        "notes": "unreviewed template; not part of kaoyan_eval_v2.jsonl",
    }


def build_candidates(db_path: Path = DB_PATH, cap: int = CANDIDATE_CAP) -> list[dict]:
    conn = _connect(db_path)
    try:
        programs = _programs(conn)
        lines = []
        plans = []
        for program in programs:
            line = _best_score_line(conn, program["program_id"])
            if line is not None:
                lines.append(_candidate(program, line, "score_line"))
            plan = _best_plan(conn, program["program_id"])
            if plan is not None:
                plans.append(_candidate(program, plan, "plan"))
    finally:
        conn.close()
    # Score lines first, then plans, until the cap. One of each per program before the slice.
    return (lines + plans)[:cap]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--migrate-v1", action="store_true", help="only rewrite kaoyan_eval_v2.jsonl")
    parser.add_argument("--candidates", action="store_true", help="only rewrite candidates_m0.jsonl")
    parser.add_argument("--apply-review", action="store_true", help="only merge review_m0.json into the eval file")
    parser.add_argument("--db", default=str(DB_PATH))
    args = parser.parse_args()

    if args.apply_review:
        rows = apply_review()
        print(f"wrote {len(rows)} reviewed rows to {EVAL_V2.relative_to(ROOT)}")
        return 0
    do_v1 = args.migrate_v1 or not args.candidates
    do_candidates = args.candidates or not args.migrate_v1
    if args.migrate_v1 and args.candidates:
        do_v1 = do_candidates = True

    if do_v1:
        rows = migrate_v1()
        print(f"wrote {len(rows)} dev rows to {EVAL_V2.relative_to(ROOT)}")

    if not do_candidates:
        return 0
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"{db_path} missing; candidates not written", file=sys.stderr)
        return 2
    rows = build_candidates(db_path)
    write_jsonl(CANDIDATES, rows)
    n_line = sum(r["category"] == "score_line" for r in rows)
    n_plan = sum(r["category"] == "plan" for r in rows)
    print(f"wrote {len(rows)} candidates ({n_line} score_line, {n_plan} plan) to {CANDIDATES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
