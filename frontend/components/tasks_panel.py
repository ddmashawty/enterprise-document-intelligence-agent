from __future__ import annotations

import pandas as pd
import streamlit as st

from frontend.api_client import ApiError, DocAgentClient
from frontend.components.trace_panel import render_trace


def render_tasks(client: DocAgentClient) -> None:
    st.subheader("任务中心")
    session_id = st.session_state.session_id.strip()
    only_session = st.checkbox("只看当前会话", value=bool(session_id))
    try:
        payload = client.list_tasks(session_id if only_session and session_id else None, limit=30)
    except ApiError as exc:
        st.error(f"{exc.code}：{exc.message}")
        return

    tasks = payload.get("tasks") or []
    if not tasks:
        st.info("还没有任务。先在对话里提问。")
        return

    rows = [
        {
            "task_id": t.get("task_id", ""),
            "status": t.get("status", ""),
            "created_at": t.get("created_at", ""),
            "goal": (t.get("user_goal") or "")[:80],
        }
        for t in tasks
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    labels = [f"{r['status']} · {r['goal'] or r['task_id']}" for r in rows]
    pick = st.selectbox("查看任务", options=list(range(len(tasks))), format_func=lambda i: labels[i])
    task = tasks[pick]
    st.markdown(task.get("answer") or "（尚无回答）")
    render_trace(task)

    if session_id:
        st.subheader("会话时间线")
        try:
            history = client.get_session(session_id)
        except ApiError as exc:
            st.error(f"{exc.code}：{exc.message}")
            return
        for turn in history.get("turns") or []:
            role = turn.get("role") or "turn"
            content = (turn.get("content") or "")[:500]
            st.markdown(f"**{role}**  \n{content}")
