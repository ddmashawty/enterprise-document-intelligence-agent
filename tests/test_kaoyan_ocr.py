import io
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageDraw

from doc_agent.config import Settings
from doc_agent.ingest import pipeline
from doc_agent.ingest.loaders import load_file
from doc_agent.ingest.ocr import (
    CachedOCR,
    OCRBox,
    OCRResult,
    VisionBackend,
    fix_cjk_punct,
    get_ocr_backend,
    group_lines,
    join_pieces,
    markdown_tables,
)
from doc_agent.ingest.ocr_table import rebuild_table
from doc_agent.ingest.tables import Table
from doc_agent.kaoyan.db import KaoyanStore
from doc_agent.kaoyan.extract.base import ExtractContext
from doc_agent.kaoyan.extract.scut_baseline_img import ScutBaselineImage
from doc_agent.kaoyan.extract.scut_subjects_img import ScutSubjectsImage
from doc_agent.kaoyan.roster import count_lines, count_results, roster_counts

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "kaoyan"
IMAGE_DOCS = ["scut-040", "scut-049", "scut-061", "sysu-089", "sysu-092", "sysu-095"]


def _settings(tmp_path: Path, **kw: object) -> Settings:
    return Settings(_env_file=None, llm_api_key="", ocr_cache_dir=str(tmp_path / "ocr_cache"), **kw)  # type: ignore[call-arg]


class FakeOCR:
    name = "fake"

    def __init__(self, result: OCRResult | None = None, *, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def available(self) -> bool:
        return True

    def recognize(self, image: bytes) -> OCRResult | None:
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


# --- synthetic ruled table ------------------------------------------------------
# 400x200: dark header band (y 10-40), thin rows at 70/100/130, columns at 10/110/250/390.
# Column 0 has no line at y=100 (rows 2-3 merged); column line 250 stops at y=102 (row 3
# merges columns 1-2). A footnote sits below the table.

EXPECTED = [
    ["学院", "专业", "总分"],
    ["软件学院", "083500软件工程", "330"],
    ["计算机学院", "081200计算机科学与技术", "340"],
    ["计算机学院", "备注：含少干计划", "备注：含少干计划"],
]


def _grid_image(scale: int = 1) -> Image.Image:
    img = Image.new("RGB", (400 * scale, 200 * scale), "white")
    d = ImageDraw.Draw(img)

    def rect(x0: int, y0: int, x1: int, y1: int, fill: str | tuple[int, int, int]) -> None:
        d.rectangle([x0 * scale, y0 * scale, (x1 + 1) * scale - 1, (y1 + 1) * scale - 1], fill=fill)

    rect(10, 10, 391, 39, (31, 78, 121))
    rect(10, 70, 391, 71, "black")
    rect(110, 100, 391, 101, "black")
    rect(10, 130, 391, 131, "black")
    for x in (10, 110, 390):
        rect(x, 10, x + 1, 131, "black")
    rect(250, 10, 251, 101, "black")
    return img


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _boxes(scale: int = 1) -> list[OCRBox]:
    def box(text: str, cx: float, cy: float, w: float = 40, h: float = 12) -> OCRBox:
        return OCRBox(text, ((cx - w / 2) * scale, (cy - h / 2) * scale, (cx + w / 2) * scale, (cy + h / 2) * scale))

    return [
        box("学院", 60, 25), box("专业", 180, 25), box("总分", 320, 25),
        box("软件学院", 60, 55), box("083500软件工程", 180, 55, 100), box("330", 320, 55),
        box("计算机学院", 60, 101),  # centered in the merged cell, i.e. on the missing line
        box("081200计算机科学与技术", 180, 86, 120), box("340", 320, 86),
        box("备注：含少干计划", 251, 116, 120),
        box("注：数据为示例", 100, 170, 120),
    ]


def test_rebuild_table_merges_and_header_band() -> None:
    grid = rebuild_table(_png(_grid_image()), _boxes())
    assert grid is not None
    assert grid.cells == EXPECTED
    assert grid.origins[2][0] == grid.origins[3][0]
    assert grid.origins[3][1] == grid.origins[3][2]
    assert grid.origins[1][0] != grid.origins[2][0]


def test_rebuild_table_without_grid() -> None:
    assert rebuild_table(_png(Image.new("RGB", (200, 100), "white")), _boxes()) is None
    assert rebuild_table(_png(_grid_image()), []) is None


# --- text helpers ---------------------------------------------------------------


def test_fix_cjk_punct() -> None:
    assert fix_cjk_punct("英语 (一)") == "英语（一）"
    assert fix_cjk_punct("数学(二),英语") == "数学（二），英语"
    assert fix_cjk_punct("GPA (4.0), top") == "GPA (4.0), top"


def test_join_and_group_lines() -> None:
    assert join_pieces(["计算机", "学院"]) == "计算机学院"
    assert join_pieces(["deep", "learning", "（一）"]) == "deep learning（一）"
    boxes = [OCRBox("学院", (60, 0, 100, 12)), OCRBox("计算机", (0, 1, 58, 13)), OCRBox("第二行", (0, 30, 50, 42))]
    assert group_lines(boxes) == ["计算机学院", "第二行"]


def test_markdown_tables() -> None:
    text = "```markdown\n标题\n| 专业 | 总分 |\n|---|---:|\n| 083500 | 330 |\n\n注：示例\n```"
    tables, lines = markdown_tables(text)
    assert tables == [[["专业", "总分"], ["083500", "330"]]]
    assert lines == ["标题", "注：示例"]


# --- backends -------------------------------------------------------------------


def test_backend_registry_and_cache_dir(tmp_path: Path) -> None:
    s = _settings(tmp_path, vision_base_url="http://vision.test/v1", vision_model="qwen-vl/max", vision_api_key="k")
    cached = get_ocr_backend("vision", s)
    assert isinstance(cached, CachedOCR) and cached.available()
    assert cached.dir == tmp_path / "ocr_cache" / "vision-qwen-vl_max"
    assert not get_ocr_backend("vision", _settings(tmp_path)).available()
    assert get_ocr_backend("rapidocr", s).name == "rapidocr"
    with pytest.raises(ValueError, match="needs settings"):
        get_ocr_backend("vision")
    with pytest.raises(ValueError, match="not implemented"):
        get_ocr_backend("paddleocr", s)


def test_vision_backend_request_and_tables() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        content = "复试分数线\n| 专业代码 | 总分 |\n| --- | --- |\n| 085405 | 314 |"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    backend = VisionBackend("http://vision.test/v1/", "vl-model", "secret", transport=httpx.MockTransport(handler))
    result = backend.recognize(_png(_grid_image()))
    assert result is not None and result.backend == "vision"
    assert result.tables == [[["专业代码", "总分"], ["085405", "314"]]]
    assert result.lines == ["复试分数线"]
    assert seen["url"] == "http://vision.test/v1/chat/completions"
    assert seen["auth"] == "Bearer secret"
    body = seen["body"]
    assert isinstance(body, dict) and body["model"] == "vl-model" and body["temperature"] == 0
    image_part = body["messages"][1]["content"][1]
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


def test_cached_ocr_skips_second_call(tmp_path: Path) -> None:
    inner = FakeOCR(OCRResult(text="a", backend="fake", lines=["a"], boxes=_boxes()))
    cached = CachedOCR(inner, tmp_path)
    first, second = cached.recognize(b"img"), cached.recognize(b"img")
    assert inner.calls == 1
    assert first is not None and second is not None
    assert second.boxes == first.boxes and second.lines == ["a"]
    assert cached.path_for(b"img").parent == tmp_path / "fake"


# --- loaders --------------------------------------------------------------------


def test_load_image_with_box_backend(tmp_path: Path) -> None:
    path = tmp_path / "table.png"
    _grid_image().save(path)
    doc = load_file(path, ocr=FakeOCR(OCRResult(text="", backend="fake", boxes=_boxes())))
    (table,) = doc.tables
    assert table.cells == EXPECTED and table.origins is not None
    assert not doc.needs_ocr and doc.meta["ocr_applied"] == [1]
    assert "注：数据为示例" in doc.text
    assert "083500软件工程 | 330" in doc.text


def test_load_image_vision_tables_used_as_is(tmp_path: Path) -> None:
    path = tmp_path / "table.png"
    _grid_image().save(path)
    result = OCRResult(text="", backend="vision", lines=["标题"], tables=[[["专业", "总分"], ["083500", "330"]]])
    doc = load_file(path, ocr=FakeOCR(result))
    assert doc.tables[0].cells == [["专业", "总分"], ["083500", "330"]]
    assert doc.text.startswith("标题")


def test_load_image_backend_error_keeps_needs_ocr(tmp_path: Path) -> None:
    path = tmp_path / "table.png"
    _grid_image().save(path)
    doc = load_file(path, ocr=FakeOCR(error=RuntimeError("boom")))
    assert doc.needs_ocr and not doc.pages
    assert doc.meta["ocr_error"] == "RuntimeError: boom"


def test_scanned_pdf_pages_are_ocred(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    _grid_image().save(path, "PDF", resolution=72)
    assert load_file(path).needs_ocr
    backend = FakeOCR(OCRResult(text="", backend="fake", boxes=_boxes(scale=2)))
    doc = load_file(path, tables=True, ocr=backend)
    assert backend.calls == 1
    assert doc.tables[0].cells == EXPECTED and doc.tables[0].page == 1
    assert doc.meta["ocr_applied"] == [1] and doc.ocr_pages == [] and not doc.needs_ocr


def test_personal_files_are_never_ocred(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    for name in ("roster.png", "table.png"):
        _grid_image().save(raw / name)
    (tmp_path / "sources.json").write_text(json.dumps({"documents": [
        {"doc_id": "t-001", "local_path": "raw/roster.png", "contains_personal_data": True},
        {"doc_id": "t-002", "local_path": "raw/table.png"},
    ]}), encoding="utf-8")
    backend = FakeOCR(OCRResult(text="", backend="fake", boxes=_boxes()))
    monkeypatch.setattr(pipeline, "get_ocr_backend", lambda name, s: backend)
    s = _settings(tmp_path, kaoyan_data_dir=str(tmp_path), ocr_backend="rapidocr")
    roster = pipeline.load_document(raw / "roster.png", s)
    assert backend.calls == 0 and roster.needs_ocr and not roster.tables
    table = pipeline.load_document(raw / "table.png", s)
    assert backend.calls == 1 and table.tables


# --- extractors on OCR-shaped tables (shapes copied from the rebuilt real images) --


def _ctx(**kw: object) -> ExtractContext:
    base = {"doc_id": "t-img", "school_id": "scut", "year": 2026, "format": "img"}
    return ExtractContext(**{**base, **kw})  # type: ignore[arg-type]


def _ocr_doc(cells: list[list[str]], origins: list[list[tuple[int, int]]] | None = None):
    from doc_agent.ingest.loaders import DocumentPage, ParsedDocument

    return ParsedDocument(source="ocr", pages=[DocumentPage("ocr", 1, "")],
                          tables=[Table(cells=cells, index=0, origins=origins)], meta={"ocr_applied": [1]})


def test_scut_baseline_image_rows() -> None:
    cells = [
        ["学科门类", "级学科、专业学位类别（以下简称学科专业）", "总分", "单科（满分=100分）", "单科（满分>100分）"],
        ["08工学", "各学科专业", "290", "40", "60"],
        ["12管理学", "125603工业工程与管理、125604物流工程与管理", "185", "40", "80"],
        ["说明", "以上为基本要求", "", "", ""],
    ]
    ctx = _ctx(doc_type="score_line")
    assert ScutBaselineImage().matches(ctx) and not ScutBaselineImage().matches(_ctx(doc_type="score_line", format="html"))
    lines = ScutBaselineImage().extract(_ocr_doc(cells), ctx)
    assert [(f.values["discipline_code"], f.values["total"], f.values["politics"], f.values["subject2"])
            for f in lines] == [("08", 290, 40, 60), ("125603", 185, 40, 80), ("125604", 185, 40, 80)]
    assert all(f.kind == "school_baseline" and f.program is None for f in lines)
    assert "工学各学科专业" in lines[0].values["definition"]


def test_scut_subjects_image_merged_programs() -> None:
    cells = [["招生专业代码及名称", "初试科目设置", "涉及招生学院"]]
    origins = [[(0, 0), (0, 1), (0, 2)]]
    for i, subject in enumerate(["101 思想政治理论", "201英语（一）", "301数学（一）", "811信号与系统"], start=1):
        cells.append(["081100控制科学与工程085400电子信息", subject, "自动化科学与工程学院"])
        origins.append([(1, 0), (i, 1), (1, 2)])
    ctx = _ctx(doc_type="subject_change", year=2027)
    facts = ScutSubjectsImage().extract(_ocr_doc(cells, origins), ctx)
    by_code: dict[str, list[str]] = {}
    for f in facts:
        assert f.program is not None and f.program.college == "自动化科学与工程学院"
        by_code.setdefault(f.program.code, []).append(f.values["code"])
    assert by_code == {"081100": ["101", "201", "301", "811"], "085400": ["101", "201", "301", "811"]}


# --- scanned roster: counts only --------------------------------------------------

ROSTER_LINES = [
    "华南理工大学2026年拟录取名单",
    "序号 姓名 考生编号 专业代码 专业名称 总分",
    "1 张某 105611234500001 085404 计算机技术 401",
    "2 王某 105611234500002 085404 计算机技术 399",
    "3 赵某 105611234500003 081200 计算机科学与技术 388",
    "4 合并行 081200 085404",
]


def test_roster_count_lines() -> None:
    assert count_lines(ROSTER_LINES) == {"085404": 2, "081200": 1}


def test_roster_count_results_and_failed_pages() -> None:
    boxes = [OCRBox(line, (0, 20 * i, 300, 20 * i + 12)) for i, line in enumerate(ROSTER_LINES)]
    out = count_results([OCRResult(text="", backend="fake", boxes=boxes), None,
                         OCRResult(text="", backend="fake", lines=ROSTER_LINES[2:3])])
    assert out.summary() == {"total": 4, "by_program_code": {"081200": 1, "085404": 3}, "pages": 3, "pages_failed": [2]}


def test_roster_counts_on_scanned_pdf_reports_no_personal_data(tmp_path: Path) -> None:
    path = tmp_path / "roster.pdf"
    pages = [Image.new("RGB", (300, 200), "white") for _ in range(2)]
    pages[0].save(path, "PDF", resolution=72, save_all=True, append_images=pages[1:])
    out = roster_counts(path, FakeOCR(OCRResult(text="", backend="fake", lines=ROSTER_LINES)), pages=[2])
    summary = json.dumps(out.summary(), ensure_ascii=False)
    assert out.total == 3 and out.pages == 1 and out.pages_failed == []
    assert "某" not in summary and "1056112345" not in summary


# --- real images (local bundle + optional rapidocr) ----------------------------------


def test_real_ocr_extraction_matches_seeds(tmp_path: Path) -> None:
    pytest.importorskip("rapidocr_onnxruntime")
    from doc_agent.kaoyan.extract.run import document_contexts, run_extraction
    from doc_agent.kaoyan.seed import seed_kaoyan

    if not (DATA_DIR / "sources.json").exists():
        pytest.skip("data/kaoyan bundle not present")
    local = {ctx.doc_id for path, ctx in document_contexts(DATA_DIR) if path.exists()}
    if not set(IMAGE_DOCS) <= local:
        pytest.skip("image fixtures missing")
    store = KaoyanStore(tmp_path / "kaoyan.db")
    seed_kaoyan(store, DATA_DIR)
    run = run_extraction(store, _settings(tmp_path, ocr_backend="rapidocr"), doc_ids=IMAGE_DOCS)
    assert {d.doc_id: d.status for d in run.docs} == dict.fromkeys(IMAGE_DOCS, "ok")
    assert run.facts and all(f.extraction_method == "ocr" for f in run.facts)
    assert run.apply is not None
    counts = run.apply.counts()
    assert counts.get("conflict", 0) == 0 and counts.get("match", 0) >= 17
    # OCR facts are only verified where they equal a seed; everything else stays verified=0
    assert store.count("score_lines", "extraction_method = 'ocr' AND verified = 1") > 0
    assert store.count("score_lines", "extraction_method = 'ocr' AND verified = 0") > 0
