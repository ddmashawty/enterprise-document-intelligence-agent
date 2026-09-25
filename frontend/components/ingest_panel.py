from __future__ import annotations

from pathlib import Path

import streamlit as st

from frontend.api_client import ApiError, DocAgentClient

UPLOAD_DIR = Path("data/uploads")


def render_ingest(client: DocAgentClient) -> None:
    st.subheader("导入")
    path = st.text_input("文档或目录路径", value="data/raw", help="相对仓库根目录，支持 PDF、DOCX、TXT、Markdown")
    reindex = st.checkbox("重建索引（清空后重导）", value=False)
    upload = st.file_uploader("或上传文件", type=["pdf", "docx", "txt", "md"])
    if st.button("开始导入", type="primary"):
        paths = [path.strip()] if path.strip() else []
        if upload is not None:
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            dest = UPLOAD_DIR / upload.name
            dest.write_bytes(upload.getvalue())
            paths = [str(dest)]
        if not paths:
            st.warning("请填写路径或上传文件。")
            return
        try:
            result = client.ingest(paths, reindex=reindex)
        except ApiError as exc:
            st.error(f"{exc.code}：{exc.message}")
            return
        st.session_state.last_ingest = result
        st.success(
            f"已索引 {result.get('docs_indexed', 0)} 篇，"
            f"新增切片 {result.get('chunks_added', 0)}，"
            f"库内共 {result.get('chunks_total', 0)}。"
        )
        failed = result.get("docs_failed") or []
        if failed:
            st.warning("部分文件失败")
            st.json(failed)

    last = st.session_state.get("last_ingest")
    if last:
        with st.expander("最近一次导入", expanded=False):
            st.json(
                {
                    "docs_indexed": last.get("docs_indexed"),
                    "chunks_added": last.get("chunks_added"),
                    "chunks_total": last.get("chunks_total"),
                    "retrieval_backend": last.get("retrieval_backend"),
                    "files": last.get("files"),
                    "docs_failed": last.get("docs_failed"),
                }
            )
