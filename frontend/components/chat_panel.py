from __future__ import annotations

import time
from typing import Any

import streamlit as st

from frontend.api_client import ApiError, DocAgentClient
from frontend.components.trace_panel import render_trace

POLL_SECONDS = 2
POLL_LIMIT = 90


def _append(role: str, content: str, meta: dict[str, Any] | None = None) -> None:
    st.session_state.messages.append({"role": role, "content": content, "meta": meta or {}})


def _poll_task(client: DocAgentClient, task_id: str) -> dict[str, Any]:
    box = st.empty()
    last: dict[str, Any] = {"task_id": task_id, "status": "queued"}
    for _ in range(POLL_LIMIT):
        last = client.get_task(task_id)
        status = last.get("status") or "unknown"
        box.info(f"任务 {task_id} · {status}")
        if status in {"done", "error"}:
            box.empty()
            return last
        time.sleep(POLL_SECONDS)
    box.warning(f"轮询超时，任务仍为 {last.get('status')}。可到任务中心用 task_id 继续查看。")
    return last


def send_message(client: DocAgentClient, message: str, *, async_mode: bool, max_tool_calls: int) -> None:
    message = message.strip()
    if not message:
        return
    _append("user", message)
    session_id = st.session_state.session_id.strip() or None
    try:
        if async_mode:
            queued = client.chat_async(message, session_id, max_tool_calls=max_tool_calls)
            st.session_state.session_id = queued.get("session_id") or st.session_state.session_id
            task = _poll_task(client, queued["task_id"])
            status = task.get("status") or ""
            if status == "error":
                _append("assistant", task.get("answer") or "任务失败", task)
            else:
                _append("assistant", task.get("answer") or "（无回答）", task)
        else:
            result = client.chat(message, session_id, max_tool_calls=max_tool_calls)
            st.session_state.session_id = result.get("session_id") or st.session_state.session_id
            _append("assistant", result.get("answer") or "（无回答）", result)
    except ApiError as exc:
        _append("assistant", f"{exc.code}：{exc.message}", {"status": "error", "code": exc.code})


def render_chat(client: DocAgentClient, *, async_mode: bool, max_tool_calls: int) -> None:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                render_trace(msg.get("meta"))

    draft = st.session_state.pop("draft_question", "")
    prompt = st.chat_input("问文档里的问题", key="chat_input")
    if draft and not prompt:
        prompt = draft
    if prompt:
        send_message(client, prompt, async_mode=async_mode, max_tool_calls=max_tool_calls)
        st.rerun()
