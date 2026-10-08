import hashlib
from pathlib import Path

import pytest

from doc_agent.ingest.loaders import (
    ParsedDocument,
    decode_html,
    iter_source_files,
    load_file,
    parse_html,
)
from doc_agent.ingest.ocr import get_ocr_backend
from doc_agent.ingest.tables import Table, expand_spans, join_wrapped, render_page
from doc_agent.kaoyan.normalize import parse_total_tm

RAW = Path(__file__).resolve().parents[1] / "data" / "kaoyan" / "raw"


def _fixture(rel: str) -> Path:
    path = RAW / rel
    if not path.exists():
        pytest.skip(f"fixture missing: {rel}")
    return path


# --- real fixtures (values checked against the files and majors.csv) ----------


def test_sysu_cse_rules_table_row() -> None:
    doc = load_file(_fixture("sysu/sysu_cse_2026_复试录取实施细则.html"))
    assert isinstance(doc, ParsedDocument)
    rows = [r for t in doc.tables for r in t.find_rows("085404", "计算机技术（全日制）", "379")]
    assert rows and rows[0][1:10] == ["085404", "计算机技术（全日制）", "69", "不分方向", "379", "50", "50", "60", "60"]
    assert "085404 | 计算机技术（全日制） | 69 | 不分方向 | 379 | 50 | 50 | 60 | 60" in doc.text


def test_jnu_2027_catalog_three_level_rows() -> None:
    doc = load_file(_fixture("jnu/jnu_2027_硕士招生专业目录_202607.html"))
    (table,) = doc.tables
    count_col = table.column_index("招生人数")
    assert count_col is not None
    (program,) = table.find_rows("085412网络与信息安全(专业学位)")
    assert program[count_col] == "62"
    (college,) = table.find_rows("052网络空间安全学院", "拟招生总人数：")
    assert "116" in college
    (info,) = table.find_rows("010信息科学技术学院", "拟招生总人数：")
    assert any("计算机科学与技术指标为24个" in cell for cell in info)
    assert "052网络空间安全学院 | 拟招生总人数： | 116" in doc.text


def test_scnu_catalog_total_tm_cells() -> None:
    doc = load_file(_fixture("scnu/scnu_2026_招生专业目录_Zsml_View_019_p1.html"))
    (table,) = doc.tables  # the outer layout table is skipped, only the leaf data table remains
    assert parse_total_tm(table.find_rows("081200", "计算机科学与技术")[0][2]) == (48, 17)
    assert parse_total_tm(table.find_rows("085404", "计算机技术")[0][2]) == (50, 4)
    # rowspan="4" subject cell is spread over all four direction rows of 081200
    directions = [r for r in table.cells if r[0] in {"01", "02", "03", "04"}][:4]
    assert all("101|思想政治理论" in r[3] for r in directions)


def test_scnu_2027_tm_xls_ffill() -> None:
    doc = load_file(_fixture("scnu/scnu_2027_推免硕士招生专业目录.xls"))
    table = doc.tables[0].ffill(range(3))
    got = {(r[0], r[1], r[5]) for r in table.cells if r[3] == "085410"}
    assert got == {("019", "计算机学院", "3"), ("041", "人工智能学院", "8")}
    assert all(r[4] == "人工智能" for r in table.cells if r[3] == "085410")


def test_sysu_baseline_pdf_table() -> None:
    path = _fixture("sysu/sysu_2026_复试基本分数线.pdf")
    plain = load_file(path)
    assert plain.tables == []
    doc = load_file(path, tables=True)
    rows = [r for t in doc.tables for r in t.find_rows("工学[08]")]
    assert rows == [["学术学位", "工学[08]", "280", "45", "60"]]  # vertical merged 学/术/学/位 filled down
    assert "工学[08] | 280 | 45 | 60" in doc.text
    assert doc.meta["prose"] and not doc.needs_ocr


def test_sysu_sece_data_uri_image() -> None:
    doc = load_file(_fixture("sysu/sysu_sece_2026_复试录取实施细则.html"))
    inline = [img for img in doc.images if img.data is not None]
    assert len(inline) == 1
    expected = hashlib.sha256(_fixture("sysu/sysu_sece_2026_复试分数线_内嵌base64图1.png").read_bytes()).hexdigest()
    assert inline[0].sha256 == expected
    assert expected.startswith("19cedf27") and expected.endswith("6209")
    assert inline[0].mime == "image/png" and inline[0].needs_ocr
    assert doc.needs_ocr and doc.pages
    assert "base64" not in doc.text


def test_image_file_needs_ocr() -> None:
    doc = load_file(_fixture("scut/scut_ft_2026_招生专业及初试科目_图.jpg"))
    assert doc.pages == [] and doc.needs_ocr
    assert doc.images[0].mime == "image/jpeg" and len(doc.images[0].sha256) == 64


def test_jnu_xlsx_blocks_split_on_titles() -> None:
    doc = load_file(_fixture("scnu/scnu_2026_非全日制专业汇总.xlsx"))
    (table,) = doc.tables
    assert table.title.startswith("华南师范大学2026年招收非全日制")
    assert table.cells[0][:4] == ["院系代码", "院系名称", "专业代码", "专业名称"]


# --- synthetic cases ------------------------------------------------------------


def test_iter_source_files_new_suffixes_skip_csv(tmp_path: Path) -> None:
    for name in ("a.html", "b.htm", "c.xlsx", "d.xls", "e.jpg", "f.jpeg", "g.png", "h.pdf", "i.csv", "j.json"):
        (tmp_path / name).write_bytes(b"x")
    names = {p.name for p in iter_source_files(tmp_path)}
    assert names == {"a.html", "b.htm", "c.xlsx", "d.xls", "e.jpg", "f.jpeg", "g.png", "h.pdf"}


def test_expand_spans_and_render_dedupes_horizontal_merge() -> None:
    cells, origins = expand_spans([
        [("学院", 1, 2), ("人数", 1, 1)],
        [("019", 2, 1), ("计算机", 1, 1), ("48", 1, 1)],
        [("软件", 1, 1), ("20", 1, 1)],
    ])
    assert cells == [["学院", "学院", "人数"], ["019", "计算机", "48"], ["019", "软件", "20"]]
    table = Table(cells, origins=origins, title="示例")
    assert table.to_text() == "示例\n学院 | 人数\n019 | 计算机 | 48\n019 | 软件 | 20"
    assert render_page("前言\n[[TABLE:0]]\n结语", [table]).splitlines()[1] == "示例"


def test_table_helpers() -> None:
    table = Table([["代码", "名称", "人数"], ["019", "计算机学院", "3"], ["", "", "8"]])
    assert table.column_index("人 数") == 2
    filled = table.ffill([0, 1])
    assert filled.cells[2] == ["019", "计算机学院", "8"]
    assert table.drop_columns([1]).cells[1] == ["019", "3"]


def test_join_wrapped_cjk_and_latin() -> None:
    assert join_wrapped("学\n术\n学\n位") == "学术学位"
    assert join_wrapped("单科（ 满\n分=100 分）") == "单科（ 满分=100 分）"
    assert join_wrapped("Computer\nScience") == "Computer Science"


def test_decode_html_meta_charset_and_gbk_fallback() -> None:
    gbk = '<html><head><meta charset="gb2312"></head><body>复试分数线</body></html>'.encode("gbk")
    assert "复试分数线" in decode_html(gbk)
    undeclared = "<html><body>招生目录</body></html>".encode("gbk")
    assert "招生目录" in decode_html(undeclared)


def test_parse_html_drops_navigation_keeps_tables() -> None:
    html = """
    <html><head><title>通知</title></head><body>
      <div class="nav"><a href="/">首页</a><a href="/x">学院概况</a></div>
      <div class="article"><p>正文第一段</p>
        <table><tr><th>代码</th><th>线</th></tr><tr><td>085404</td><td>379</td></tr></table>
      </div>
      <div id="footer">版权所有</div>
    </body></html>"""
    doc = parse_html(html, source="t.html")
    assert "首页" not in doc.text and "版权所有" not in doc.text
    assert doc.text.splitlines() == ["通知", "正文第一段", "代码 | 线", "085404 | 379"]


def test_scanned_pdf_flagged_not_failed(tmp_path: Path) -> None:
    from PIL import Image

    path = tmp_path / "scan.pdf"
    Image.new("RGB", (200, 100), "white").save(path, "PDF")
    doc = load_file(path)
    assert doc.pages == [] and doc.ocr_pages == [1] and doc.needs_ocr


def test_empty_pdf_still_raises(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as f:
        writer.write(f)
    with pytest.raises(ValueError, match="No extractable text"):
        load_file(path)


def test_ocr_backend_registry() -> None:
    backend = get_ocr_backend("none")
    assert backend.name == "none" and not backend.available() and backend.recognize(b"") is None
    assert get_ocr_backend("rapidocr").name == "rapidocr"
    with pytest.raises(ValueError, match="not implemented"):
        get_ocr_backend("paddleocr")
    with pytest.raises(ValueError, match="Unknown"):
        get_ocr_backend("tesseract")
