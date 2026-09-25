from __future__ import annotations

import sys
import uuid
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend.api_client import ApiError, DocAgentClient
from frontend.components.chat_panel import render_chat
from frontend.components.ingest_panel import render_ingest
from frontend.components.tasks_panel import render_tasks

DEMO_QUESTIONS = [
    "演示产品手册里 TopK 和切片大小分别是多少？",
    "普通文档的保存期限是多久？",
    "保密等级分为哪几级？",
    "贵州茅台 2024 年报的主营业务和主要风险是什么？",
    "对比演示产品参数手册和演示企业文档管理制度的要点",
    "保密等级分为哪几级？导出 Excel，文件名 demo_secrecy",
]


def _init_state() -> None:
    st.session_state.setdefault("session_id", f"ui-{uuid.uuid4().hex[:8]}")
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("base_url", "http://127.0.0.1:8000")
    st.session_state.setdefault("async_mode", False)
    st.session_state.setdefault("max_tool_calls", 5)


def _sidebar_controls() -> None:
    st.sidebar.header("连接")
    st.session_state.base_url = st.sidebar.text_input("API Base URL", st.session_state.base_url)


def _prefer_local_agent() -> None:
    """Before the URL widget is drawn, leave 8000 when another process owns it."""
    if st.session_state.get("port_checked"):
        return
    st.session_state.port_checked = True
    if st.session_state.base_url.rstrip("/") != "http://127.0.0.1:8000":
        return
    try:
        DocAgentClient(st.session_state.base_url).health()
        return
    except ApiError as exc:
        if exc.code != "wrong_service":
            return
    alt = DocAgentClient("http://127.0.0.1:8001")
    try:
        alt.health()
    except ApiError:
        return
    st.session_state.base_url = alt.base_url
    st.session_state.port_notice = "8000 被其他服务占用，已改连本项目的 8001。"


def _connect() -> DocAgentClient:
    client = DocAgentClient(st.session_state.base_url)
    try:
        st.session_state.health = client.health()
        st.session_state.health_error = None
    except ApiError as exc:
        st.session_state.health = None
        st.session_state.health_error = exc
    return client


def _sidebar_health(client: DocAgentClient) -> None:
    health = st.session_state.get("health")
    notice = st.session_state.get("port_notice") or ""
    if notice:
        st.sidebar.info(notice)
    err = st.session_state.get("health_error")
    if err:
        st.sidebar.error(f"{err.code}：{err.message}")
    if health:
        st.sidebar.success(
            f"{health.get('status')} · {health.get('version')} · "
            f"llm {health.get('llm')} · {health.get('chunks')} chunks"
        )
        st.sidebar.caption(str(health.get("retrieval_backend") or ""))

    st.sidebar.header("会话")
    st.session_state.session_id = st.sidebar.text_input("session_id", st.session_state.session_id)
    if st.sidebar.button("新建会话"):
        st.session_state.session_id = f"ui-{uuid.uuid4().hex[:8]}"
        st.session_state.messages = []
        st.rerun()

    mode = st.sidebar.radio("模式", ["同步 Chat", "异步 Chat"], index=1 if st.session_state.async_mode else 0)
    st.session_state.async_mode = mode == "异步 Chat"
    st.session_state.max_tool_calls = st.sidebar.slider(
        "max_tool_calls",
        min_value=1,
        max_value=5,
        value=int(st.session_state.max_tool_calls),
    )
    st.sidebar.caption("异步任务在单个 uvicorn 进程内执行，不要开多 worker。")


def _demo_tab() -> None:
    st.subheader("演示剧本")
    st.caption("点一条问句，会填入对话并发送。")
    for question in DEMO_QUESTIONS:
        if st.button(question, use_container_width=True):
            st.session_state.draft_question = question
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="文档智能 Agent", layout="wide")
    _init_state()
    _prefer_local_agent()
    _sidebar_controls()
    client = _connect()
    _sidebar_health(client)
    st.title("企业文档智能处理")
    st.caption(f"API {st.session_state.base_url} · 本地演示，不要暴露到公网。")
    err = st.session_state.get("health_error")
    if err:
        st.error(f"{err.code}：{err.message}")
    notice = st.session_state.get("port_notice")
    if notice:
        st.info(notice)

    tab_chat, tab_kb, tab_tasks, tab_demo = st.tabs(["对话", "知识库", "任务中心", "演示剧本"])
    with tab_chat:
        render_chat(
            client,
            async_mode=st.session_state.async_mode,
            max_tool_calls=int(st.session_state.max_tool_calls),
        )
    with tab_kb:
        render_ingest(client)
    with tab_tasks:
        render_tasks(client)
    with tab_demo:
        _demo_tab()


if __name__ == "__main__":
    main()
