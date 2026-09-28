"""Compare an extraction run with the seed and render docs/kaoyan_extraction_report.md.

The report lists keys, counts and values only — never evidence excerpts — so nothing
from name-list documents can leak into it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from doc_agent.kaoyan.db import KaoyanStore
from doc_agent.kaoyan.extract.apply import KEY_FIELDS, row_key
from doc_agent.kaoyan.extract.run import ExtractionRun, document_contexts
from doc_agent.kaoyan.models import SEED_METHODS

IMAGE_FORMATS = ("img", "pdf-scan")

# Seed facts of text documents that rules must reproduce exactly (image sources wait for OCR in K7).
ACCEPTANCE: dict[str, Callable[[dict[str, Any]], bool]] = {
    "中大各学院复试线": lambda r: r["_table"] == "score_lines"
    and r["school_id"] == "sysu"
    and r["scope"] != "school_baseline",
    "暨南 2027 目录计划": lambda r: r["_table"] == "plans"
    and r["_school"] == "jnu"
    and r["kind"] == "catalog_total"
    and r["year"] == 2027,
    "华师目录总(推免)": lambda r: r["_table"] == "plans"
    and r["_school"] == "scnu"
    and r["kind"] in ("catalog_total", "tm")
    and r["_doc_type"] == "catalog",
    "华师 2027 推免数": lambda r: r["_table"] == "plans"
    and r["_school"] == "scnu"
    and r["kind"] == "tm"
    and r["year"] == 2027,
}


@dataclass
class DocEval:
    doc_id: str
    school: str
    doc_type: str | None
    run_status: str
    extractors: list[str]
    seed: int = 0
    matched: int = 0
    new: int = 0
    conflicts: int = 0
    unresolved: int = 0
    missing: Counter[str] = field(default_factory=Counter)


@dataclass
class AcceptanceEval:
    name: str
    seed: int
    matched: int
    conflicts: int
    missing: list[str]

    @property
    def passed(self) -> bool:
        return self.seed > 0 and self.matched == self.seed and self.conflicts == 0


@dataclass
class EvalReport:
    docs: list[DocEval]
    acceptance: list[AcceptanceEval]
    status: dict[str, int]
    seed_total: int
    matched_total: int
    facts_total: int
    facts_without_evidence: int
    conflicts: list[dict[str, Any]]

    @property
    def missing_reasons(self) -> Counter[str]:
        out: Counter[str] = Counter()
        for d in self.docs:
            out.update(d.missing)
        return out


def _seed_rows(store: KaoyanStore) -> list[dict[str, Any]]:
    marks = ", ".join("?" for _ in SEED_METHODS)
    rows: list[dict[str, Any]] = []
    for table in KEY_FIELDS:
        for row in store.query(
            f"SELECT t.*, d.school_id AS _school, d.doc_type AS _doc_type, d.format AS _format FROM {table} t "
            f"LEFT JOIN documents d ON d.id = t.source_doc_id WHERE t.extraction_method IN ({marks})",
            list(SEED_METHODS),
        ):
            row["_table"] = table
            rows.append(row)
    return rows


def _missing_reason(row: dict[str, Any], doc_status: str, entry: dict[str, Any]) -> str:
    fmt = str(entry.get("format") or "")
    if doc_status == "missing":
        return "本地无文件（local-only 未下载）"
    if doc_status == "not_listed":
        return "来源无本地文件（仅网页链接）"
    if doc_status == "needs_ocr" or any(fmt.startswith(f) for f in IMAGE_FORMATS):
        return "图片/扫描件，OCR 留到 K7"
    if row["_table"] == "exam_subjects" and row.get("status") == "unknown":
        return "种子判断（科目未公布）"
    if entry.get("contains_personal_data") or (
        row["_table"] == "admission_stats" and row.get("extraction_method") == "seed_note_regex"
    ):
        return "名单类统计（种子计数，规则不读名单）"
    if doc_status == "no_extractor":
        return "暂无规则抽取器"
    return "规则未覆盖"


def evaluate(store: KaoyanStore, run: ExtractionRun, data_dir: Path) -> EvalReport:
    entries = {ctx.doc_id: ctx for _, ctx in document_contexts(data_dir)}
    runs = {d.doc_id: d for d in run.docs}
    results = run.apply.results if run.apply else []
    matched = {r.key for r in results if r.status == "match"}
    per_doc: dict[str, DocEval] = {}

    def doc_eval(doc_id: str) -> DocEval:
        if doc_id not in per_doc:
            ctx = entries.get(doc_id)
            dr = runs.get(doc_id)
            per_doc[doc_id] = DocEval(
                doc_id,
                ctx.school_id if ctx else doc_id.split("-")[0],
                ctx.doc_type if ctx else None,
                dr.status if dr else "not_listed",
                dr.extractors if dr else [],
            )
        return per_doc[doc_id]

    for r in results:
        d = doc_eval(r.fact.source_doc_id)
        if r.status == "new":
            d.new += 1
        elif r.status == "conflict":
            d.conflicts += 1
        elif r.status in ("unresolved", "ambiguous"):
            d.unresolved += 1

    seeds = _seed_rows(store)
    for row in seeds:
        d = doc_eval(row["source_doc_id"])
        d.seed += 1
        if row_key(row["_table"], row) in matched:
            d.matched += 1
        else:
            ctx = entries.get(d.doc_id)
            entry = {"format": ctx.format, "contains_personal_data": ctx.contains_personal_data} if ctx else {}
            d.missing[_missing_reason(row, d.run_status, entry)] += 1

    conflict_keys = {r.key for r in results if r.status == "conflict"}
    acceptance = []
    for name, pred in ACCEPTANCE.items():
        rows = [r for r in seeds if r["_format"] not in IMAGE_FORMATS and pred(r)]
        keys = [row_key(r["_table"], r) for r in rows]
        acceptance.append(
            AcceptanceEval(
                name,
                len(rows),
                sum(k in matched for k in keys),
                sum(k in conflict_keys for k in keys),
                [" / ".join(str(x) for x in k[1:] if x is not None) for k in keys if k not in matched],
            )
        )

    written = [r for r in results if r.row is not None and r.status != "duplicate"]
    return EvalReport(
        docs=sorted(per_doc.values(), key=lambda d: d.doc_id),
        acceptance=acceptance,
        status=dict(Counter(r.status for r in results)),
        seed_total=len(seeds),
        matched_total=sum(d.matched for d in per_doc.values()),
        facts_total=len(written),
        facts_without_evidence=sum(
            1 for r in written if not r.fact.source_doc_id or not r.fact.evidence_text.strip()
        ),
        conflicts=[{"key": list(r.key or ()), "diff": r.diff} for r in results if r.status == "conflict"],
    )


def render_markdown(report: EvalReport) -> str:
    lines = [
        "# 考研结构化抽取评估报告（K4）",
        "",
        "> 由 `scripts/eval_extraction.py` 生成：新建库 → 种子入库 → 规则抽取 → 与种子逐键比对。",
        "> 只列键、计数与数值，不含证据原文，名单类文件不出现任何个人信息。",
        "",
        "## 概览",
        "",
        f"- 种子事实：{report.seed_total}，被规则逐值复现：{report.matched_total}",
        f"- 写入的抽取事实：{report.facts_total}（缺 `source_doc_id` / `evidence_text` 的：{report.facts_without_evidence}）",
        "- 抽取状态：" + "，".join(f"{k} {v}" for k, v in sorted(report.status.items())),
        "  - match = 与种子同键同值（写入 verified=1）；new = 种子没有的事实（verified=0）；",
        "  - conflict = 同键不同值（只记录、写入 verified=0，不覆盖种子）；",
        "  - unresolved = 专业不在 37 个目标专业内（不写库）；duplicate = 同文档同键重复出现（只保留首条）。",
        "",
        "## 验收：文本文档的种子事实须被规则逐值复现",
        "",
        "图片来源（img / pdf-scan）的种子事实不计入验收，留到 K7 OCR。",
        "",
        "| 类别 | 种子事实 | 规则命中 | 冲突 | 结果 |",
        "|---|---:|---:|---:|---|",
    ]
    for a in report.acceptance:
        lines.append(f"| {a.name} | {a.seed} | {a.matched} | {a.conflicts} | {'通过' if a.passed else '未通过'} |")
    for a in report.acceptance:
        if a.missing:
            lines.append("")
            lines.append(f"{a.name} 未命中：" + "；".join(a.missing))
    lines += [
        "",
        "## 冲突",
        "",
    ]
    if report.conflicts:
        lines += ["| 键 | 字段：种子 → 抽取 |", "|---|---|"]
        for c in report.conflicts:
            diff = "；".join(f"{k}: {s} → {v}" for k, (s, v) in c["diff"].items())
            lines.append(f"| {' / '.join(str(x) for x in c['key'] if x is not None)} | {diff} |")
    else:
        lines.append("无。")
    lines += [
        "",
        "## 未被规则复现的种子事实（按原因）",
        "",
        "| 原因 | 事实数 |",
        "|---|---:|",
    ]
    for reason, n in report.missing_reasons.most_common():
        lines.append(f"| {reason} | {n} |")
    lines += [
        "",
        "## 按文档",
        "",
        "| 文档 | 类型 | 运行状态 | 抽取器 | 种子 | 命中 | 新增 | 冲突 | 未解析 | 未复现原因 |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for d in report.docs:
        if not (d.seed or d.extractors or d.new or d.unresolved):
            continue
        reasons = "；".join(f"{k} {v}" for k, v in d.missing.most_common())
        lines.append(
            f"| {d.doc_id} | {d.doc_type or ''} | {d.run_status} | {', '.join(d.extractors)} | "
            f"{d.seed} | {d.matched} | {d.new} | {d.conflicts} | {d.unresolved} | {reasons} |"
        )
    lines.append("")
    return "\n".join(lines)
