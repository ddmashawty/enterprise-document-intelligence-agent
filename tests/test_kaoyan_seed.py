import json
from pathlib import Path

import pytest

from doc_agent.kaoyan.db import KaoyanStore
from doc_agent.kaoyan.seed import NoteFact, extract_note_facts, seed_kaoyan

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "kaoyan"


def _facts(note: str, code: str = "085404") -> dict[tuple[str, str], NoteFact]:
    return {(f.table, f.kind): f for f in extract_note_facts(note, code)}


# --- 备注 regex variants (strings copied from data/kaoyan/majors.csv) ---------


@pytest.mark.parametrize(
    ("note", "total", "tm", "public"),
    [
        ("学院细则为总13/已招推免9/公开4", 13, 9, 4),
        ("学院2026复试细则为总15/已招推免7/公开8", 15, 7, 8),
        ("学院2026复试细则调整为总214/已招推免165/公开招考49", 214, 165, 49),
        ("学院细则（图片）为总53/已招推免30/公开23", 53, 30, 23),
        ("学院细则：总40/推免0/公开40", 40, 0, 40),
        ("学院细则总82/已招推免51/公开31", 82, 51, 31),
        ("推免数取自学院2026复试细则（总65/已招推免55/公开招考10）", 65, 55, 10),
    ],
)
def test_rules_plan_variants(note: str, total: int, tm: int, public: int) -> None:
    f = _facts(note)
    assert f[("plan", "rules_total")].value == total
    assert f[("plan", "tm")].value == tm
    assert f[("plan", "public_exam")].value == public


@pytest.mark.parametrize(
    ("note", "plan", "line", "singles"),
    [
        ("退役线288（30/30/48/48）", None, 288, (30, 30, 48, 48)),
        ("另退役2（线296）", 2, 296, (None, None, None, None)),
        ("退役大学生计划3名（线323）", 3, 323, (None, None, None, None)),
        ("另有退役大学生计划2名，复试线339", 2, 339, (None, None, None, None)),
    ],
)
def test_veteran_variants(note: str, plan: int | None, line: int, singles: tuple) -> None:
    f = _facts(note)
    assert f[("score", "special_veteran")].value == line
    assert f[("score", "special_veteran")].lines == singles
    if plan is None:
        assert ("plan", "special_veteran") not in f
    else:
        assert f[("plan", "special_veteran")].value == plan


def test_veteran_plan_without_line() -> None:
    f = _facts("复试方案：拟招47、已招推免2（含产教融合2、联培1），另退役3；计划含退役大学生士兵计划3")
    vets = [x for x in extract_note_facts("另退役3；含退役大学生士兵计划3", "085404") if x.kind == "special_veteran"]
    assert {x.value for x in vets} == {3}
    assert f[("plan", "rules_total")].value == 47
    assert f[("plan", "tm")].value == 2


@pytest.mark.parametrize(
    ("note", "plan", "line", "singles"),
    [
        ("少数民族骨干计划4名（线303）", 4, 303, (None, None, None, None)),
        ("少数民族骨干1名，线280（35/35/53/53）", 1, 280, (35, 35, 53, 53)),
        ("少干1名线375", 1, 375, (None, None, None, None)),
    ],
)
def test_minority_variants(note: str, plan: int, line: int, singles: tuple) -> None:
    f = _facts(note)
    assert f[("plan", "special_minority")].value == plan
    assert f[("score", "special_minority")].value == line
    assert f[("score", "special_minority")].lines == singles


@pytest.mark.parametrize(
    ("note", "kind", "value"),
    [
        ("统考计划35（含基地11、广东石油化工学院联培3）", "college_exam_plan", 35),
        ("学校统考可用计划PDF写21（口径不同）", "available_exam", 21),
        ("统考可用计划PDF也写18", "available_exam", 18),
        ("统考可用计划22（2025-10-22）", "available_exam", 22),
        ("学院2026-03-30通知统考招生计划28", "college_exam_plan", 28),
    ],
)
def test_scut_plan_variants(note: str, kind: str, value: int) -> None:
    facts = [f for f in extract_note_facts(note, "085404") if f.table == "plan"]
    assert [(f.kind, f.value) for f in facts] == [(kind, value)]


def test_scnu_retest_plan_variants() -> None:
    f = _facts("复试方案中计划为72（推免5，含联培专项），与目录的66不同", "085410")
    assert (f[("plan", "rules_total")].value, f[("plan", "tm")].value) == (72, 5)
    f = _facts("复试方案：拟招47、已招推免2（含产教融合2、联培1）")
    assert (f[("plan", "rules_total")].value, f[("plan", "tm")].value) == (47, 2)
    f = _facts("复试方案（2026-03-18）：拟招20/推免0，差额1:1.2，复试名单26人（网页表格计数）")
    assert (f[("plan", "rules_total")].value, f[("plan", "tm")].value) == (20, 0)
    assert f[("stat", "retest_count")].value == 26
    f = _facts("2027推免目录：推免16（学院合计27）", "081200")
    assert (f[("plan", "tm")].value, f[("plan", "tm")].year) == (16, 2027)


def test_jnu_pool_and_catalog_variants() -> None:
    note = (
        "2026：0812按一级学科复试，统招计划10人，复试19人，复试比1:1.90；"
        "2026目录中分专业计划：081201 5、081202 3、081203 6、0812Z3 10；"
        "2027目录只给出0812合计24人（含推免）"
    )
    facts = extract_note_facts(note, "081203")
    got = {(f.kind, f.year, f.pool_scope): f.value for f in facts}
    assert got[("public_exam", 2026, "0812")] == 10
    assert got[("retest_count", 2026, "0812")] == 19
    assert got[("catalog_total", 2026, None)] == 6
    assert got[("catalog_total", 2027, "0812")] == 24
    assert not [f for f in extract_note_facts(note, "085404") if f.kind == "catalog_total"]

    f = _facts("2026：目录55；统招计划51，复试83人，1:1.63", "085412")
    assert (f[("plan", "catalog_total")].value, f[("plan", "public_exam")].value) == (55, 51)
    assert f[("stat", "retest_count")].value == 83


def test_school_baseline_variants() -> None:
    f = _facts("学校基本线：工学[08]学硕 280/45/60", "081200")[("baseline", "school_baseline")]
    assert (f.value, f.discipline_code, f.lines) == (280, "08", (45, 45, 60, 60))
    f = _facts("学校基本要求（08工学：总分305，单科满分100的50，满分>100的70）")[("baseline", "school_baseline")]
    assert (f.value, f.discipline_code, f.lines) == (305, "08", (50, 50, 70, 70))
    f = _facts("学校14交叉学科320/50/75", "140500")[("baseline", "school_baseline")]
    assert (f.value, f.discipline_code) == (320, "14")


def test_admission_stat_variants() -> None:
    f = _facts("复试名单56人（339–416），统考拟录取36人")
    assert f[("stat", "retest_count")].value == 56
    assert f[("stat", "admit_count")].value == 36
    got = {(x.kind, x.pref): x.value for x in extract_note_facts("复试名单56人（339–416），统考拟录取36人", "085404")}
    assert got[("score_min", "retest_count")] == 339
    assert got[("score_max", "retest_count")] == 416
    f = _facts("复试及拟录取汇总表显示统考拟录取32（初试316–382，由表格计数得出）", "081200")
    assert f[("stat", "admit_count")].value == 32
    assert "由名单计数" in f[("stat", "admit_count")].definition
    f = _facts("复试名单15，拟录取8（https://sai.sysu.edu.cn/article/692）", "081200")
    assert f[("stat", "admit_count")].value == 8
    assert f[("stat", "admit_count")].url == "https://sai.sysu.edu.cn/article/692"
    # split counts (普通 + 退役) are left in notes rather than guessed
    assert not extract_note_facts("2026统考拟录取13（普通）+2（退役）", "081200")
    assert not extract_note_facts("拟录取66普通+4少干+3退役", "085404")


# --- full seed of the committed bundle --------------------------------------


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> KaoyanStore:
    if not (DATA_DIR / "majors.csv").exists() or not (DATA_DIR / "sources.json").exists():
        pytest.skip("data/kaoyan bundle not present")
    s = KaoyanStore(tmp_path_factory.mktemp("kaoyan") / "kaoyan.db")
    seed_kaoyan(s, DATA_DIR)
    return s


def _pid(store: KaoyanStore, school: str, college: str, code: str, mode: str = "全日制") -> str:
    rows = store.find_programs(school_id=school, college_code=college, code=code, study_mode=mode)
    assert len(rows) == 1, (school, college, code, rows)
    return rows[0]["id"]


def _plan(store: KaoyanStore, pid: str, kind: str, **where: object) -> list[dict]:
    return [p for p in store.plans_for(pid, kind) if all(p[k] == v for k, v in where.items())]


def test_seed_counts(store: KaoyanStore) -> None:
    assert store.count("programs") == 37
    assert store.count("documents") == 97
    assert store.count("documents", "id LIKE 'seed-%'") == 0
    assert store.count("schools") == 4
    assert store.count("score_lines", "source_doc_id IS NULL") == 0
    assert store.count("plans", "source_doc_id IS NULL") == 0
    assert store.count("admission_stats", "source_doc_id IS NULL") == 0


def test_sysu_670_085404(store: KaoyanStore) -> None:
    pid = _pid(store, "sysu", "670", "085404")
    (line,) = store.score_lines_for(pid, "college")
    assert (line["total"], line["politics"], line["foreign_lang"], line["subject1"], line["subject2"]) == (379, 50, 50, 60, 60)
    assert store.get_document(line["source_doc_id"])["page_url"] == "https://cse.sysu.edu.cn/article/3475"
    assert _plan(store, pid, "catalog_total")[0]["value"] == 210
    assert _plan(store, pid, "tm")[0]["value"] == 165
    assert _plan(store, pid, "public_exam")[0]["value"] == 49


def test_jnu_052_085412(store: KaoyanStore) -> None:
    pid = _pid(store, "jnu", "052", "085412")
    assert store.score_lines_for(pid, "college")[0]["total"] == 348
    (cat,) = _plan(store, pid, "catalog_total", year=2027)
    assert cat["value"] == 62 and cat["pool_scope"] is None
    (tm,) = _plan(store, pid, "tm")
    assert (tm["value"], tm["year"], tm["is_upper_bound"]) == (25, 2027, 0)


def test_scnu_019_085404(store: KaoyanStore) -> None:
    pid = _pid(store, "scnu", "019", "085404")
    assert store.score_lines_for(pid, "college")[0]["total"] == 348
    (vet,) = store.score_lines_for(pid, "special_veteran")
    assert (vet["total"], vet["politics"], vet["foreign_lang"], vet["subject1"], vet["subject2"]) == (288, 30, 30, 48, 48)
    assert {p["value"] for p in _plan(store, pid, "tm", year=2026)} == {4, 2}


def test_scut_cs_085404(store: KaoyanStore) -> None:
    pid = _pid(store, "scut", "cs", "085404")
    subjects = store.subjects_for(pid)
    assert subjects and {s["status"] for s in subjects} == {"unknown"}
    assert "统一认证" in subjects[0]["unknown_reason"]
    (line,) = store.score_lines_for(pid)
    assert (line["scope"], line["total"], line["discipline_code"]) == ("school_baseline", 305, "08")
    assert _plan(store, pid, "college_exam_plan")[0]["value"] == 35
    (avail,) = _plan(store, pid, "available_exam")
    assert avail["value"] == 21
    assert "统考可用计划" in store.get_document(avail["source_doc_id"])["title"]
    assert not _plan(store, pid, "catalog_total")
    retest = [s for s in store.stats_for(pid) if s["kind"] == "retest_count"]
    assert "085404" in store.get_document(retest[0]["source_doc_id"])["title"]


@pytest.mark.parametrize("code", ["081201", "081202", "081203", "0812Z3"])
def test_jnu_010_0812_pool(store: KaoyanStore, code: str) -> None:
    pid = _pid(store, "jnu", "010", code)
    assert not _plan(store, pid, "catalog_total", year=2027, pool_scope=None)
    (pool_total,) = _plan(store, pid, "catalog_total", year=2027)
    assert (pool_total["value"], pool_total["pool_scope"]) == (24, "0812")
    (tm,) = _plan(store, pid, "tm")
    assert (tm["value"], tm["is_upper_bound"], tm["pool_scope"]) == (19, 1, "0812")
    (retest,) = [s for s in store.stats_for(pid) if s["kind"] == "retest_count"]
    assert retest["pool_scope"] == "0812"


def test_sysu_757_083900_no_exam(store: KaoyanStore) -> None:
    pid = _pid(store, "sysu", "757", "083900")
    assert [s["status"] for s in store.subjects_for(pid)] == ["no_exam"]
    assert not store.score_lines_for(pid)
    assert _plan(store, pid, "public_exam")[0]["value"] == 0


def test_boundary_and_part_time(store: KaoyanStore) -> None:
    pid = _pid(store, "sysu", "765", "085400")
    assert store.query_one("SELECT is_boundary FROM programs WHERE id = ?", (pid,))["is_boundary"] == 1
    assert [s["code"] for s in store.subjects_for(pid)] == ["101", "204", "302", "884"]
    assert _pid(store, "jnu", "063", "085410", "非全日制").endswith("-pt")


def test_school_baselines(store: KaoyanStore) -> None:
    sysu = {(b["discipline_code"], b["total"]) for b in store.school_baselines("sysu")}
    assert ("08", 280) in sysu and ("0854", 300) in sysu
    scut = {(b["discipline_code"], b["total"]) for b in store.school_baselines("scut")}
    assert scut == {("08", 305), ("14", 320)}


def test_program_facts_view(store: KaoyanStore) -> None:
    facts = store.program_facts(_pid(store, "jnu", "010", "081203"))
    assert facts["tm"] == "2027:≤19[0812]@jnu-012"
    assert facts["catalog_total"].startswith("2027:24[0812]")


def test_golden_qa_sources_resolve(store: KaoyanStore) -> None:
    gold = json.loads((DATA_DIR.parent / "gold" / "kaoyan_qa.json").read_text(encoding="utf-8"))
    items = gold["items"]
    assert [i["id"] for i in items] == list(range(1, 19))
    for item in items:
        assert item["question"] and item["expected_answer"] and item["sources"]
        assert isinstance(item["expect_unknown"], bool)
        for src in item["sources"]:
            doc = store.get_document(src["doc_id"])
            assert doc is not None, (item["id"], src)
            assert src["url"] in (doc["page_url"], doc["attachment_url"]), (item["id"], src)
    assert sum(i["expect_unknown"] for i in items) == 2


def test_seed_is_idempotent(store: KaoyanStore) -> None:
    tables = ("programs", "documents", "plans", "score_lines", "admission_stats", "exam_subjects", "directions")
    before = {t: store.count(t) for t in tables}
    seed_kaoyan(store, DATA_DIR)
    assert {t: store.count(t) for t in tables} == before
