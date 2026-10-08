"""Run the extractors over the bundle documents listed in sources.json."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from doc_agent.config import Settings, get_settings
from doc_agent.ingest.pipeline import load_document
from doc_agent.kaoyan.db import KaoyanStore
from doc_agent.kaoyan.extract.apply import ApplyReport, apply_facts
from doc_agent.kaoyan.extract.base import ExtractContext, Extractor, Fact
from doc_agent.kaoyan.extract.llm_fallback import LlmFallback, LlmReport


@dataclass
class DocRun:
    doc_id: str
    status: str  # ok | no_extractor | missing | needs_ocr | failed | llm
    extractors: list[str] = field(default_factory=list)
    facts: int = 0
    error: str | None = None


@dataclass
class ExtractionRun:
    docs: list[DocRun] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    apply: ApplyReport | None = None
    llm: LlmReport | None = None

    def summary(self) -> dict[str, Any]:
        docs: dict[str, Any] = {}
        for d in self.docs:
            docs[d.doc_id] = {"status": d.status, "facts": d.facts, "extractors": d.extractors}
            if d.error:
                docs[d.doc_id]["error"] = d.error
        out: dict[str, Any] = {"docs": docs}
        if self.apply:
            out["apply"] = self.apply.summary()
        if self.llm:
            out["llm"] = self.llm.summary()
        return out


def document_contexts(data_dir: Path) -> list[tuple[Path, ExtractContext]]:
    """(local path, context) for every sources.json document with a local file entry."""
    from doc_agent.kaoyan.index import source_documents

    return [(path, ExtractContext.from_entry(entry)) for path, entry in source_documents(data_dir).items()]


def default_extractors() -> list[Extractor]:
    from doc_agent.kaoyan.extract import RULE_EXTRACTORS

    return [cls() for cls in RULE_EXTRACTORS]


def run_extraction(
    store: KaoyanStore,
    settings: Settings | None = None,
    *,
    doc_ids: Sequence[str] | None = None,
    extractors: Sequence[Extractor] | None = None,
    llm_model: Any = None,
    write: bool = True,
) -> ExtractionRun:
    """Extract facts from local bundle documents and apply them to ``store``.

    Rule extractors run on every matching document. When ``llm_model`` is given, text
    documents without any rule fact go through the LLM fallback (evidence-checked).
    """
    s = settings or get_settings()
    rules = list(extractors) if extractors is not None else default_extractors()
    wanted = set(doc_ids) if doc_ids else None
    run = ExtractionRun()
    llm = LlmFallback(llm_model) if llm_model is not None else None
    processed: set[str] = set()

    for path, ctx in sorted(document_contexts(s.kaoyan_data_path), key=lambda pc: pc[1].doc_id):
        if wanted is not None and ctx.doc_id not in wanted:
            continue
        matching = [e for e in rules if e.matches(ctx)]
        wants_llm = llm is not None and not matching and llm.eligible(ctx)
        if not matching and not wants_llm:
            run.docs.append(DocRun(ctx.doc_id, "no_extractor"))
            continue
        if not path.exists():
            run.docs.append(DocRun(ctx.doc_id, "missing", [e.name for e in matching]))
            continue
        try:
            doc = load_document(path, s)
        except Exception as exc:  # noqa: BLE001
            run.docs.append(DocRun(ctx.doc_id, "failed", [e.name for e in matching], error=str(exc)))
            continue
        processed.add(ctx.doc_id)
        facts: list[Fact] = []
        for extractor in matching:
            facts.extend(extractor.extract(doc, ctx))
        if doc.meta.get("ocr_applied"):
            for fact in facts:
                fact.extraction_method = "ocr"
        status = "needs_ocr" if not facts and doc.needs_ocr else "ok"
        if not facts and llm is not None and llm.eligible(ctx) and not doc.needs_ocr:
            facts = llm.extract(doc, ctx)
            status = "llm"
        run.docs.append(DocRun(ctx.doc_id, status, [e.name for e in matching], len(facts)))
        run.facts.extend(facts)

    run.apply = apply_facts(store, run.facts, doc_ids=processed, write=write)
    if llm is not None:
        run.llm = llm.report
    return run
