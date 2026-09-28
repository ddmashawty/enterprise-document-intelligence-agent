import json
from pathlib import Path

import pytest

from doc_agent.config import Settings
from doc_agent.ingest.chunking import TextChunk, _table_blocks, chunk_document, table_header_rows
from doc_agent.ingest.loaders import DocumentPage, LoadedDocument
from doc_agent.ingest.tables import Table
from doc_agent.kaoyan.index import ingest_kaoyan
from doc_agent.rag.embeddings import Hit
from doc_agent.rag.query_expand import expand_queries, kaoyan_prior
from doc_agent.rag.store import DocumentStore, get_store, reset_store

DATA = Path(__file__).resolve().parents[1] / "data" / "kaoyan"
FIXTURES = [
    "raw/jnu/jnu_2027_硕士招生专业目录_202607.html",
    "raw/jnu/jnu_2026_硕士招生专业目录.html",
    "raw/jnu/jnu_2026_各学院硕士复试方案_20260320.html",
    "raw/sysu/sysu_cse_2026_复试录取实施细则.html",
    "raw/sysu/sysu_2026_复试基本分数线.pdf",
    "raw/scnu/scnu_2026_招生专业目录_Zsml_View_019_p1.html",
    "raw/scnu/scnu_2027_推免硕士招生专业目录.xls",
]
JNU_HEADER = "专业、研究方向 | 导师 | 招生 人数 | 考试科目 | 复试科目 | 同等学力加试科目 | 专业备注"


@pytest.fixture(scope="module")
def ky(tmp_path_factory):
    missing = [p for p in FIXTURES if not (DATA / p).exists()]
    if missing:
        pytest.skip(f"fixtures missing: {missing}")
    s = Settings(kaoyan_chroma_dir=str(tmp_path_factory.mktemp("chroma_kaoyan")), embedding_base_url="")
    report = ingest_kaoyan(s, paths=[DATA / p for p in FIXTURES], reindex=True)
    yield s, get_store(s, profile="kaoyan"), report
    reset_store("kaoyan")


def _chunks(store: DocumentStore, doc_id: str) -> list[dict]:
    return [c for c in store._chunks if c.get("doc_id") == doc_id]


def test_ingest_report_and_metadata(ky) -> None:
    s, store, report = ky
    assert report["docs_indexed"] == len(FIXTURES) and not report["docs_failed"]
    assert report["collection"] == "kaoyan_docs" and report["retrieval_backend"] == "bm25"
    rows = _chunks(store, "jnu-016")
    assert rows and all(c["chunk_id"].startswith("jnu-016::p1::c") for c in rows)
    first = rows[0]
    assert (first["school"], first["year"], first["doc_type"]) == ("jnu", 2027, "catalog")
    assert first["url"].startswith("https://yz.jnu.edu.cn/") and first["title"].startswith("2027年硕士研究生招生专业目录")
    assert "redacted" not in first


def test_school_filter(ky) -> None:
    _, store, _ = ky
    hits = store.search("计算机技术 复试分数线", top_k=8, school="jnu")
    assert hits and {h.metadata["school"] for h in hits} == {"jnu"}
    alias = store.search("计算机技术 复试分数线", top_k=8, school="暨大")
    assert [h.chunk_id for h in alias] == [h.chunk_id for h in hits]
    unfiltered = store.search("计算机技术 复试分数线", top_k=8)
    assert len({h.metadata["school"] for h in unfiltered}) > 1


def test_school_inferred_from_query(ky) -> None:
    _, store, _ = ky
    hits = store.search("暨大 085412 招生人数", top_k=8)
    assert hits and {h.metadata["school"] for h in hits} == {"jnu"}


def test_year_and_doc_type_filter_hits_2027_catalog(ky) -> None:
    _, store, _ = ky
    hits = store.search("085412 网络与信息安全 招生人数", top_k=5, year=2027, doc_type="catalog")
    assert hits and {h.metadata["doc_id"] for h in hits} == {"jnu-016"}
    top = hits[0].text
    assert "085412网络与信息安全(专业学位) | 62" in top
    assert "052网络空间安全学院 | 拟招生总人数： | 116" in top  # college row repeated as context
    older = store.search("085412 网络与信息安全 招生人数", top_k=5, year=2026, doc_type="catalog")
    assert older and "jnu-016" not in {h.metadata["doc_id"] for h in older}


def test_table_blocks_keep_header(ky) -> None:
    _, store, _ = ky
    rows = [c for c in _chunks(store, "jnu-016") if "①101思想政治理论" in c["text"]]
    assert len(rows) > 50 and all(JNU_HEADER in c["text"] for c in rows)
    assert all(c["text"].startswith("2027年硕士研究生招生专业目录") for c in rows)
    (cse,) = [c for c in _chunks(store, "sysu-078") if "| 379 |" in c["text"]]
    lines = cse["text"].splitlines()
    assert lines[:2] == ["计算机学院2026年硕士研究生复试录取实施细则", "我院各专业（方向）复试分数线如下："]
    assert lines[3].startswith("序号 | 专业代码 | 专业 名称 | 方向 代码 | 方向名称 | 总分 | 政治 | 外语")
    tm = [c for c in _chunks(store, "scnu-034") if " | " in c["text"]]
    assert len(tm) > 5 and all("院系代码 | 院系名称 | 学院拟接收推免人数 | 专业代码" in c["text"] for c in tm)


def test_rag_search_tool_uses_kaoyan_index_for_filters(ky, monkeypatch, tmp_path) -> None:
    from doc_agent.tools import registry

    s, _, _ = ky
    s = s.model_copy(update={"chroma_dir": str(tmp_path / "enterprise")})
    monkeypatch.setattr(registry, "get_settings", lambda: s)
    payload = json.loads(registry.rag_search.invoke({"query": "085404 复试分数线", "school": "sysu", "top_k": 3}))
    assert payload and all(h["metadata"]["school"] == "sysu" for h in payload)
    assert payload[0]["metadata"]["doc_id"] in {"sysu-078", "sysu-070"}
    assert "未检索到" in registry.rag_search.invoke({"query": "085404 复试分数线"})  # enterprise index is empty
    reset_store("enterprise")


def test_personal_files_are_flagged_and_downweighted(tmp_path) -> None:
    data = tmp_path / "kaoyan"
    (data / "raw" / "demo").mkdir(parents=True)
    (data / "raw" / "demo" / "list.html").write_text(
        "<p>复试名单</p><table><tr><td>考生编号</td><td>姓名</td><td>专业代码</td></tr>"
        "<tr><td>105586000000001</td><td>测试甲</td><td>085404</td></tr></table>",
        encoding="utf-8",
    )
    (data / "raw" / "demo" / "rules.html").write_text(
        "<p>085404 计算机技术 复试分数线 350</p>", encoding="utf-8"
    )
    docs = [
        {"doc_id": "demo-1", "school": "demo", "college": "测试学院", "title": "复试名单", "intake_year": 2026,
         "doc_type": "retest_list", "local_path": "raw/demo/list.html", "contains_personal_data": True},
        {"doc_id": "demo-2", "school": "demo", "college": "测试学院", "title": "复试细则", "intake_year": 2026,
         "doc_type": "retest_rules", "local_path": "raw/demo/rules.html", "contains_personal_data": False},
    ]
    (data / "sources.json").write_text(json.dumps({"schools": [], "documents": docs}), encoding="utf-8")
    s = Settings(kaoyan_data_dir=str(data), kaoyan_chroma_dir=str(tmp_path / "idx"), embedding_base_url="")
    report = ingest_kaoyan(s, reindex=True)
    assert report["docs_redacted"] == 1 and report["docs_indexed"] == 2 and not report["docs_missing"]
    store = get_store(s, profile="kaoyan")
    rows = _chunks(store, "demo-1")
    assert rows and all(r["redacted"] is True for r in rows)
    text = "\n".join(r["text"] for r in rows)
    assert "测某 | 085404" in text and "测试甲" not in text and "105586000000001" not in text
    hits = store.search("085404 复试分数线", top_k=2, school="demo")
    assert hits[0].metadata["doc_id"] == "demo-2"
    reset_store("kaoyan")


# --- unit level -------------------------------------------------------------------


def test_table_blocks_repeat_header_and_context() -> None:
    header = ["专业、研究方向", "导师", "招生人数", "考试科目", "复试科目", "备注"]
    table = Table(
        [header, ["052网络空间安全学院", "拟招生总人数：", "116", "", "", ""], ["085412网络与信息安全", "", "62", "", "", ""]]
        + [[f"{i:02d}(全日制)方向{i}", "导师" * 20, "", "①101", "密码学", ""] for i in range(1, 9)]
    )
    assert table_header_rows(table) == (0, 1)
    blocks = _table_blocks(table, ["2027目录"], chunk_size=300)
    assert len(blocks) > 2
    for block in blocks:
        lines = block.splitlines()
        assert lines[:4] == [
            "2027目录", " | ".join(header), "052网络空间安全学院 | 拟招生总人数： | 116", "085412网络与信息安全 | 62",
        ]
        assert len(lines) > 4


def test_header_detection_skips_title_and_data_rows() -> None:
    two_level = Table([["序号", "专业代码", "复试分数线", "复试分数线"], ["序号", "专业代码", "总分", "政治"], ["1", "085404", "379", "50"]])
    assert table_header_rows(two_level) == (0, 2)
    no_header = Table([["019", "计算机学院", "141(30)"], ["081200", "计算机科学与技术", "48(17)"]])
    assert table_header_rows(no_header) == (0, 0)


def test_enterprise_chunks_unchanged(tmp_path) -> None:
    doc = LoadedDocument(source="/tmp/demo.txt", pages=[DocumentPage("/tmp/demo.txt", 1, "hello world " * 50)])
    chunks = chunk_document(doc, chunk_size=40, overlap=5)
    assert chunks[0].chunk_id == "demo.txt::p1::c1" and chunks[0].metadata() == {}
    s = Settings(chroma_dir=str(tmp_path / "ent"), embedding_base_url="")
    store = DocumentStore(s)
    texts = ["文档保存期限为十年", "会议纪要由行政部归档", "合同原件存放在档案室"]
    store.upsert_chunks([TextChunk(f"a::p1::c{i}", "/x/a.txt", 1, t, "a.txt") for i, t in enumerate(texts, 1)])
    rows = [json.loads(ln) for ln in (tmp_path / "ent" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(set(r) == {"chunk_id", "source", "page", "doc_name", "text"} for r in rows)
    hits = store.search("保存期限")
    assert hits[0].chunk_id == "a::p1::c1" and "metadata" not in hits[0].to_dict()
    assert store.list_documents() == [{"doc_name": "a.txt", "source": "/x/a.txt", "chunks": 3, "pages": 1}]


def test_query_expansion_by_profile() -> None:
    assert expand_queries("085404复试线") == ["085404复试线"]
    assert expand_queries("主营业务构成") == [
        "主营业务构成", "主营业务分行业", "主营业务分地区", "产品情况", "营业收入主要来自", "茅台酒及系列酒",
    ]
    ky = expand_queries("中大 085404 复试线", profile="kaoyan")
    assert ky[0] == "中大 085404 复试线" and ky[1] == "中大 085404 复试线 中山大学"
    assert any("复试分数线" in q and q.startswith("中大 085404 复试线 中山大学") for q in ky[2:])


def test_kaoyan_prior() -> None:
    assert kaoyan_prior("085404 复试线", {"redacted": True, "doc_type": "retest_list"}) == 0.5
    assert kaoyan_prior("085404 复试线", {"doc_type": "retest_rules"}) == pytest.approx(1.2)
    assert kaoyan_prior("华师人工智能学院 085410 计划", {"doc_type": "catalog", "college": "041人工智能学院（佛山南海）"}) == pytest.approx(1.44)
    assert kaoyan_prior("085410 计划", {"college": "研究生院（校级）"}) == 1.0


def test_profiles_and_store_cache(tmp_path) -> None:
    s = Settings(chroma_dir=str(tmp_path / "a"), kaoyan_chroma_dir=str(tmp_path / "b"), embedding_base_url="")
    ky = s.for_profile("kaoyan")
    assert ky.chroma_path == tmp_path / "b" and ky.collection_name == "kaoyan_docs"
    assert s.for_profile("enterprise") is s
    with pytest.raises(ValueError):
        s.for_profile("other")
    ent, kao = get_store(s), get_store(s, profile="kaoyan")
    assert ent is not kao and ent is get_store(s) and kao.profile == "kaoyan"
    other = Settings(chroma_dir=str(tmp_path / "c"), embedding_base_url="")
    assert get_store(other) is not ent
    reset_store()
    assert Hit("c", "s", 1, "d", "t", 1.0, "bm25").to_dict().keys() == {"chunk_id", "source", "page", "doc_name", "text", "score", "backend"}
