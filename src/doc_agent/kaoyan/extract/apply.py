"""Resolve facts to programs, compare with the seed, and write them.

Every machine-extracted row is written as its own row (seed rows are never updated):
``verified=1`` only when it equals the seed row with the same key; a differing value is a
*conflict* — written with ``verified=0`` and reported, never overwriting the seed.
Re-running replaces the previous rule / llm rows of the same documents.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from doc_agent.kaoyan.db import KaoyanStore
from doc_agent.kaoyan.extract.base import Fact, ProgramRef
from doc_agent.kaoyan.models import (
    SEED_METHODS,
    AdmissionStat,
    Direction,
    ExamSubject,
    Plan,
    ScoreLine,
)

Status = Literal["match", "conflict", "new", "unresolved", "ambiguous", "duplicate"]

KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "plans": ("program_id", "year", "kind", "source_doc_id"),
    "score_lines": ("school_id", "program_id", "year", "scope", "discipline_code", "source_doc_id"),
    "admission_stats": ("program_id", "year", "kind", "source_doc_id"),
    "exam_subjects": ("program_id", "year", "slot", "status", "source_doc_id"),
    "directions": ("program_id", "year", "code", "source_doc_id"),
}
VALUE_FIELDS: dict[str, tuple[str, ...]] = {
    "plans": ("value", "is_upper_bound", "pool_scope"),
    "score_lines": ("total", "politics", "foreign_lang", "subject1", "subject2"),
    "admission_stats": ("value", "pool_scope"),
    "exam_subjects": ("code", "name", "status"),
    "directions": ("name",),
}
OPTIONAL_FIELDS = frozenset({"politics", "foreign_lang", "subject1", "subject2"})
_MODELS: dict[str, type[BaseModel]] = {
    "plans": Plan,
    "score_lines": ScoreLine,
    "admission_stats": AdmissionStat,
    "exam_subjects": ExamSubject,
    "directions": Direction,
}
_KIND_FIELD = {"plans": "kind", "admission_stats": "kind", "score_lines": "scope"}


class ProgramResolver:
    """Source-style program reference → ``programs.id`` (only programs already in the DB)."""

    def __init__(self, store: KaoyanStore) -> None:
        self._rows = store.query(
            "SELECT p.id, p.school_id, p.college_id, p.code, p.study_mode, "
            "c.code AS college_code, c.slug, c.name AS college_name "
            "FROM programs p JOIN colleges c ON c.id = p.college_id"
        )

    def resolve(self, school_id: str, ref: ProgramRef) -> tuple[list[str], Status | None]:
        rows = [r for r in self._rows if r["school_id"] == school_id]
        if ref.college:
            keys = ("college_id", "college_code", "slug", "college_name")
            rows = [r for r in rows if ref.college in (r[k] for k in keys)]
        elif ref.is_pool:
            return [], "unresolved"
        if ref.is_pool:
            rows = [r for r in rows if r["code"].startswith(ref.code)]
        else:
            rows = [r for r in rows if r["code"] == ref.code]
        if ref.study_mode:
            rows = [r for r in rows if r["study_mode"] == ref.study_mode]
        if not rows:
            return [], "unresolved"
        if not ref.is_pool and len(rows) > 1:
            return [], "ambiguous"
        return [r["id"] for r in rows], None


def _norm(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        return "".join(value.split())
    return value


def fact_row(fact: Fact, program_id: str | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "program_id": program_id,
        "year": fact.year,
        "source_doc_id": fact.source_doc_id,
        "evidence_text": fact.evidence_text,
        "extraction_method": fact.extraction_method,
        "verified": False,
        **fact.values,
    }
    if fact.table in _KIND_FIELD:
        row[_KIND_FIELD[fact.table]] = fact.kind
    if fact.table == "score_lines":
        row["school_id"] = fact.school_id
    if fact.table in ("plans", "score_lines", "exam_subjects"):
        row["page"] = fact.page
    fields = _MODELS[fact.table].model_fields
    return {k: v for k, v in row.items() if k in fields}


def row_key(table: str, row: dict[str, Any]) -> tuple[Any, ...]:
    return (table, *(row.get(k) for k in KEY_FIELDS[table]))


def differences(table: str, seed: dict[str, Any], row: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    """Fields where the seed states a value and the extraction disagrees.

    Single-subject lines are optional detail: an extraction that omits them is not a conflict.
    """
    out: dict[str, tuple[Any, Any]] = {}
    for f in VALUE_FIELDS[table]:
        s, v = seed.get(f), row.get(f)
        if s is None or (f == "is_upper_bound" and not s and not v):
            continue
        if v is None and f in OPTIONAL_FIELDS:
            continue
        if _norm(s) != _norm(v):
            out[f] = (s, v)
    return out


@dataclass
class FactResult:
    fact: Fact
    status: Status
    program_id: str | None = None
    row: dict[str, Any] | None = None
    seed: dict[str, Any] | None = None
    diff: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    @property
    def key(self) -> tuple[Any, ...] | None:
        return row_key(self.fact.table, self.row) if self.row else None


@dataclass
class ApplyReport:
    results: list[FactResult] = field(default_factory=list)
    removed: int = 0
    written: int = 0

    def counts(self) -> dict[str, int]:
        return dict(Counter(r.status for r in self.results))

    def by_doc(self) -> dict[str, dict[str, int]]:
        out: dict[str, Counter[str]] = {}
        for r in self.results:
            out.setdefault(r.fact.source_doc_id, Counter())[r.status] += 1
        return {doc: dict(c) for doc, c in sorted(out.items())}

    @property
    def conflicts(self) -> list[FactResult]:
        return [r for r in self.results if r.status == "conflict"]

    def summary(self) -> dict[str, Any]:
        return {
            "facts": len(self.results),
            "status": self.counts(),
            "written": self.written,
            "removed_previous": self.removed,
            "by_doc": self.by_doc(),
            "conflicts": [
                {
                    "key": list(r.key or ()),
                    "diff": {k: list(v) for k, v in r.diff.items()},
                    "seed_evidence": (r.seed or {}).get("evidence_text"),
                    "evidence": r.fact.evidence_text,
                }
                for r in self.conflicts
            ],
        }


def load_seed_rows(store: KaoyanStore, doc_ids: set[str]) -> dict[tuple[Any, ...], dict[str, Any]]:
    if not doc_ids:
        return {}
    ids = sorted(doc_ids)
    marks = ", ".join("?" for _ in ids)
    methods = ", ".join("?" for _ in SEED_METHODS)
    seeds: dict[tuple[Any, ...], dict[str, Any]] = {}
    for table in KEY_FIELDS:
        rows = store.query(
            f"SELECT * FROM {table} WHERE source_doc_id IN ({marks}) AND extraction_method IN ({methods})",
            [*ids, *SEED_METHODS],
        )
        for row in rows:
            seeds.setdefault(row_key(table, row), row)
    return seeds


def apply_facts(
    store: KaoyanStore,
    facts: list[Fact],
    *,
    doc_ids: set[str] | None = None,
    write: bool = True,
) -> ApplyReport:
    """Resolve, compare with the seed and (optionally) write ``facts``.

    ``doc_ids`` are the documents whose previous rule / llm rows are replaced
    (default: the documents the facts come from).
    """
    docs = set(doc_ids) if doc_ids is not None else {f.source_doc_id for f in facts}
    resolver = ProgramResolver(store)
    seeds = load_seed_rows(store, docs)
    report = ApplyReport()
    seen: set[tuple[Any, ...]] = set()
    to_write: list[tuple[str, BaseModel]] = []

    for fact in facts:
        if fact.program is None:
            program_ids: list[str | None] = [None]
        else:
            resolved, problem = resolver.resolve(fact.school_id, fact.program)
            if problem:
                report.results.append(FactResult(fact, problem))
                continue
            program_ids = list(resolved)
        for pid in program_ids:
            row = fact_row(fact, pid)
            key = row_key(fact.table, row)
            if key in seen:
                report.results.append(FactResult(fact, "duplicate", pid, row))
                continue
            seen.add(key)
            seed = seeds.get(key)
            if seed is None:
                status: Status = "new"
                diff: dict[str, tuple[Any, Any]] = {}
            else:
                diff = differences(fact.table, seed, row)
                status = "conflict" if diff else "match"
            row["verified"] = status == "match"
            report.results.append(FactResult(fact, status, pid, row, seed, diff))
            to_write.append((fact.table, _MODELS[fact.table](**row)))

    if write:
        with store.transaction() as conn:
            report.removed = store.delete_extracted_facts(conn, docs)
            for table, model in to_write:
                store.insert(conn, table, model)
        report.written = len(to_write)
    return report
