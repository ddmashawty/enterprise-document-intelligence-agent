import json
import re
import sqlite3
from pathlib import Path

import pytest

from doc_agent.config import get_settings
from doc_agent.ingest.loaders import DocumentPage, ParsedDocument
from doc_agent.ingest.tables import Table
from doc_agent.kaoyan.db import KaoyanStore
from doc_agent.kaoyan.extract import RULE_EXTRACTORS
from doc_agent.kaoyan.extract.apply import apply_facts
from doc_agent.kaoyan.extract.base import ExtractContext, Fact, FactSet, ProgramRef
from doc_agent.kaoyan.extract.evaluate import evaluate, render_markdown
from doc_agent.kaoyan.extract.jnu_tm_pdf import JnuTmPdf
from doc_agent.kaoyan.extract.llm_fallback import LlmFallback
from doc_agent.kaoyan.extract.run import (
    ExtractionRun,
    document_contexts,
    run_extraction,
)
from doc_agent.kaoyan.extract.scnu_retest_html import ScnuRetestHtml
from doc_agent.kaoyan.extract.scnu_zsml_html import ScnuZsmlHtml
from doc_agent.kaoyan.extract.scut_plan_html import ScutPlan
from doc_agent.kaoyan.extract.sysu_baseline_pdf import SysuBaselinePdf
from doc_agent.kaoyan.extract.sysu_retest_html import SysuRetestHtml
from doc_agent.kaoyan.seed import seed_kaoyan

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "kaoyan"
FACT_TABLES = ("plans", "score_lines", "exam_subjects", "directions", "admission_stats")


def _doc(*tables: list[list[str]], text: str = "") -> ParsedDocument:
    return ParsedDocument(
        source="synthetic",
        pages=[DocumentPage("synthetic", 1, text)],
        tables=[Table(cells=t, index=i) for i, t in enumerate(tables)],
    )


def _ctx(**kw: object) -> ExtractContext:
    base = {"doc_id": "t-001", "school_id": "sysu", "year": 2026, "doc_type": "retest_rules", "format": "html"}
    return ExtractContext(**{**base, **kw})  # type: ignore[arg-type]


def _by(facts: list[Fact], table: str, kind: str | None = None) -> list[Fact]:
    return [f for f in facts if f.table == table and (kind is None or f.kind == kind)]


# --- rule extractors on synthetic tables (shapes copied from the real files) --


def test_sysu_lines_two_row_header_special_scope() -> None:
    table = [
        ["序号", "专业代码", "专业名称", "复试分数线", "复试分数线", "复试分数线", "复试分数线", "复试分数线", "备注"],
        ["序号", "专业代码", "专业名称", "总分", "政治", "外语", "业务课一", "业务课二", ""],
        ["1", "085404", "计算机技术（全日制）", "379", "50", "50", "60", "60", ""],
        ["2", "085404", "计算机技术（全日制）", "303", "50", "50", "60", "60", "少干计划"],
        ["3", "081200", "计算机科学与技术", "339", "45", "45", "60", "60", "退役士兵计划"],
    ]
    facts = SysuRetestHtml().extract(_doc(table), _ctx(college="670计算机学院"))
    scopes = {(f.kind, f.program.code, f.values["total"]) for f in _by(facts, "score_lines")}
    assert scopes == {("college", "085404", 379), ("special_minority", "085404", 303), ("special_veteran", "081200", 339)}
    line = _by(facts, "score_lines", "college")[0]
    assert line.program == ProgramRef("670", "085404", "全日制")
    assert (line.values["politics"], line.values["subject2"]) == (50, 60)
    assert all(f.evidence_text and f.source_doc_id == "t-001" for f in facts)


def test_sysu_plan_table() -> None:
    table = [
        ["学科专业代码", "学科专业名称", "总计划", "已招推免生", "公开招考计划", "备注"],
        ["081200", "计算机科学与技术", "15", "7", "8", ""],
        ["085410", "人工智能", "1", "0", "1", "少干计划"],
    ]
    facts = SysuRetestHtml().extract(_doc(table), _ctx(college="724人工智能学院"))
    got = {(f.kind, f.program.code): f.values["value"] for f in _by(facts, "plans")}
    assert got == {
        ("rules_total", "081200"): 15,
        ("tm", "081200"): 7,
        ("public_exam", "081200"): 8,
        ("special_minority", "085410"): 1,
    }


def test_sysu_baseline_skips_separate_tracks() -> None:
    table = [
        ["类别", "学科门类/学位类别", "总分", "单科（满分=100分）", "单科（满分>100分）"],
        ["学术学位", "工学[08]", "280", "45", "60"],
        ["专业学位", "电子信息[0854]、机械[0855]", "300", "50", "60"],
        ["单独考试", "公共卫生[1053]", "300", "40", "180"],
    ]
    ctx = _ctx(doc_type="score_line", format="pdf-text", title="中山大学2026年复试基本分数线")
    lines = SysuBaselinePdf().extract(_doc(table), ctx)
    got = {f.values["discipline_code"]: (f.values["total"], f.values["politics"], f.values["subject1"]) for f in lines}
    assert got == {"08": (280, 45, 60), "0854": (300, 50, 60), "0855": (300, 50, 60)}
    assert all(f.program is None and f.kind == "school_baseline" for f in lines)
    assert "学硕" in next(f for f in lines if f.values["discipline_code"] == "08").values["definition"]


def test_scnu_retest_plan_rows_and_candidate_tables() -> None:
    plans = [
        ["序号", "学习方式", "专业代码", "专业名称", "拟招生人数", "已招收推免生数", "复试差额比例"],
        ["1", "全日制", "081200", "计算机科学与技术", "48", "16", "1:1.6"],
        ["2", "全日制", "081200", "计算机科学与技术", "1 （立功表彰免初试考生）", "0", "1:1.6"],
        ["3", "全日制", "085404", "计算机技术", "47 （含产教融合联培专项 2 个）", "2", "1:1.6"],
        ["4", "全日制", "085404", "计算机技术", "3 （退役大学生士兵计划）", "0", "1:1.6"],
    ]
    candidates = [
        ["序号", "学习方式", "专业代码", "专业名称", "考生姓名", "初试成绩", "备注"],
        ["1", "全日制", "081200", "计算机科学与技术", "张某", "380", ""],
    ]
    ctx = _ctx(school_id="scnu", college="019计算机学院")
    facts = ScnuRetestHtml().extract(_doc(plans, candidates), ctx)
    got = sorted((f.kind, f.program.code, f.values["value"]) for f in facts)
    assert got == [
        ("rules_total", "081200", 48),
        ("rules_total", "085404", 47),
        ("special_veteran", "085404", 3),
        ("tm", "081200", 16),
        ("tm", "085404", 2),
    ]
    assert not any("张某" in f.evidence_text for f in facts)


def test_scnu_zsml_total_tm_and_no_tm_note() -> None:
    table = [
        ["编码", "名称", "拟招 人数", "考试科目", "复试科目", "备注"],
        ["046", "数据科学与工程学院", "20(0)", "", "", ""],
        ["085404", "计算机技术", "20", "", "", ""],
        ["01", "计算机应用技术", "", "① 101|思想政治理论 ② 204|英语（二） ③ 302|数学（二） ④ 408|计算机学科专业基础",
         "", "本专业拟招20名，不招推免生。"],
        ["02", "人工智能", "", "① 101|思想政治理论 ② 204|英语（二） ③ 302|数学（二） ④ 408|计算机学科专业基础", "", "同上"],
    ]
    ctx = _ctx(school_id="scnu", doc_type="catalog", local_path="raw/scnu/x_Zsml_View_046.html", title="2026目录 全日制")
    facts = ScnuZsmlHtml().extract(_doc(table), ctx)
    plans = {f.kind: f.values["value"] for f in _by(facts, "plans")}
    assert plans == {"catalog_total": 20, "tm": 0}
    assert _by(facts, "plans", "tm")[0].evidence_text == "本专业拟招20名，不招推免生。"
    subjects = _by(facts, "exam_subjects")
    assert [(s.values["slot"], s.values["code"]) for s in subjects] == [(1, "101"), (2, "204"), (3, "302"), (4, "408")]
    assert [d.values["code"] for d in _by(facts, "directions")] == ["01", "02"]


def test_scut_college_plan_skips_sub_plans() -> None:
    table = [
        ["专业名称及代码", "统考招生计划数", "备注"],
        ["计算机科学与技术 081200", "18", ""],
        ["计算机科学与技术 081200", "5", "中法南特联培项目"],
        ["计算机技术 085404", "35", "含基地计划"],
    ]
    ctx = _ctx(school_id="scut", doc_type="plan_quota", college="计算机科学与工程学院")
    facts = ScutPlan().extract(_doc(table), ctx)
    assert [(f.kind, f.program.code, f.values["value"]) for f in facts] == [
        ("college_exam_plan", "081200", 18),
        ("college_exam_plan", "085404", 35),
    ]
    assert facts[0].values["definition"] == "学院通知“统考招生计划”"
    assert facts[0].program.college == "计算机科学与工程学院"


def test_scut_available_exam_table() -> None:
    table = [
        ["招生学院（系）名称", "招生专业代码及名称", "学习方式", "统考可用计划"],
        ["未来技术学院", "140500 智能科学与技术", "全日制", "22"],
    ]
    ctx = _ctx(school_id="scut", doc_type="plan_quota", format="pdf-text", college="研究生招生办（校级）",
               publish_date="2025-10-22")
    (fact,) = ScutPlan().extract(_doc(table), ctx)
    assert (fact.kind, fact.program, fact.values["value"]) == (
        "available_exam", ProgramRef("未来技术学院", "140500", "全日制"), 22)
    assert fact.values["definition"] == "学校“统考可用计划”（2025-10-22 公布）"


def test_jnu_tm_pool_upper_bound() -> None:
    table = [
        ["专业代码", "专业名称", "推免名额"],
        ["081201", "计算机系统结构", "≤19"],
        ["081202", "计算机软件与理论", "≤19"],
        ["085404", "计算机技术", "≤41"],
    ]
    ctx = _ctx(school_id="jnu", doc_type="tm_policy", format="pdf-text", year=2027, college="010信息科学技术学院")
    facts = JnuTmPdf().extract(_doc(table, text="计算机科学与技术按一级学科统筹"), ctx)
    got = {f.program.code: (f.values["value"], f.values["is_upper_bound"], f.values["pool_scope"]) for f in facts}
    assert got["081201"] == (19, True, "0812")
    assert got["085404"] == (41, True, None)


def test_every_rule_extractor_has_a_name() -> None:
    names = [cls().name for cls in RULE_EXTRACTORS]
    assert len(names) == len(set(names)) == 10


# --- apply: resolve / compare / write ----------------------------------------


@pytest.fixture()
def seeded(tmp_path: Path) -> KaoyanStore:
    if not (DATA_DIR / "majors.csv").exists():
        pytest.skip("data/kaoyan bundle not present")
    store = KaoyanStore(tmp_path / "kaoyan.db")
    seed_kaoyan(store, DATA_DIR)
    return store


def _seed_counts(store: KaoyanStore) -> dict[str, int]:
    where = "extraction_method IN ('manual_seed', 'seed_note_regex')"
    return {t: store.count(t, where) for t in FACT_TABLES}


def _plan_fact(value: int, *, college: str = "670", code: str = "085404", doc: str = "sysu-078") -> Fact:
    facts = FactSet(ExtractContext(doc_id=doc, school_id="sysu", year=2026), "test")
    facts.plan("rules_total", ProgramRef(college, code, "全日制"), value, evidence=f"085404 计算机技术 {value}",
               definition="学院复试细则“总计划”")
    return facts[0]


def test_apply_match_conflict_new_unresolved(seeded: KaoyanStore) -> None:
    before = _seed_counts(seeded)
    seed_rows = seeded.plans_for("sysu-670-085404", "rules_total")
    report = apply_facts(
        seeded,
        [_plan_fact(999), _plan_fact(214, doc="sysu-081"), _plan_fact(5, code="070102")],
        doc_ids={"sysu-078", "sysu-081"},
    )
    statuses = [r.status for r in report.results]
    assert statuses == ["conflict", "new", "unresolved"]
    assert report.conflicts[0].diff == {"value": (214, 999)}
    assert report.written == 2

    rows = seeded.plans_for("sysu-670-085404", "rules_total")
    rule_rows = [r for r in rows if r["extraction_method"] == "rule"]
    assert {(r["value"], r["verified"]) for r in rule_rows} == {(999, 0), (214, 0)}
    assert [r for r in rows if r["extraction_method"] != "rule"] == seed_rows  # seed untouched
    assert _seed_counts(seeded) == before

    report = apply_facts(seeded, [_plan_fact(214)], doc_ids={"sysu-078", "sysu-081"})
    assert [r.status for r in report.results] == ["match"]
    rule_rows = [r for r in seeded.plans_for("sysu-670-085404", "rules_total") if r["extraction_method"] == "rule"]
    assert [(r["value"], r["verified"]) for r in rule_rows] == [(214, 1)]  # previous rule rows replaced


def test_resolver_expands_pool_and_rejects_ambiguity(seeded: KaoyanStore) -> None:
    facts = FactSet(ExtractContext(doc_id="jnu-012", school_id="jnu", year=2027), "test")
    facts.plan("tm", ProgramRef("010", "0812"), 19, evidence="0812 ≤19", definition="x", is_upper_bound=True,
               pool_scope="0812")
    facts.plan("tm", ProgramRef(None, "0812"), 19, evidence="0812 ≤19", definition="x")
    report = apply_facts(seeded, facts, write=False)
    pool = [r for r in report.results if r.fact is facts[0]]
    assert sorted(r.program_id for r in pool) == [
        "jnu-010-081201", "jnu-010-081202", "jnu-010-081203", "jnu-010-0812Z3"]
    assert [r.status for r in report.results if r.fact is facts[1]] == ["unresolved"]


# --- LLM fallback (fake model, evidence gate) --------------------------------


class FakeModel:
    def __init__(self, reply: object) -> None:
        self.reply = json.dumps(reply, ensure_ascii=False)
        self.calls = 0

    def invoke(self, messages: list[tuple[str, str]]) -> object:
        self.calls += 1
        return type("Reply", (), {"content": f"```json\n{self.reply}\n```"})()


LLM_TEXT = "我院2026年计算机技术（085404）拟招收全日制硕士研究生47名，其中已接收推免生2名。复试分数线为348分。"


def test_llm_fallback_keeps_only_grounded_facts(seeded: KaoyanStore) -> None:
    model = FakeModel([
        {"table": "plans", "kind": "rules_total", "college": "019", "program_code": "085404", "value": 47,
         "definition": "学院复试方案“拟招收”", "evidence": "计算机技术（085404）拟招收全日制硕士研究生47名"},
        {"table": "score_lines", "kind": "college", "college": "019", "program_code": "085404", "total": 348,
         "evidence": "复试分数线为348分"},
        {"table": "plans", "kind": "tm", "program_code": "085404", "value": 3, "evidence": "其中已接收推免生2名"},
        {"table": "plans", "kind": "tm", "program_code": "085404", "value": 2, "evidence": "推免生共2名（编造）"},
        {"table": "plans", "kind": "guess", "program_code": "085404", "value": 47, "evidence": "47名"},
        {"table": "plans", "kind": "tm", "program_code": "0854", "value": 2, "evidence": "推免生2名"},
    ])
    llm = LlmFallback(model)
    ctx = _ctx(school_id="scnu", doc_id="scnu-037", college="019计算机学院")
    facts = llm.extract(_doc(text=LLM_TEXT), ctx)
    assert [(f.table, f.kind) for f in facts] == [("plans", "rules_total"), ("score_lines", "college")]
    assert all(f.extraction_method == "llm" and f.evidence_text in LLM_TEXT for f in facts)
    reasons = sorted(d["reason"] for d in llm.report.dropped)
    assert reasons == [
        "bad program code", "evidence not found in document", "unknown table/kind", "value not in evidence"]

    report = apply_facts(seeded, facts)
    assert {r.status for r in report.results} == {"match"}  # both equal the seed → verified
    rows = seeded.query("SELECT verified FROM plans WHERE extraction_method = 'llm'")
    assert rows == [{"verified": 1}]


def test_llm_fallback_never_sees_personal_documents() -> None:
    model = FakeModel([])
    llm = LlmFallback(model)
    assert llm.extract(_doc(text=LLM_TEXT), _ctx(contains_personal_data=True)) == []
    assert llm.extract(_doc(text=LLM_TEXT), _ctx(format="img")) == []
    assert model.calls == 0


# --- DB migration ---------------------------------------------------------------


def test_old_db_gets_evidence_columns(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    KaoyanStore(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP VIEW IF EXISTS v_program_facts")
        conn.execute("ALTER TABLE directions DROP COLUMN evidence_text")
        conn.execute("ALTER TABLE exam_subjects DROP COLUMN evidence_text")
    KaoyanStore(db)
    with sqlite3.connect(db) as conn:
        for table in ("directions", "exam_subjects"):
            assert "evidence_text" in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


# --- real bundle documents ---------------------------------------------------


@pytest.fixture(scope="module")
def extracted(tmp_path_factory: pytest.TempPathFactory) -> tuple[KaoyanStore, ExtractionRun]:
    if not (DATA_DIR / "sources.json").exists():
        pytest.skip("data/kaoyan bundle not present")
    store = KaoyanStore(tmp_path_factory.mktemp("kaoyan_extract") / "kaoyan.db")
    seed_kaoyan(store, DATA_DIR)
    return store, run_extraction(store, get_settings())


def _local(doc_id: str) -> None:
    for path, ctx in document_contexts(DATA_DIR):
        if ctx.doc_id == doc_id:
            if not path.exists():
                pytest.skip(f"local-only file missing: {doc_id}")
            return
    pytest.skip(f"{doc_id} not in sources.json")


def _rule(store: KaoyanStore, table: str, program_id: str | None, doc: str, **where: object) -> list[dict]:
    sql = f"SELECT * FROM {table} WHERE extraction_method = 'rule' AND source_doc_id = ?"
    params: list[object] = [doc]
    if program_id:
        sql += " AND program_id = ?"
        params.append(program_id)
    for k, v in where.items():
        sql += f" AND {k} = ?"
        params.append(v)
    return store.query(sql, params)


def test_real_no_conflicts_and_acceptance(extracted: tuple[KaoyanStore, ExtractionRun]) -> None:
    store, run = extracted
    assert run.apply is not None and run.apply.conflicts == []
    report = evaluate(store, run, DATA_DIR)
    for a in report.acceptance:
        assert a.passed, (a.name, a.matched, a.seed, a.missing)
    assert report.facts_without_evidence == 0


def test_real_every_rule_row_has_source_and_evidence(extracted: tuple[KaoyanStore, ExtractionRun]) -> None:
    store, _ = extracted
    for table in FACT_TABLES:
        bad = store.count(table, "extraction_method = 'rule' AND (source_doc_id IS NULL OR "
                                 "evidence_text IS NULL OR TRIM(evidence_text) = '')")
        assert bad == 0, table
    assert store.count("plans", "extraction_method = 'rule'") > 100


def test_real_sysu_670_rules(extracted: tuple[KaoyanStore, ExtractionRun]) -> None:
    store, _ = extracted
    got = {r["kind"]: (r["value"], r["verified"]) for r in _rule(store, "plans", "sysu-670-085404", "sysu-078")}
    assert got == {"rules_total": (214, 1), "tm": (165, 1), "public_exam": (49, 1), "special_minority": (4, 1),
                   "special_veteran": (3, 1)}
    lines = {r["scope"]: r["total"] for r in _rule(store, "score_lines", "sysu-670-085404", "sysu-078")}
    assert lines == {"college": 379, "special_minority": 303, "special_veteran": 323}
    (pt,) = _rule(store, "plans", "sysu-670-085411-pt", "sysu-078", kind="rules_total")
    assert pt["value"] == 40


def test_real_sysu_baseline(extracted: tuple[KaoyanStore, ExtractionRun]) -> None:
    store, _ = extracted
    (row,) = _rule(store, "score_lines", None, "sysu-070", discipline_code="0854")
    assert (row["total"], row["politics"], row["foreign_lang"], row["subject1"], row["subject2"]) == (300, 50, 50, 60, 60)
    assert row["program_id"] is None and row["verified"] == 1


def test_real_jnu_2027_catalog_pool(extracted: tuple[KaoyanStore, ExtractionRun]) -> None:
    store, _ = extracted
    (row,) = _rule(store, "plans", "jnu-010-081201", "jnu-016", kind="catalog_total")
    assert (row["value"], row["pool_scope"], row["verified"]) == (24, "0812", 1)
    (row,) = _rule(store, "plans", "jnu-044-085410", "jnu-016", kind="catalog_total")
    assert row["value"] == 58
    assert len(_rule(store, "exam_subjects", None, "jnu-016", year=2027)) >= 44


def test_real_jnu_tm_upper_bound(extracted: tuple[KaoyanStore, ExtractionRun]) -> None:
    store, _ = extracted
    (row,) = _rule(store, "plans", "jnu-010-0812Z3", "jnu-012", kind="tm")
    assert (row["value"], row["is_upper_bound"], row["pool_scope"]) == (19, 1, "0812")
    (row,) = _rule(store, "plans", "jnu-052-083900", "jnu-014", kind="tm")
    assert (row["value"], row["is_upper_bound"]) == (45, 0)


def test_real_scnu_catalog_and_tm(extracted: tuple[KaoyanStore, ExtractionRun]) -> None:
    store, _ = extracted
    got = {r["kind"]: r["value"] for r in _rule(store, "plans", "scnu-019-081200", "scnu-022")}
    assert got == {"catalog_total": 48, "tm": 17}
    (row,) = _rule(store, "plans", "scnu-046-085404", "scnu-026", kind="tm")
    assert row["value"] == 0
    (row,) = _rule(store, "plans", "scnu-019-081200", "scnu-034", kind="tm", year=2027)
    assert row["value"] == 16
    names = [r["name"] for r in _rule(store, "directions", "scnu-019-085410", "scnu-034")]
    assert names == ["计算机软件技术", "智能感知与智能系统", "脑机接口与混合智能"]


def test_real_scut_plans(extracted: tuple[KaoyanStore, ExtractionRun]) -> None:
    store, _ = extracted
    (row,) = _rule(store, "plans", "scut-ft-140500", "scut-048", kind="available_exam")
    assert row["value"] == 22
    (row,) = _rule(store, "plans", "scut-ft-140500", "scut-060", kind="college_exam_plan")
    assert row["value"] == 28
    got = {r["program_id"]: r["value"] for r in _rule(store, "plans", None, "scut-055")}
    assert got == {"scut-cs-081200": 18, "scut-cs-085404": 35}


def test_real_sysu_catalog_pdf(extracted: tuple[KaoyanStore, ExtractionRun]) -> None:
    _local("sysu-072")
    store, _ = extracted
    (row,) = _rule(store, "plans", "sysu-670-085404", "sysu-072", kind="catalog_total")
    assert row["value"] == 210
    (no_exam,) = _rule(store, "exam_subjects", "sysu-757-083900", "sysu-072")
    assert no_exam["status"] == "no_exam"


def test_real_jnu_retest_xlsx_reads_only_plan_sheet(extracted: tuple[KaoyanStore, ExtractionRun]) -> None:
    _local("jnu-003")
    store, _ = extracted
    rows = _rule(store, "plans", "jnu-010-081202", "jnu-003", kind="public_exam")
    assert [(r["value"], r["pool_scope"]) for r in rows] == [(10, "0812")]
    (line,) = _rule(store, "score_lines", "jnu-010-085404", "jnu-003")
    assert (line["total"], line["politics"], line["subject1"]) == (318, 35, 53)
    evidence = " ".join(r["evidence_text"] for t in FACT_TABLES for r in _rule(store, t, None, "jnu-003"))
    assert not re.search(r"[\u4e00-\u9fff]某|\d{15}", evidence)


def test_real_idempotent(extracted: tuple[KaoyanStore, ExtractionRun]) -> None:
    store, _ = extracted
    before = {t: store.count(t) for t in FACT_TABLES}
    run_extraction(store, get_settings())
    assert {t: store.count(t) for t in FACT_TABLES} == before


def test_real_report_has_no_personal_data(extracted: tuple[KaoyanStore, ExtractionRun]) -> None:
    store, run = extracted
    md = render_markdown(evaluate(store, run, DATA_DIR))
    assert "验收" in md and "通过" in md
    assert not re.search(r"[\u4e00-\u9fff]某|\d{15}", md)
