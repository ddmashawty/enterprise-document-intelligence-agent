from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel

from doc_agent.config import get_settings
from doc_agent.kaoyan.models import SEED_METHODS

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_FACT_TABLES = ("directions", "exam_subjects", "plans", "score_lines", "admission_stats")


def _row_values(model: BaseModel) -> dict[str, Any]:
    data = model.model_dump()
    return {k: int(v) if isinstance(v, bool) else v for k, v in data.items()}


class KaoyanStore:
    """SQLite store for structured kaoyan facts (data/kaoyan.db)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._connect()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def init_schema(self) -> None:
        with self.transaction() as conn:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    # -- writes -----------------------------------------------------------

    @staticmethod
    def upsert(conn: sqlite3.Connection, table: str, model: BaseModel, key: str = "id") -> None:
        values = _row_values(model)
        cols = list(values)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != key)
        conn.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)}) "
            f"ON CONFLICT({key}) DO UPDATE SET {updates}",
            [values[c] for c in cols],
        )

    @staticmethod
    def insert(conn: sqlite3.Connection, table: str, model: BaseModel) -> int:
        values = _row_values(model)
        cols = list(values)
        cur = conn.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [values[c] for c in cols],
        )
        return int(cur.lastrowid or 0)

    @staticmethod
    def delete_seed_facts(conn: sqlite3.Connection) -> None:
        marks = ", ".join("?" for _ in SEED_METHODS)
        for table in _FACT_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE extraction_method IN ({marks})", SEED_METHODS)

    # -- reads ------------------------------------------------------------

    def query(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(sql, params).fetchall()
            finally:
                conn.close()
        return [dict(r) for r in rows]

    def query_one(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def count(self, table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
        sql = f"SELECT COUNT(*) AS n FROM {table}" + (f" WHERE {where}" if where else "")
        row = self.query_one(sql, params)
        return int(row["n"]) if row else 0

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM documents WHERE id = ?", (doc_id,))

    def find_programs(
        self,
        *,
        school_id: str | None = None,
        college_code: str | None = None,
        code: str | None = None,
        study_mode: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT p.*, c.code AS college_code, c.name AS college_name "
            "FROM programs p JOIN colleges c ON c.id = p.college_id WHERE 1=1"
        )
        params: list[Any] = []
        if school_id:
            sql += " AND p.school_id = ?"
            params.append(school_id)
        if college_code:
            sql += " AND (c.code = ? OR c.slug = ?)"
            params.extend([college_code, college_code])
        if code:
            sql += " AND p.code = ?"
            params.append(code)
        if study_mode:
            sql += " AND p.study_mode = ?"
            params.append(study_mode)
        return self.query(sql + " ORDER BY p.id", params)

    def plans_for(self, program_id: str, kind: str | None = None, year: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM plans WHERE program_id = ?"
        params: list[Any] = [program_id]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if year is not None:
            sql += " AND year = ?"
            params.append(year)
        return self.query(sql + " ORDER BY year DESC, kind, id", params)

    def score_lines_for(self, program_id: str, scope: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM score_lines WHERE program_id = ?"
        params: list[Any] = [program_id]
        if scope:
            sql += " AND scope = ?"
            params.append(scope)
        return self.query(sql + " ORDER BY year DESC, scope, id", params)

    def school_baselines(self, school_id: str, year: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM score_lines WHERE school_id = ? AND scope = 'school_baseline' AND program_id IS NULL"
        params: list[Any] = [school_id]
        if year is not None:
            sql += " AND year = ?"
            params.append(year)
        return self.query(sql + " ORDER BY discipline_code", params)

    def subjects_for(self, program_id: str) -> list[dict[str, Any]]:
        return self.query(
            "SELECT * FROM exam_subjects WHERE program_id = ? ORDER BY year DESC, slot",
            (program_id,),
        )

    def stats_for(self, program_id: str) -> list[dict[str, Any]]:
        return self.query(
            "SELECT * FROM admission_stats WHERE program_id = ? ORDER BY year DESC, kind",
            (program_id,),
        )

    def program_facts(self, program_id: str) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM v_program_facts WHERE program_id = ?", (program_id,))


@lru_cache
def get_kaoyan_store() -> KaoyanStore:
    return KaoyanStore(get_settings().kaoyan_db_path)
