from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from doc_agent.agent.graph import run_agent
from doc_agent.memory import TaskRecord, get_task_store, new_task_id
from doc_agent.runtime_options import request_options

logger = logging.getLogger(__name__)


def enqueue_chat_job(
    *,
    message: str,
    session_id: str | None = None,
    max_tool_calls: int | None = None,
    temperature: float | None = None,
) -> tuple[str, str]:
    """Persist a queued task row and return (task_id, session_id)."""
    sid = session_id or str(uuid4())
    task_id = new_task_id()
    store = get_task_store()
    record = TaskRecord(
        task_id=task_id,
        session_id=sid,
        user_goal=message,
        plan=[],
        answer="",
        citations=[],
        trace=[],
        reflection="",
        exports=[],
        status="queued",
        iterations=0,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.save_task(record)
    # stash options in reflection prefix for worker (lightweight; options also passed to worker)
    _ = (max_tool_calls, temperature)
    return task_id, sid


def run_chat_job(
    *,
    task_id: str,
    session_id: str,
    message: str,
    max_tool_calls: int | None = None,
    temperature: float | None = None,
) -> None:
    store = get_task_store()
    existing = store.get_task(task_id)
    created_at = (
        existing.created_at if existing else datetime.now(timezone.utc).isoformat()
    )
    store.save_task(
        TaskRecord(
            task_id=task_id,
            session_id=session_id,
            user_goal=message,
            plan=[],
            answer="",
            citations=[],
            trace=[],
            reflection="",
            exports=[],
            status="running",
            iterations=0,
            created_at=created_at,
        )
    )
    try:
        with request_options(max_tool_calls=max_tool_calls, temperature=temperature):
            result = run_agent(
                message,
                session_id=session_id,
                task_id=task_id,
                persist=True,
            )
        # run_agent already saved done status; ensure created_at preserved if overwritten
        saved = store.get_task(task_id)
        if saved and created_at and saved.created_at != created_at:
            saved.created_at = created_at
            store.save_task(saved)
        logger.info("async chat job done task_id=%s status=%s", task_id, result.get("status"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("async chat job failed task_id=%s", task_id)
        store.save_task(
            TaskRecord(
                task_id=task_id,
                session_id=session_id,
                user_goal=message,
                plan=[],
                answer="",
                citations=[],
                trace=[],
                reflection=str(exc),
                exports=[],
                status="error",
                iterations=0,
                created_at=created_at,
            )
        )
