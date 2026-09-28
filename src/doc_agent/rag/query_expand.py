from __future__ import annotations

import re
from typing import Iterable


# Intent → extra lexical queries that match annual-report section wording.
_INTENT_EXPANSIONS: list[tuple[tuple[str, ...], list[str]]] = [
    (
        ("主营业务", "营收构成", "业务构成", "收入构成", "产品结构"),
        [
            "主营业务分行业",
            "主营业务分地区",
            "产品情况",
            "营业收入主要来自",
            "茅台酒及系列酒",
        ],
    ),
    (
        ("风险", "主要风险", "风险因素", "重大风险"),
        [
            "可能面对的风险",
            "重大风险提示",
            "公司未来发展的讨论与分析",
        ],
    ),
    (
        ("管理层讨论", "经营情况", "经营分析"),
        [
            "第三节 管理层讨论与分析",
            "报告期内主要经营情况",
            "行业经营性信息分析",
        ],
    ),
]

# Phrase boosts only fire when the query matches the same intent family.
_PHRASE_BOOSTS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("主营", "业务", "营收", "产品", "收入"),
        (
            "主营业务分行业",
            "主营业务分地区",
            "产品情况",
            "营业收入主要来自",
            "茅台酒及系列酒",
        ),
    ),
    (
        ("风险",),
        (
            "可能面对的风险",
            "重大风险提示",
            "宏观经济风险",
            "安全风险",
            "舆情风险",
            "环境保护风险",
        ),
    ),
    (
        ("管理层", "经营分析", "经营情况"),
        (
            "管理层讨论与分析",
            "行业经营性信息分析",
            "报告期内主要经营情况",
        ),
    ),
]


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
    from doc_agent.kaoyan.normalize import find_schools

    schools = find_schools(query)
    return schools[0] if len(schools) == 1 else None


def _expand_kaoyan(q: str, max_queries: int) -> list[str]:
    from doc_agent.kaoyan.normalize import DEFAULT_SCHOOL_ALIASES, find_schools

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


def expand_queries(query: str, *, max_queries: int = 10, profile: str = "enterprise") -> list[str]:
    """Return original query plus section-oriented expansions (balanced across intents)."""
    q = (query or "").strip()
    if not q:
        return []
    if profile == "kaoyan":
        return _expand_kaoyan(q, max_queries)
    out = [q]
    seen = {q}
    # Collect matched intent extras first, then round-robin so one intent cannot dominate.
    buckets: list[list[str]] = []
    for triggers, extras in _INTENT_EXPANSIONS:
        if any(t in q for t in triggers):
            buckets.append([e for e in extras if e not in seen])
    idx = 0
    while len(out) < max_queries and any(buckets):
        progressed = False
        for bucket in buckets:
            if idx < len(bucket):
                e = bucket[idx]
                if e not in seen:
                    seen.add(e)
                    out.append(e)
                    progressed = True
                    if len(out) >= max_queries:
                        break
        if not progressed:
            break
        idx += 1
    return out


def infer_doc_name(query: str, doc_names: Iterable[str]) -> str | None:
    """Heuristic: pin search to a document mentioned in the query."""
    q = query or ""
    names = list(doc_names)
    rules = [
        (("茅台", "600519"), ("茅台",)),
        (("五粮液", "000858"), ("五粮液",)),
        (("宁德", "300750"), ("宁德",)),
        (("人权", "宣言"), ("人权宣言", "UDHR", "OHCHR")),
        (("参数手册", "DocMind"), ("参数手册", "产品参数")),
        (("文档管理制度", "保密等级", "保存期限"), ("文档管理制度",)),
    ]
    for needles, name_keys in rules:
        if any(n in q for n in needles):
            for name in names:
                if any(k in name for k in name_keys):
                    return name
    if "年报" in q or "年度报告" in q:
        reports = [n for n in names if "年报" in n or "年度报告" in n]
        if len(reports) == 1:
            return reports[0]
    return None


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


def keyword_boost(query: str, text: str, *, profile: str = "enterprise") -> float:
    """Small additive boost for intent-aligned exact phrases."""
    if not query or not text:
        return 0.0
    if profile == "kaoyan":
        codes = _PROGRAM_CODE.findall(query)
        boost = 0.02 * sum(1 for c in codes if c in text)
        terms = re.findall(r"[\u4e00-\u9fff]{2,8}|[a-zA-Z0-9_]{2,}", query)
        if terms:
            boost += 0.01 * (sum(1 for t in terms if t in text) / len(terms))
        return boost
    boost = 0.0
    for triggers, phrases in _PHRASE_BOOSTS:
        if not any(t in query for t in triggers):
            continue
        for p in phrases:
            if p in text:
                boost += 0.15
    terms = re.findall(r"[\u4e00-\u9fff]{2,8}|[a-zA-Z0-9_]{2,}", query)
    if terms:
        hit = sum(1 for t in terms if t in text)
        boost += 0.04 * (hit / max(len(terms), 1))
    return boost
