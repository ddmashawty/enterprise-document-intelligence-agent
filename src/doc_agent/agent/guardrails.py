from __future__ import annotations

import json
import re
from typing import Any

from doc_agent.rag.store import get_store


EXPORT_HINTS = ("导出", "excel", "Excel", "xlsx", "markdown", "Markdown", "报告文件", "落盘")
COMPARE_HINTS = ("对比", "比较", "分别列出", "vs", "VS")
EXCEL_HINTS = ("excel", "xlsx", "Excel", "电子表格")


def wants_export(goal: str) -> bool:
    return any(k in goal for k in EXPORT_HINTS)


def wants_excel(goal: str) -> bool:
    g = goal.lower()
    return any(k.lower() in g for k in EXCEL_HINTS) or ("表格" in goal and "导出" in goal)


def wants_compare(goal: str) -> bool:
    return any(k in goal for k in COMPARE_HINTS)


def infer_export_filename(goal: str) -> str:
    m = re.search(r"文件名\s*[：:]?\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)", goal)
    if m:
        return m.group(1)
    if wants_excel(goal):
        return "export_table"
    return "export_report"


def tool_call_count(results: list[dict[str, Any]], name: str) -> int:
    return sum(1 for r in results if r.get("tool") == name)


def recent_tools(results: list[dict[str, Any]], n: int = 5) -> list[str]:
    return [str(r.get("tool") or "") for r in results[-n:]]


def is_list_documents_spin(results: list[dict[str, Any]]) -> bool:
    recent = recent_tools(results, 4)
    if len(recent) < 3:
        return False
    return all(t == "list_documents" for t in recent)


def resolve_compare_doc_names(goal: str) -> list[str]:
    """Map Chinese aliases in the goal to ingested doc_name values."""
    docs = get_store().list_documents()
    names = [str(d.get("doc_name") or "") for d in docs if d.get("doc_name")]
    if len(names) < 2:
        return names

    picked: list[str] = []

    def add_matching(*needles: str) -> None:
        for name in names:
            if name in picked:
                continue
            if any(n in name for n in needles):
                picked.append(name)

    # Explicit pairs commonly used in verification
    if "手册" in goal or "参数" in goal:
        add_matching("手册", "参数")
    if "制度" in goal or "管理" in goal or "保存" in goal or "保密" in goal:
        add_matching("制度", "管理")
    if "茅台" in goal:
        add_matching("茅台")
    if "五粮液" in goal:
        add_matching("五粮液")
    if "宁德" in goal:
        add_matching("宁德")
    if "人权" in goal:
        add_matching("人权", "OHCHR")

    # Fallback: first two non-annual + any mentioned
    if len(picked) < 2:
        for name in names:
            if name not in picked:
                picked.append(name)
            if len(picked) >= 2:
                break
    return picked[:4]


def citations_to_markdown(goal: str, citations: list[dict[str, Any]], title: str) -> str:
    lines = [f"# {title}", "", f"> 用户目标：{goal}", "", "## 依据摘录", ""]
    for i, c in enumerate(citations[:8], start=1):
        doc = c.get("doc_name") or c.get("source") or "unknown"
        page = c.get("page", "?")
        text = (c.get("text") or "").strip().replace("\n", " ")[:400]
        lines.append(f"{i}. **{doc}** p.{page}")
        lines.append(f"   {text}")
        lines.append("")
    lines.append("## 说明")
    lines.append("本文件由 Agent 根据检索证据自动导出；请以原文为准。")
    return "\n".join(lines)


def citations_to_excel_rows(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for c in citations[:30]:
        rows.append(
            {
                "文档": c.get("doc_name") or c.get("source") or "",
                "页码": c.get("page", ""),
                "摘录": (c.get("text") or "").strip().replace("\n", " ")[:500],
                "分数": c.get("score", ""),
            }
        )
    if not rows:
        rows = [{"文档": "", "页码": "", "摘录": "无可用摘录", "分数": ""}]
    return rows


def filter_redundant_tool_calls(
    tool_calls: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop repeated list_documents and duplicate identical calls in one turn."""
    out: list[dict[str, Any]] = []
    listed = tool_call_count(results, "list_documents") > 0
    seen: set[str] = set()
    for call in tool_calls:
        name = call.get("name") or ""
        args = call.get("args") or {}
        key = f"{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}"
        if key in seen:
            continue
        if name == "list_documents" and listed:
            continue
        if name == "list_documents":
            listed = True
        seen.add(key)
        out.append(call)
    return out


# -- 考研 intent ------------------------------------------------------------

PROGRAM_CODE_RE = re.compile(r"(?<![0-9A-Za-z])((?:0[1-9]|1[0-4])\d{2}[0-9A-Z]{2})(?![0-9A-Za-z])")
DISCIPLINE_RE = re.compile(r"(?<![0-9A-Za-z])((?:0[1-9]|1[0-4])\d{2})(?![0-9A-Za-z])")
YEAR_RE = re.compile(r"(?<!\d)(20[2-3]\d)(?!\d)")
COLLEGE_RE = re.compile(r"([\u4e00-\u9fff]{2,14}?学院)")
KAOYAN_STRONG_HINTS = (
    "复试", "推免", "统招", "统考", "考研", "招生", "研究生", "硕士", "408", "初试", "拟录取",
    "专硕", "学硕", "调剂", "分数线", "研招", "招多少", "考什么",
)
_KIND_HINTS: dict[str, tuple[str, ...]] = {
    "score_line": ("复试线", "分数线", "国家线", "校线", "基本线", "多少分", "进复试"),
    "plan": ("招多少", "招几", "多少人", "几个人", "计划", "名额", "统招", "统考招", "推免多少", "公开招考", "拟招"),
    "subjects": ("考什么", "考不考", "考408", "考 408", "初试科目", "科目", "专业课", "考哪"),
    "compare": ("对比", "比较", "相比", "vs", "VS"),
    "filter": ("哪些", "筛选", "有哪些", "哪几个", "列出所有"),
    "directions": ("有没有", "方向"),
}
_PRIVACY_RE = re.compile(
    r"(名单|录取|复试名单|拟录取).{0,12}(有没有|是否有|查|找|姓名|名字|编号|某某)|考生编号|准考证|姓名|个人成绩"
)
_THRESHOLD_RE = re.compile(
    r"(统招|统考|公开招考)[^0-9]{0,6}?(>=|≥|>|＞|大于等于|大于|超过|多于|不少于|至少)\s*(\d+)"
)
_NAME_KW_RE = re.compile(r"有没有([\u4e00-\u9fffA-Za-z]{2,12}?)(?:学硕|专硕|专业|方向|学位|[（(？?，,]|$)")
_COLLEGE_PREFIX_STRIP = "的在查看问请帮我"


def _strip_school_aliases(text: str) -> str:
    from doc_agent.kaoyan.normalize import DEFAULT_SCHOOL_ALIASES

    out = text
    for names in DEFAULT_SCHOOL_ALIASES.values():
        for alias in sorted(names, key=len, reverse=True):
            out = out.replace(alias, " ")
    return out


def detect_kaoyan_intent(goal: str) -> dict[str, Any]:
    """Rule-based 考研 intent: schools, program codes, colleges, year, question kinds, filters."""
    from doc_agent.kaoyan.normalize import find_schools

    text = goal or ""
    schools = find_schools(text)
    codes = list(dict.fromkeys(PROGRAM_CODE_RE.findall(text)))
    masked = PROGRAM_CODE_RE.sub(" ", text)
    prefixes = [p for p in dict.fromkeys(DISCIPLINE_RE.findall(masked)) if not YEAR_RE.fullmatch(p)]
    colleges = []
    for m in COLLEGE_RE.finditer(_strip_school_aliases(text)):
        name = m.group(1).lstrip(_COLLEGE_PREFIX_STRIP)
        if len(name) > 2:
            colleges.append(name)
    years = [int(y) for y in YEAR_RE.findall(text)]
    is_kaoyan = bool(schools or codes or any(k in text for k in KAOYAN_STRONG_HINTS))

    kinds = [k for k, hints in _KIND_HINTS.items() if any(h in text for h in hints)]
    if "四校" in text and "compare" not in kinds and ("复试线" in text or "计划" in text):
        kinds.append("compare")
    privacy = bool(_PRIVACY_RE.search(text))
    if privacy:
        kinds.append("privacy")
    if wants_export(text):
        kinds.append("export")
    if not kinds:
        kinds.append("narrative")

    filters: dict[str, Any] = {}
    if "filter" in kinds or "compare" in kinds:
        if re.search(r"不考\s*408", text):
            filters["is_408"] = False
        elif "408" in text:
            filters["is_408"] = True
        if "非全日制" in text or "非全" in text:
            filters["study_mode"] = "非全日制"
        elif "全日制" in text:
            filters["study_mode"] = "全日制"
        if "学硕" in text and "专硕" not in text:
            filters["degree_type"] = "学硕"
        elif "专硕" in text and "学硕" not in text:
            filters["degree_type"] = "专硕"
    m = _THRESHOLD_RE.search(text)
    if m:
        n = int(m.group(3))
        strict = m.group(2) in (">", "＞", "大于", "超过", "多于")
        filters["min_public_plan"] = n + 1 if strict else n
        if "filter" not in kinds:
            kinds.append("filter")
    name_kw = None
    if not privacy:
        nm = _NAME_KW_RE.search(text)
        if nm:
            name_kw = nm.group(1)

    numeric = bool(set(kinds) & {"score_line", "plan", "filter", "compare"})
    return {
        "is_kaoyan": is_kaoyan,
        "schools": schools,
        "codes": codes,
        "prefixes": prefixes,
        "colleges": colleges,
        "year": years[0] if years else None,
        "kinds": kinds,
        "numeric": numeric,
        "privacy": privacy,
        "export": "export" in kinds,
        "filters": filters,
        "name_kw": name_kw,
    }


# -- number validation --------------------------------------------------------

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_PROTECTED_RES = (
    PROGRAM_CODE_RE,
    re.compile(r"(?<![0-9A-Za-z.])0[1-9]\d{2}(?![0-9A-Za-z])"),
    re.compile(r"https?://\S+"),
    re.compile(r"[A-Za-z0-9.-]+\.(?:edu|com|cn|org|net)(?:\.cn)?(?:/[^\s，。；）)]*)?"),
    re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*\d[A-Za-z0-9_\-]*(?:\.[A-Za-z]{2,5})?"),
    re.compile(r"(?m)^\s*\d+[.、)）]\s"),
    re.compile(r"第\s*\d+"),
)


def _canon(token: str) -> str:
    if "." in token:
        return token.rstrip("0").rstrip(".") or "0"
    return str(int(token))


def _is_exempt_number(token: str) -> bool:
    return len(token) == 4 and "." not in token and 1990 <= int(token) <= 2035


def _protected_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for rx in _PROTECTED_RES:
        spans.extend(m.span() for m in rx.finditer(text))
    return spans


def _unsupported_matches(answer: str, evidence: str) -> list[re.Match[str]]:
    known = {_canon(t) for t in _NUMBER_RE.findall(evidence)}
    spans = _protected_spans(answer)
    out = []
    for m in _NUMBER_RE.finditer(answer):
        if any(s <= m.start() and m.end() <= e for s, e in spans):
            continue
        tok = m.group()
        if _is_exempt_number(tok) or _canon(tok) in known:
            continue
        out.append(m)
    return out


def find_unsupported_numbers(answer: str, evidence: str) -> list[str]:
    """Numbers in the answer that do not occur in the evidence. Years, program codes,
    discipline codes (0812), URLs/file names and list ordinals are exempt."""
    return list(dict.fromkeys(m.group() for m in _unsupported_matches(answer, evidence)))


def strip_unsupported_numbers(answer: str, evidence: str, marker: str = "（依据不足）") -> str:
    out = answer
    for m in reversed(_unsupported_matches(answer, evidence)):
        out = out[: m.start()] + marker + out[m.end() :]
    return out
