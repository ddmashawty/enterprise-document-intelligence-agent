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


def expand_queries(query: str, *, max_queries: int = 10) -> list[str]:
    """Return original query plus section-oriented expansions (balanced across intents)."""
    q = (query or "").strip()
    if not q:
        return []
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


def keyword_boost(query: str, text: str) -> float:
    """Small additive boost for intent-aligned exact phrases."""
    if not query or not text:
        return 0.0
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
