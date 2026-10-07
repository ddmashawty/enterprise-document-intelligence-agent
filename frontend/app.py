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
from frontend.components.programs_panel import render_programs
from frontend.components.tasks_panel import render_tasks

# Acceptance cases of data/gold/kaoyan_qa.json (CURSOR_PROMPT section 6).
DEMO_QUESTIONS = [
    "中大计算机学院 085404 的 2026 复试线是多少？",
    "暨大网络空间安全学院 085412 的 2026 复试线？",
    "华师计算机学院 085404 复试线多少？",
    "中大网络空间安全学院 083900 考什么、复试线多少？",
    "华工计算机学院 085404 初试考什么？考不考 408？",
    "华工 140500 智能科学与技术考 408 吗？复试线？",
    "暨大 081203 计算机应用技术 2027 招多少人？",
    "中大人工智能学院 081200 招多少人？",
    "华师人工智能学院 085410 计划多少？",
    "中大软件工程学院 085405 推免多少、公开招考多少？",
    "哪些专业考 408、全日制、统招 > 20？",
    "对比四校 085404 的 2026 复试线",
    "中大 2027 年 085404 招多少人？",
    "华师有没有网络空间安全学硕（0839）？",
    "暨大智能科学与工程学院 0812Z3 统考招几个？",
    "中大电子与通信工程学院 085400 的人工智能方向考 408 吗？",
    "帮我查华工计算机学院拟录取名单里有没有某某某",
    "把四校 085404 的复试线和计划导出 Excel",
]

# 通用文档模式 (the original enterprise demo corpus under data/raw).
GENERIC_QUESTIONS = [
    "演示产品手册里 TopK 和切片大小分别是多少？",
    "保密等级分为哪几级？",
    "对比演示产品参数手册和演示企业文档管理制度的要点",
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
    st.caption("点一条问句，会填入对话并发送。期望答案见 data/gold/kaoyan_qa.json。")
    for i, question in enumerate(DEMO_QUESTIONS, start=1):
        if st.button(f"{i}. {question}", key=f"demo-{i}", use_container_width=True):
            st.session_state.draft_question = question
            st.rerun()
    with st.expander("通用文档模式（企业演示语料 data/raw）"):
        for i, question in enumerate(GENERIC_QUESTIONS, start=1):
            if st.button(question, key=f"generic-{i}", use_container_width=True):
                st.session_state.draft_question = question
                st.rerun()


def main() -> None:
    st.set_page_config(page_title="考研信息 Agent", layout="wide")
    _init_state()
    _prefer_local_agent()
    _sidebar_controls()
    client = _connect()
    _sidebar_health(client)
    st.title("广东四校计算机考研信息 Agent")
    st.caption(f"中大 / 华工 / 暨大 / 华师 · 每个数字带年份、口径和官方来源 · API {st.session_state.base_url} · "
               "本地演示，不要暴露到公网。")
    err = st.session_state.get("health_error")
    if err:
        st.error(f"{err.code}：{err.message}")
    notice = st.session_state.get("port_notice")
    if notice:
        st.info(notice)

    tab_chat, tab_programs, tab_kb, tab_tasks, tab_demo = st.tabs(["对话", "专业筛选", "知识库", "任务中心", "演示剧本"])
    with tab_chat:
        render_chat(
            client,
            async_mode=st.session_state.async_mode,
            max_tool_calls=int(st.session_state.max_tool_calls),
        )
    with tab_programs:
        render_programs(client)
    with tab_kb:
        render_ingest(client)
    with tab_tasks:
        render_tasks(client)
    with tab_demo:
        _demo_tab()


if __name__ == "__main__":
    main()
