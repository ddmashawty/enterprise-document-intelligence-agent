"""Scoring for the kaoyan eval set. Pure functions over intents and tool outputs."""

from __future__ import annotations

import json
from typing import Any


def predicted_operation(intent: dict[str, Any]) -> str:
    kinds = set(intent.get("kinds") or [])
    if intent.get("export"):
        return "export"
    if "filter" in kinds:
        return "filter"
    if "compare" in kinds:
        return "compare"
    return "lookup"


def intent_fields(expected: dict[str, Any], predicted: dict[str, Any], expected_refusal: str | None) -> dict[str, bool]:
    """Field-by-field match of a detected intent against the gold intent.

    `metrics` is only scored when the gold row lists metrics; the migrated v1 rows leave it empty.
    The detector keeps 4-digit discipline codes (0812) in `prefixes`, so they count as codes here.
    """
    codes = set(predicted.get("codes") or []) | set(predicted.get("prefixes") or [])
    fields = {
        "schools": set(predicted.get("schools") or []) == set(expected.get("schools") or []),
        "codes": codes == set(expected.get("codes") or []),
        "year": predicted.get("year") == expected.get("year"),
        "operation": predicted_operation(predicted) == expected.get("operation"),
        "privacy": bool(predicted.get("privacy")) == (expected_refusal == "privacy"),
    }
    if expected.get("metrics"):
        fields["metrics"] = set(expected["metrics"]) <= set(predicted.get("kinds") or [])
    return fields


_FACT_KEYS = ("lines", "score_lines", "plans", "admission_stats", "exam_subjects")


def _walk_programs(data: Any):
    if isinstance(data, dict):
        if "program_id" in data and any(k in data for k in _FACT_KEYS):
            yield data
        for value in data.values():
            yield from _walk_programs(value)
    elif isinstance(data, list):
        for value in data:
            yield from _walk_programs(value)


def _fact(table: str, pid: str, kind: Any, year: Any, value: Any, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "table": table,
        "program_id": pid,
        "kind": kind,
        "year": year,
        "value": value,
        "source_doc_id": (item.get("source") or {}).get("doc_id"),
    }


def tool_facts(outputs: list[str]) -> list[dict[str, Any]]:
    """Facts found in kaoyan tool outputs, keyed like `expected_facts`.

    get_score_lines names the score lines `lines`, search_programs names them `score_lines`.
    Exam subjects become one fact per slot: kind `slot4`, value the subject code.
    """
    facts: list[dict[str, Any]] = []
    for output in outputs:
        try:
            data = json.loads(output)
        except (TypeError, json.JSONDecodeError):
            continue
        for program in _walk_programs(data):
            pid = program["program_id"]
            for line in (program.get("lines") or []) + (program.get("score_lines") or []):
                facts.append(_fact("score_lines", pid, line.get("scope"), line.get("year"), line.get("total"), line))
            for table in ("plans", "admission_stats"):
                for item in program.get(table) or []:
                    facts.append(_fact(table, pid, item.get("kind"), item.get("year"), item.get("value"), item))
            for entry in program.get("exam_subjects") or []:
                for subject in entry.get("subjects") or []:
                    facts.append(_fact("exam_subjects", pid, f"slot{subject.get('slot')}", entry.get("year"),
                                       subject.get("code"), entry))
    return facts


def match_fact(expected: dict[str, Any], facts: list[dict[str, Any]]) -> tuple[bool, bool]:
    """(value found, found with the expected source document)."""
    key = ("table", "program_id", "kind", "year", "value")
    hits = [f for f in facts if all(f[k] == expected[k] for k in key)]
    return bool(hits), any(f["source_doc_id"] == expected.get("source_doc_id") for f in hits)


def ratio(hit: int, total: int) -> float | None:
    return round(hit / total, 4) if total else None
