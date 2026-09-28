import csv
import re
from pathlib import Path

import pytest

from doc_agent.config import Settings
from doc_agent.ingest.loaders import DocumentPage, ParsedDocument, load_file
from doc_agent.ingest.pipeline import load_document
from doc_agent.ingest.redact import (
    NAME_HEADER,
    find_header,
    is_personal_table,
    mask_lead_names,
    mask_name,
    redact_document,
    redact_tables,
    redact_text,
)
from doc_agent.ingest.tables import Table, render_page

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "kaoyan"

# synthetic placeholder names only; never real candidates
LIST = Table(
    [
        ["序号", "考生编号", "考生姓名", "初试成绩"],
        ["1", "105586000000001", "测试甲", "350"],
        ["2", "105586000000002", "欧阳测试", "341"],
    ],
    page=1,
    index=0,
)


def test_mask_name() -> None:
    assert mask_name("测试甲") == "测某"
    assert mask_name("欧阳测试") == "欧阳某"
    assert mask_name(" 李 四 ") == "李某"
    assert mask_name("") == ""


def test_find_header_variants() -> None:
    assert find_header(LIST) == (0, [2], [1])
    variants = Table([["考生编号（后五位）", "姓名", "总分"], ["00001", "测试乙", "300"]])
    assert find_header(variants) == (0, [1], [0])
    assert is_personal_table(variants)
    contacts = Table([["姓名", "职务", "电话"], ["测试丙", "秘书", "020-1"]])
    assert not is_personal_table(contacts)


def test_redact_tables_masks_and_drops_ids() -> None:
    continued = Table([["3", "105586000000003", "测试丁", "330"]], page=2, index=1)
    (first, second), names = redact_tables([LIST, continued])
    assert first.cells == [["序号", "考生姓名", "初试成绩"], ["1", "测某", "350"], ["2", "欧阳某", "341"]]
    assert second.cells == [["3", "测某", "330"]]
    assert names == {"测试甲", "欧阳测试", "测试丁"}


def test_redact_text_safety_net() -> None:
    text = "测试甲放弃复试，考生编号105586000000001；身份证44010119900101123X；电话02012345678"
    out = redact_text(text, {"测试甲"})
    assert "测试甲" not in out and "测某放弃复试" in out
    assert "105586000000001" not in out and "44010119900101123X" not in out
    assert "02012345678" in out


def test_lead_names_in_public_notices() -> None:
    assert mask_lead_names("经审核，拟录取测试甲等2582人为硕士研究生") == "经审核，拟录取测某等2582人为硕士研究生"
    assert mask_lead_names("同意接收欧阳测试等 12 名") == "同意接收欧阳某等 12 名"
    assert mask_lead_names("接收推免生等100人") == "接收推免生等100人"
    assert mask_lead_names("录取人数为50人") == "录取人数为50人"


def test_load_document_masks_lead_names_in_kaoyan_notices(tmp_path: Path) -> None:
    root = tmp_path / "kaoyan"
    (root / "raw").mkdir(parents=True)
    page = root / "raw" / "通知.html"
    page.write_text("<p>学校审定，拟录取测试庚等2582人为硕士研究生。</p>", encoding="utf-8")
    doc = load_document(page, Settings(kaoyan_data_dir=str(root)))
    assert "测试庚" not in doc.text and "拟录取测某等2582人" in doc.text
    assert not doc.meta.get("redacted")


def test_redact_document_rerenders_pages() -> None:
    prose = "复试名单\n[[TABLE:0]]\n备注：测试甲为专项计划"
    doc = ParsedDocument(
        source="x.html",
        pages=[DocumentPage("x.html", 1, render_page(prose, [LIST]))],
        tables=[LIST],
        meta={"prose": {1: prose}},
    )
    red = redact_document(doc)
    assert red.meta["redacted"] is True
    assert red.pages[0].text.splitlines() == [
        "复试名单", "序号 | 考生姓名 | 初试成绩", "1 | 测某 | 350", "2 | 欧阳某 | 341", "备注：测某为专项计划",
    ]
    assert "测试甲" not in red.meta["prose"][1]
    assert doc.tables[0].cells[1][2] == "测试甲"  # input untouched


def test_load_document_auto_detects_lists_outside_bundle(tmp_path: Path) -> None:
    page = tmp_path / "名单.html"
    page.write_text(
        "<table><tr><td>考生编号</td><td>姓名</td><td>总分</td></tr>"
        "<tr><td>105586000000009</td><td>测试戊</td><td>360</td></tr></table>",
        encoding="utf-8",
    )
    s = Settings(kaoyan_data_dir=str(tmp_path / "none"))
    doc = load_document(page, s)
    assert doc.meta.get("redacted") and "测试戊" not in doc.text and "105586000000009" not in doc.text
    plain = tmp_path / "通讯录.html"
    plain.write_text("<table><tr><td>姓名</td><td>职务</td></tr><tr><td>测试己</td><td>秘书</td></tr></table>", encoding="utf-8")
    assert "测试己" in load_document(plain, s).text


def _personal_files() -> list[Path]:
    manifest = DATA / "raw" / "manifest.csv"
    if not manifest.exists():
        return []
    with manifest.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return [DATA / r["local_path"] for r in rows if r["contains_personal_data"] == "True" and (DATA / r["local_path"]).exists()]


def test_no_names_or_exam_numbers_leak_from_local_lists() -> None:
    files = _personal_files()
    if not files:
        pytest.skip("local-only personal-data files not present")
    s = Settings()
    failures: list[str] = []
    for path in files:
        raw = load_file(path, tables=True)
        _, names = redact_tables(raw.tables)
        names = {n for n in names if len(n) >= 2 and not NAME_HEADER.match(n)}
        text = load_document(path, s).text
        leaked = sum(1 for n in names if n in text)
        exam_nos = len(re.findall(r"(?<!\d)\d{15}(?!\d)", text))
        if not names or leaked or exam_nos:
            # counts only: never put names or numbers into test output
            failures.append(f"{path.name}: names={len(names)} leaked={leaked} exam_nos={exam_nos}")
    assert not failures, failures
