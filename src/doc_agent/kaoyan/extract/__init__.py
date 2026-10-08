"""Structured extraction: bundle documents → facts (plans / lines / subjects / directions / stats)."""

from __future__ import annotations

from doc_agent.kaoyan.extract.base import (
    ExtractContext,
    Extractor,
    Fact,
    FactSet,
    ProgramRef,
)
from doc_agent.kaoyan.extract.jnu_catalog_html import JnuCatalogHtml
from doc_agent.kaoyan.extract.jnu_retest_xlsx import JnuRetestXlsx
from doc_agent.kaoyan.extract.jnu_tm_pdf import JnuTmPdf
from doc_agent.kaoyan.extract.scnu_retest_html import ScnuRetestHtml
from doc_agent.kaoyan.extract.scnu_tm_xls import ScnuTmXls
from doc_agent.kaoyan.extract.scnu_zsml_html import ScnuZsmlHtml
from doc_agent.kaoyan.extract.scut_baseline_img import ScutBaselineImage
from doc_agent.kaoyan.extract.scut_plan_html import ScutPlan
from doc_agent.kaoyan.extract.scut_subjects_img import ScutSubjectsImage
from doc_agent.kaoyan.extract.sysu_baseline_pdf import SysuBaselinePdf
from doc_agent.kaoyan.extract.sysu_catalog_pdf import SysuCatalogPdf
from doc_agent.kaoyan.extract.sysu_retest_html import SysuRetestHtml

RULE_EXTRACTORS: tuple[type[Extractor], ...] = (
    JnuCatalogHtml,
    JnuRetestXlsx,
    JnuTmPdf,
    ScnuZsmlHtml,
    ScnuTmXls,
    ScnuRetestHtml,
    ScutPlan,
    ScutBaselineImage,
    ScutSubjectsImage,
    SysuBaselinePdf,
    SysuCatalogPdf,
    SysuRetestHtml,
)

__all__ = [
    "RULE_EXTRACTORS",
    "ExtractContext",
    "Extractor",
    "Fact",
    "FactSet",
    "ProgramRef",
]
