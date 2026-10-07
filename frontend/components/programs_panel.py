from __future__ import annotations

import pandas as pd
import streamlit as st

from frontend.api_client import ApiError, DocAgentClient
from frontend.kaoyan_view import fact_lines, program_rows, unknown_rows

SCHOOLS = {"全部": None, "中山大学": "sysu", "华南理工大学": "scut", "暨南大学": "jnu", "华南师范大学": "scnu"}
TRISTATE = {"不限": None, "是": True, "否": False}
LINK_COLUMNS = ("复试线来源", "计划来源", "科目来源")


def _filters() -> dict[str, object]:
    c1, c2, c3, c4 = st.columns(4)
    school = c1.selectbox("学校", list(SCHOOLS))
    degree = c2.selectbox("学位类型", ["不限", "学硕", "专硕"])
    mode = c3.selectbox("学习方式", ["不限", "全日制", "非全日制"])
    is_408 = c4.selectbox("考 408", list(TRISTATE))
    c5, c6, c7, c8 = st.columns(4)
    code = c5.text_input("专业代码", placeholder="085404 或 0812")
    name_kw = c6.text_input("名称关键词", placeholder="人工智能")
    min_plan = c7.number_input("统招 ≥", min_value=0, value=0, step=1)
    year = c8.selectbox("年份", ["不限", 2027, 2026])
    return {
        "school": SCHOOLS[school],
        "degree_type": None if degree == "不限" else degree,
        "study_mode": None if mode == "不限" else mode,
        "is_408": TRISTATE[is_408],
        "code": code.strip() or None,
        "name_kw": name_kw.strip() or None,
        "min_public_plan": int(min_plan) or None,
        "year": None if year == "不限" else year,
    }


def render_programs(client: DocAgentClient) -> None:
    st.subheader("专业筛选")
    st.caption("数据来自 /v1/programs：每个数字都带年份和口径，来源列可直接打开官方页面。"
               "“未取得”表示官方来源没拿到，不是 0。")
    filters = _filters()
    try:
        payload = client.list_programs(**filters)
    except ApiError as exc:
        st.error(f"{exc.code}：{exc.message}")
        return

    rows = program_rows(payload)
    st.markdown(f"**{payload.get('count', len(rows))} 个专业**")
    if payload.get("public_plan_rule"):
        st.info(payload["public_plan_rule"])
    if rows:
        frame = pd.DataFrame(rows).drop(columns=["program_id"])
        st.dataframe(
            frame,
            hide_index=True,
            use_container_width=True,
            column_config={c: st.column_config.LinkColumn(c, display_text="打开") for c in LINK_COLUMNS},
        )
    unknown = unknown_rows(payload)
    if unknown:
        st.markdown("**无法判定的专业**（统招只有上限 / 合计等，不能当作满足条件）")
        st.dataframe(pd.DataFrame(unknown), hide_index=True, use_container_width=True)
    if payload.get("scope_note"):
        st.caption(payload["scope_note"])
    if not rows:
        return

    labels = [f"{r['学校']} · {r['学院']} · {r['专业']}" for r in rows]
    pick = st.selectbox("查看专业详情", options=list(range(len(rows))), format_func=lambda i: labels[i])
    program = (payload.get("programs") or [])[pick]
    st.markdown("\n".join(fact_lines(program)) or "（没有事实）")
    if program.get("notes"):
        with st.expander("备注（种子包原文）"):
            st.write(program["notes"])
