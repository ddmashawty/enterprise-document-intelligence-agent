from __future__ import annotations

import json
import sqlite3
import threading
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from doc_agent.config import get_settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    task_id: str
    session_id: str
    user_goal: str
    plan: list[str]
    answer: str
    citations: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    reflection: str
    exports: list[dict[str, Any]]
    status: str
    iterations: int
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SessionMemory:
    """Process-local short-term memory: recent turns per session."""

    def __init__(self, max_turns: int = 12) -> None:
        self._max_turns = max_turns
        self._turns: dict[str, deque[dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=self._max_turns)
        )
        self._lock = threading.Lock()

    def append(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            self._turns[session_id].append(
                {"role": role, "content": content, "at": _utc_now()}
            )

    def history(self, session_id: str, limit: int = 6) -> list[dict[str, str]]:
        with self._lock:
            turns = list(self._turns.get(session_id, ()))
        return turns[-limit:] if limit else turns

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._turns.pop(session_id, None)


class TaskStore:
    """SQLite durable task trajectories (+ optional turn archive)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_goal TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    trace_json TEXT NOT NULL,
                    reflection TEXT NOT NULL,
                    exports_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    iterations INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_session
                    ON tasks(session_id, created_at);
                CREATE TABLE IF NOT EXISTS session_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    task_id TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_turns_session
                    ON session_turns(session_id, id);
                """
            )

    def save_task(self, record: TaskRecord) -> TaskRecord:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks (
                    task_id, session_id, user_goal, plan_json, answer,
                    citations_json, trace_json, reflection, exports_json,
                    status, iterations, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.task_id,
                    record.session_id,
                    record.user_goal,
                    json.dumps(record.plan, ensure_ascii=False),
                    record.answer,
                    json.dumps(record.citations, ensure_ascii=False),
                    json.dumps(record.trace, ensure_ascii=False),
                    record.reflection,
                    json.dumps(record.exports, ensure_ascii=False),
                    record.status,
                    record.iterations,
                    record.created_at,
                ),
            )
        return record

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        if not row:
            return None
        return TaskRecord(
            task_id=row["task_id"],
            session_id=row["session_id"],
            user_goal=row["user_goal"],
            plan=json.loads(row["plan_json"] or "[]"),
            answer=row["answer"] or "",
            citations=json.loads(row["citations_json"] or "[]"),
            trace=json.loads(row["trace_json"] or "[]"),
            reflection=row["reflection"] or "",
            exports=json.loads(row["exports_json"] or "[]"),
            status=row["status"] or "",
            iterations=int(row["iterations"] or 0),
            created_at=row["created_at"] or "",
        )

    def list_tasks(self, session_id: str | None = None, limit: int = 20) -> list[TaskRecord]:
        sql = "SELECT * FROM tasks"
        params: tuple[Any, ...] = ()
        if session_id:
            sql += " WHERE session_id = ?"
            params = (session_id,)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params = (*params, limit)
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            TaskRecord(
                task_id=r["task_id"],
                session_id=r["session_id"],
                user_goal=r["user_goal"],
                plan=json.loads(r["plan_json"] or "[]"),
                answer=r["answer"] or "",
                citations=json.loads(r["citations_json"] or "[]"),
                trace=json.loads(r["trace_json"] or "[]"),
                reflection=r["reflection"] or "",
                exports=json.loads(r["exports_json"] or "[]"),
                status=r["status"] or "",
                iterations=int(r["iterations"] or 0),
                created_at=r["created_at"] or "",
            )
            for r in rows
        ]

    def append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        task_id: str | None = None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO session_turns (session_id, role, content, task_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, task_id, _utc_now()),
            )

    def session_history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, task_id, created_at
                FROM session_turns
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            {
                "role": r["role"],
                "content": r["content"],
                "task_id": r["task_id"],
                "created_at": r["created_at"],
            }
            for r in reversed(rows)
        ]


@lru_cache
def get_session_memory() -> SessionMemory:
    return SessionMemory()


@lru_cache
def get_task_store() -> TaskStore:
    settings = get_settings()
    return TaskStore(settings.memory_path)


def new_task_id() -> str:
    return str(uuid4())
