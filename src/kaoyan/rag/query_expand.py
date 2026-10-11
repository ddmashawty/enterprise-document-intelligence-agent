from __future__ import annotations

import re


# 考研 intents: extra wording used by official notices, appended to the query.
_KAOYAN_EXPANSIONS: list[tuple[tuple[str, ...], str]] = [
    (("复试线", "分数线", "复试分数", "过线", "进复试"), "复试分数线 复试基本分数线 总分 单科"),
    (("招多少", "招几", "招生人数", "计划", "名额", "统招", "统考"), "拟招生人数 招生计划 公开招考"),
    (("推免", "保研", "免试"), "推免生 接收推荐免试 已招推免"),
    (("考什么", "初试科目", "考试科目", "考不考", "408", "专业课"), "初试科目 考试科目 计算机学科专业基础"),
    (("方向", "导师"), "研究方向 导师"),
    (("学费", "费用"), "学费标准"),
]
# Intent → doc types that usually answer it (small prior, never a filter).
_KAOYAN_DOC_TYPES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("复试线", "分数线", "复试分数", "过线", "进复试"), ("retest_rules", "score_line")),
    (("招多少", "招几", "招生人数", "计划", "名额", "统招", "统考"), ("catalog", "plan_quota", "retest_rules", "brochure")),
    (("推免", "保研", "免试"), ("tm_catalog", "tm_policy", "retest_rules")),
    (("考什么", "初试科目", "考试科目", "考不考", "408", "专业课"), ("catalog", "subject_change")),
]
_PROGRAM_CODE = re.compile(r"(?<![0-9A-Z])(?:\d{6}|\d{4}[A-Z]\d)(?![0-9A-Z])")


def infer_school(query: str) -> str | None:
    """School id when the query names exactly one school (中大 → sysu)."""
    from kaoyan.normalize import find_schools

    schools = find_schools(query)
    return schools[0] if len(schools) == 1 else None


def _expand_kaoyan(q: str, max_queries: int) -> list[str]:
    from kaoyan.normalize import DEFAULT_SCHOOL_ALIASES, find_schools

    out = [q]
    full = [DEFAULT_SCHOOL_ALIASES[s][0] for s in find_schools(q) if DEFAULT_SCHOOL_ALIASES[s][0] not in q]
    if full:
        out.append(f"{q} {' '.join(full)}")
    base = out[-1]
    for triggers, extra in _KAOYAN_EXPANSIONS:
        if len(out) >= max_queries:
            break
        if any(t in q for t in triggers):
            out.append(f"{base} {extra}")
    return out


def expand_queries(query: str, *, max_queries: int = 10) -> list[str]:
    """Original query plus the wording official notices use for the same intent."""
    q = (query or "").strip()
    return _expand_kaoyan(q, max_queries) if q else []


def kaoyan_prior(query: str, meta: dict) -> float:
    """Score multiplier from chunk metadata: name lists (redacted) rarely answer questions,
    doc types matching the query intent get a small lift."""
    factor = 0.5 if meta.get("redacted") else 1.0
    doc_type = meta.get("doc_type")
    if doc_type and any(doc_type in types and any(t in query for t in triggers) for triggers, types in _KAOYAN_DOC_TYPES):
        factor *= 1.2
    college = re.sub(r"^\d+|[（(].*$", "", str(meta.get("college") or "")).strip()
    if len(college) >= 3 and college.endswith(("学院", "研究院")) and college in query:
        factor *= 1.2
    return factor


def keyword_boost(query: str, text: str) -> float:
    """Small additive boost for program codes and query terms found verbatim in the chunk."""
    if not query or not text:
        return 0.0
    codes = _PROGRAM_CODE.findall(query)
    boost = 0.02 * sum(1 for c in codes if c in text)
    terms = re.findall(r"[\u4e00-\u9fff]{2,8}|[a-zA-Z0-9_]{2,}", query)
    if terms:
        boost += 0.01 * (sum(1 for t in terms if t in text) / len(terms))
    return boost
