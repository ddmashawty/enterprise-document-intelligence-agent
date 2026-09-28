from pathlib import Path

import pytest

from doc_agent.collect.attachments import discover_attachments

RAW = Path(__file__).resolve().parents[1] / "data" / "kaoyan" / "raw"


def _html(rel: str) -> str:
    path = RAW / rel
    if not path.exists():
        pytest.skip(f"fixture missing: {rel}")
    return path.read_text(encoding="utf-8")


def test_scut_pdf_players_use_sudyfile_names() -> None:
    atts = discover_attachments(
        _html("scut/scut_cs_2026_统考入围复试名单_20260316.html"),
        "https://www2.scut.edu.cn/cs/_t2382/2026/0316/c45223a620243/page.psp",
    )
    players = [a for a in atts if a.kind == "pdf_player"]
    assert [a.name for a in players] == ["2026学硕.pdf", "2026专硕.pdf"]
    prefix = "https://www2.scut.edu.cn/_upload/article/files/d2/d5/b0f6adff46f699eda84585c02dcc/"
    assert [a.url for a in players] == [
        prefix + "a538a047-379c-4717-809d-eff7e4b00c10.pdf",
        prefix + "f5dc78bc-4321-4b39-9df9-d7773a5e963e.pdf",
    ]
    assert all(a.ext == ".pdf" for a in players)


def test_sysu_sece_relative_links_and_data_uri() -> None:
    atts = discover_attachments(
        _html("sysu/sysu_sece_2026_复试录取实施细则.html"),
        "https://sece.sysu.edu.cn/zs/zs01/1420941.htm",
    )
    links = {a.name: a.url for a in atts if a.kind == "link"}
    assert links["复试名单.pdf"] == "https://sece.sysu.edu.cn/docs/2026-03/20260317181605259414.pdf"
    assert len(links) == 4 and all(u.startswith("https://sece.sysu.edu.cn/docs/2026-03/") for u in links.values())
    (inline,) = [a for a in atts if a.kind == "data_uri"]
    assert inline.sha256.startswith("19cedf27") and inline.mime == "image/png" and inline.data
    images = [a for a in atts if a.kind == "image"]
    assert "https://sece.sysu.edu.cn/images/logo.png" in {a.url for a in images}
    assert not [a for a in discover_attachments(_html("sysu/sysu_sece_2026_复试录取实施细则.html"), include_images=False)
                if a.kind in ("image", "data_uri")]


def test_jnu_uuid_links_named_by_anchor_text() -> None:
    atts = discover_attachments(
        _html("jnu/jnu_2026_各学院硕士复试方案_20260320.html"),
        "https://yz.jnu.edu.cn/2026/0320/c33059a852118/page.htm",
    )
    links = [a for a in atts if a.kind == "link"]
    assert len(links) == 47 and {a.ext for a in links} == {".xlsx"}
    by_name = {a.name: a.url for a in links}
    assert by_name["暨南大学2026年052网络空间安全学院复试方案.xlsx"] == (
        "https://yz.jnu.edu.cn/_upload/article/files/95/2f/d77a954b4ae2a4f488e139852188/"
        "db0fa170-032e-456c-9491-8fc5473bb435.xlsx"
    )


def test_handwritten_page_rules() -> None:
    html = """
    <html><head><base href="https://example.edu.cn/news/"></head><body>
      <a href="#top">顶部</a>
      <a href="javascript:void(0)">打印</a>
      <a href="list.htm">更多通知</a>
      <a href="files/a1b2.pdf">复试名单</a>
      <a href="/_upload/x/9f.xlsx" sudyfile-attr="{'title':'计划表.xlsx'}">点击下载</a>
      <a href="/down?id=7" sudyfile-attr="{'title':'细则.docx'}">细则</a>
      <a href="files/a1b2.pdf">重复链接</a>
      <div class="wp_pdf_player" pdfsrc="/_upload/p.pdf"></div>
    </body></html>"""
    atts = discover_attachments(html, "https://ignored.example/")
    got = [(a.kind, a.name, a.url) for a in atts]
    assert got == [
        ("pdf_player", "p.pdf", "https://example.edu.cn/_upload/p.pdf"),
        ("link", "复试名单.pdf", "https://example.edu.cn/news/files/a1b2.pdf"),
        ("link", "计划表.xlsx", "https://example.edu.cn/_upload/x/9f.xlsx"),
        ("link", "细则.docx", "https://example.edu.cn/down?id=7"),
    ]
