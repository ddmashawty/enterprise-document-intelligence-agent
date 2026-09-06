from __future__ import annotations

from pathlib import Path

from doc_agent.memory import SessionMemory, TaskRecord, TaskStore


def test_session_memory_ring():
    mem = SessionMemory(max_turns=3)
    mem.append("s1", "user", "a")
    mem.append("s1", "assistant", "b")
    mem.append("s1", "user", "c")
    mem.append("s1", "assistant", "d")
    hist = mem.history("s1")
    assert len(hist) == 3
    assert hist[-1]["content"] == "d"


def test_task_store_roundtrip(tmp_path: Path):
    store = TaskStore(tmp_path / "t.db")
    rec = TaskRecord(
        task_id="t1",
        session_id="s1",
        user_goal="q",
        plan=["a"],
        answer="ans",
        citations=[{"doc_name": "x"}],
        trace=[{"tool": "rag_search"}],
        reflection="ok",
        exports=[],
        status="done",
        iterations=1,
        created_at="2026-01-01T00:00:00+00:00",
    )
    store.save_task(rec)
    got = store.get_task("t1")
    assert got is not None
    assert got.answer == "ans"
    assert got.citations[0]["doc_name"] == "x"
    store.append_turn("s1", "user", "q", task_id="t1")
    turns = store.session_history("s1")
    assert turns and turns[0]["role"] == "user"
