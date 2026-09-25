from __future__ import annotations

import json
from typing import Any

import streamlit as st


def _pretty(value: Any, limit: int = 4000) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) > limit:
        return text[:limit] + "\n…[truncated]"
    return text


def render_trace(meta: dict[str, Any] | None) -> None:
    if not meta:
        return
    plan = meta.get("plan") or []
    reflection = meta.get("reflection") or ""
    citations = meta.get("citations") or []
    exports = meta.get("exports") or []
    trace = meta.get("trace") or []
    status = meta.get("status") or ""
    task_id = meta.get("task_id") or ""
    iterations = meta.get("iterations")

    bits = [b for b in [status, f"task {task_id}" if task_id else "", f"{iterations} 轮" if iterations else ""] if b]
    if bits:
        st.caption(" · ".join(bits))

    if plan:
        with st.expander("Plan", expanded=False):
            for i, step in enumerate(plan, start=1):
                st.markdown(f"{i}. {step}")
    if reflection:
        with st.expander("Reflection", expanded=False):
            st.write(reflection)
    if citations:
        with st.expander(f"Citations ({len(citations)})", expanded=False):
            for i, cite in enumerate(citations[:12], start=1):
                doc = cite.get("doc_name") or cite.get("source") or "unknown"
                page = cite.get("page", "?")
                text = (cite.get("text") or "")[:360]
                st.markdown(f"**{i}. {doc} p.{page}**")
                st.text(text)
    if exports:
        with st.expander("Exports", expanded=True):
            for item in exports:
                path = item.get("path") or ""
                st.code(path or _pretty(item, 500))
                st.caption("文件在后端 data/exports，路径相对仓库根目录。")
    if trace:
        with st.expander(f"Trace ({len(trace)})", expanded=False):
            for i, step in enumerate(trace, start=1):
                name = step.get("tool") or "tool"
                st.markdown(f"**{i}. {name}**")
                args = step.get("args") or {}
                st.caption(_pretty(args, 500))
                st.text(_pretty(step.get("output"), 1200))
