"""LLM fallback for text documents no rule extractor covers.

The model must answer with JSON facts that each quote an ``evidence`` excerpt of the
document; a fact is dropped unless the excerpt occurs in the document text (whitespace
and table separators ignored) and contains the fact's number. Accepted facts are written
with ``extraction_method='llm'`` and ``verified=0`` unless they equal a seed row.
Personal-data documents (name lists) are never sent to the model.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, get_args

from doc_agent.ingest.loaders import ParsedDocument
from doc_agent.kaoyan.extract.base import ExtractContext, Fact, FactSet, ProgramRef
from doc_agent.kaoyan.models import LineScope, PlanKind, StatKind
from doc_agent.kaoyan.normalize import PROGRAM_CODE_RE, clean

LLM_DOC_TYPES = frozenset({"retest_rules", "score_line", "plan_quota", "tm_policy", "notice"})
MAX_DOC_CHARS = 12000
_KINDS: dict[str, frozenset[str]] = {
    "plans": frozenset(get_args(PlanKind)),
    "score_lines": frozenset(get_args(LineScope)),
    "admission_stats": frozenset(get_args(StatKind)),
}
_ID_NUMBER_RE = re.compile(r"\d{15,}")
_JSON_RE = re.compile(r"\[.*\]", re.DOTALL)

SYSTEM_PROMPT = """你是考研招生文件的信息抽取器。只从给定文件中抽取以下三类事实，输出 JSON 数组，不要输出其他文字：
1. plans: 招生计划数。kind ∈ catalog_total|tm|rules_total|public_exam|available_exam|college_exam_plan|special_veteran|special_minority
2. score_lines: 复试分数线。kind ∈ school_baseline|college|special_veteran|special_minority；给 total 以及可选 politics/foreign_lang/subject1/subject2
3. admission_stats: kind ∈ retest_count|admit_count|score_min|score_max
每个元素字段：table, kind, college（学院代码或名称，可空）, program_code（6 位专业代码；学校基本线可空并给 discipline_code）,
study_mode（全日制/非全日制，可空）, value（plans/admission_stats 的整数）, definition（原文口径，如“学院复试方案‘拟招生人数’”）,
evidence（从原文逐字复制、包含该数字的一小段文字）。
规则：不编数字；原文没有的不输出；不输出任何考生姓名、考生编号或个人分数。"""


@dataclass
class LlmReport:
    docs: list[str] = field(default_factory=list)
    accepted: int = 0
    dropped: list[dict[str, str]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {"docs": self.docs, "accepted": self.accepted, "dropped": self.dropped}


def _squash(text: str) -> str:
    return re.sub(r"[\s|｜]+", "", clean(text))


def document_text(doc: ParsedDocument) -> str:
    parts = [doc.text or ""]
    for table in doc.tables:
        parts.extend(" | ".join(table.row_values(r)) for r in range(table.n_rows))
    return "\n".join(p for p in parts if p)


def _call(model: Any, system: str, user: str) -> str:
    if hasattr(model, "invoke"):
        reply = model.invoke([("system", system), ("human", user)])
        return str(getattr(reply, "content", reply))
    return str(model(f"{system}\n\n{user}"))


def parse_items(raw: str) -> list[dict[str, Any]]:
    m = _JSON_RE.search(raw or "")
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


class LlmFallback:
    name = "llm_fallback"

    def __init__(self, model: Any) -> None:
        self.model = model
        self.report = LlmReport()

    @staticmethod
    def eligible(ctx: ExtractContext) -> bool:
        return (
            not ctx.contains_personal_data
            and ctx.doc_type in LLM_DOC_TYPES
            and ctx.format not in ("img", "pdf-scan")
        )

    def extract(self, doc: ParsedDocument, ctx: ExtractContext) -> list[Fact]:
        if not self.eligible(ctx) or ctx.year is None:
            return []
        text = document_text(doc)
        if not text.strip():
            return []
        self.report.docs.append(ctx.doc_id)
        user = f"文件标题：{ctx.title}\n发布单位：{ctx.college or ''}\n招生年份：{ctx.year}\n\n{text[:MAX_DOC_CHARS]}"
        items = parse_items(_call(self.model, SYSTEM_PROMPT, user))
        haystack = _squash(text)
        facts = FactSet(ctx, self.name, method="llm")
        for item in items:
            reason = self._add(item, haystack, ctx, facts)
            if reason:
                self.report.dropped.append({"doc_id": ctx.doc_id, "reason": reason, "kind": str(item.get("kind"))})
        self.report.accepted += len(facts)
        return facts

    @staticmethod
    def _add(item: dict[str, Any], haystack: str, ctx: ExtractContext, facts: FactSet) -> str | None:
        table, kind = item.get("table"), item.get("kind")
        if table not in _KINDS or kind not in _KINDS[table]:
            return "unknown table/kind"
        evidence = clean(str(item.get("evidence") or ""))
        if not evidence or _squash(evidence) not in haystack:
            return "evidence not found in document"
        if _ID_NUMBER_RE.search(evidence):
            return "evidence looks like personal data"
        code = clean(str(item.get("program_code") or ""))
        program = None
        if code:
            if not PROGRAM_CODE_RE.fullmatch(code):
                return "bad program code"
            program = ProgramRef(clean(str(item.get("college") or "")) or ctx.college_ref, code,
                                 clean(str(item.get("study_mode") or "")) or None)
        value = _int(item.get("total") if table == "score_lines" else item.get("value"))
        if value is None:
            return "missing value"
        if str(value) not in re.findall(r"\d+", evidence):
            return "value not in evidence"
        definition = clean(str(item.get("definition") or "")) or "LLM 抽取（待核验）"
        if table == "score_lines":
            discipline = clean(str(item.get("discipline_code") or "")) or None
            if program is None and not (kind == "school_baseline" and discipline):
                return "missing program"
            singles = [_int(item.get(k)) for k in ("politics", "foreign_lang", "subject1", "subject2")]
            facts.line(kind, program, value, singles, evidence=evidence, definition=definition,
                       discipline_code=discipline)
            return None
        if program is None:
            return "missing program"
        if table == "plans":
            facts.plan(kind, program, value, evidence=evidence, definition=definition)
        else:
            facts.stat(kind, program, value, evidence=evidence, definition=definition)
        return None


def build_llm_model(settings: Any) -> Any:
    """The configured chat model (raises when no API key is set)."""
    from doc_agent.llm.factory import build_chat_model

    return build_chat_model(settings)
