#!/usr/bin/env python3
"""Download public demo documents for the enterprise document agent."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
ANNUAL = RAW / "annual_reports"
POLICIES = RAW / "policies"
MANUALS = RAW / "manuals"
MANIFEST = ROOT / "data" / "SOURCES.md"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

CNINFO_TOP = "https://www.cninfo.com.cn/new/information/topSearch/query"
CNINFO_QUERY = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC = "https://static.cninfo.com.cn/"

# Comparable A-share names for multi-doc contrast demos
STOCKS = [
    {"code": "600519", "name": "贵州茅台", "column": "sse"},
    {"code": "000858", "name": "五粮液", "column": "szse"},
    {"code": "300750", "name": "宁德时代", "column": "szse"},
]

# Extra public PDFs (policies / manuals) for broader PRD scenario coverage
EXTRA_DOCS = [
    {
        "url": "https://www.sse.com.cn/lawandrules/sselawsrules/stocks/mainipo/c/c_20231229_5737473.shtml",
        "fallback_urls": [
            # SSE listing rules HTML pages vary; use known stable public PDFs below instead
        ],
        "path": None,  # placeholder; real extras listed separately
    }
]

# Stable public PDFs that do not require login
PUBLIC_PDFS = [
    {
        "category": "policies",
        "filename": "中国证监会_上市公司信息披露管理办法.pdf",
        "title": "上市公司信息披露管理办法（证监会令）",
        "urls": [
            # Multiple candidate mirrors; first successful wins
            "https://www.csrc.gov.cn/csrc/c101864/c1024635/content.shtml",
        ],
        "note": "If HTML only, skip and use alternative sources below.",
    },
]


def http_request(
    url: str,
    *,
    data: dict | None = None,
    timeout: int = 60,
) -> bytes:
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        headers["Origin"] = "https://www.cninfo.com.cn"
        headers["Referer"] = "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch"
        headers["X-Requested-With"] = "XMLHttpRequest"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def safe_name(text: str) -> str:
    text = re.sub(r"[\\/:*?\"<>|\s]+", "_", text.strip())
    text = re.sub(r"_+", "_", text)
    return text[:120].strip("_")


def resolve_org_id(code: str) -> str | None:
    raw = http_request(
        CNINFO_TOP,
        data={"keyWord": code, "maxNum": 10},
    )
    items = json.loads(raw.decode("utf-8"))
    if not isinstance(items, list):
        return None
    for item in items:
        if str(item.get("code", "")).startswith(code):
            return item.get("orgId")
    return items[0].get("orgId") if items else None


def find_latest_annual(code: str, org_id: str, column: str) -> dict | None:
    # Prefer full annual reports published in recent windows
    windows = [
        "2024-01-01~2025-06-30",
        "2023-01-01~2024-06-30",
        "2022-01-01~2023-06-30",
    ]
    for se_date in windows:
        raw = http_request(
            CNINFO_QUERY,
            data={
                "pageNum": "1",
                "pageSize": "30",
                "column": column,
                "tabName": "fulltext",
                "plate": "",
                "stock": f"{code},{org_id}",
                "searchkey": "",
                "secid": "",
                "category": "category_ndbg_szsh",
                "trade": "",
                "seDate": se_date,
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            },
        )
        payload = json.loads(raw.decode("utf-8"))
        anns = payload.get("announcements") or []
        # Prefer titles that look like full annual report, not摘要/英文版/更正
        ranked = []
        for a in anns:
            title = a.get("announcementTitle") or ""
            if "英文" in title or "更正" in title or "取消" in title:
                continue
            score = 0
            if "年度报告" in title or "年报" in title:
                score += 5
            if "摘要" in title:
                score -= 3
            if "全文" in title:
                score += 2
            ranked.append((score, a))
        ranked.sort(key=lambda x: x[0], reverse=True)
        if ranked and ranked[0][0] > 0:
            return ranked[0][1]
    return None


def download_file(url: str, dest: Path, timeout: int = 180) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/pdf,*/*",
            "Referer": "https://www.cninfo.com.cn/",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read()
        ctype = (resp.headers.get("Content-Type") or "").lower()
    if len(content) < 10_000:
        raise RuntimeError(f"File too small ({len(content)} bytes): {url}")
    if "pdf" not in ctype and not content.startswith(b"%PDF"):
        raise RuntimeError(f"Not a PDF ({ctype}): {url}")
    dest.write_bytes(content)


def download_annual_reports(sources: list[dict]) -> list[dict]:
    results = []
    for stock in STOCKS:
        code, name, column = stock["code"], stock["name"], stock["column"]
        print(f"[annual] resolving {code} {name} ...")
        try:
            org_id = resolve_org_id(code)
            if not org_id:
                print(f"  ! orgId not found for {code}")
                continue
            ann = find_latest_annual(code, org_id, column)
            if not ann:
                print(f"  ! annual report not found for {code}")
                continue
            title = ann.get("announcementTitle") or "annual_report"
            adjunct = ann.get("adjunctUrl") or ""
            url = CNINFO_STATIC + adjunct
            filename = f"{code}_{safe_name(name)}_{safe_name(title)}.pdf"
            dest = ANNUAL / filename
            if dest.exists() and dest.stat().st_size > 10_000:
                print(f"  = exists: {dest.name}")
            else:
                print(f"  ↓ {url}")
                download_file(url, dest)
                time.sleep(1.0)
                print(f"  ✓ saved {dest.name} ({dest.stat().st_size // 1024} KB)")
            results.append(
                {
                    "category": "annual_reports",
                    "code": code,
                    "name": name,
                    "title": title,
                    "url": url,
                    "path": str(dest.relative_to(ROOT)),
                    "bytes": dest.stat().st_size,
                }
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ! failed {code}: {exc}")
    return results


def download_public_extras(sources: list[dict]) -> list[dict]:
    """Download a few stable public PDFs for policy / manual demos."""
    stable = [
        {
            "category": "policies",
            "filename": "联合国_世界人权宣言_中文.pdf",
            "title": "世界人权宣言（联合国公开中文版，制度条款抽取演示）",
            "source": "https://www.un.org/zh/about-us/universal-declaration-of-human-rights",
            "urls": [
                "https://www.ohchr.org/sites/default/files/UDHR/Documents/UDHR_Translations/chn.pdf",
            ],
        },
        {
            "category": "manuals",
            "filename": "RFC793_TCP_Specification.pdf",
            "title": "RFC 793 Transmission Control Protocol（技术规范手册演示）",
            "source": "https://www.rfc-editor.org/rfc/rfc793",
            "urls": [
                "https://www.rfc-editor.org/rfc/pdfrfc/rfc793.txt.pdf",
                "https://www.rfc-editor.org/rfc/rfc793.pdf",
            ],
        },
        {
            "category": "manuals",
            "filename": "W3C_HTML5_A_vocabulary_and_associated_APIs.pdf",
            "title": "HTML5 W3C Recommendation excerpt PDF（产品/技术文档演示）",
            "source": "https://www.w3.org/TR/html52/",
            "urls": [
                "https://www.w3.org/TR/2017/REC-html52-20171214/single-page.html",
            ],
        },
    ]

    # Use annual-report-adjacent public Chinese PDF: 中国人民银行政策报告 if available
    # Also add a Chinese government whitepaper PDF which is commonly downloadable
    stable.extend(
        [
            {
                "category": "policies",
                "filename": "中国政府_网络安全法_全文.pdf",
                "title": "中华人民共和国网络安全法（公开法律文本演示）",
                "source": "http://www.npc.gov.cn/",
                "urls": [
                    # NPC / gov often serve HTML; try known PDF mirrors
                    "https://www.gov.cn/xinwen/2016-11/07/content_5129723.htm",
                ],
            },
        ]
    )

    results = []
    # First try annual-adjacent: skip HTML-only extras, focus on PDFs we can verify
    candidates = [
        {
            "category": "policies",
            "filename": "OHCHR_世界人权宣言_中文.pdf",
            "title": "世界人权宣言（OHCHR 中文 PDF）",
            "source": "https://www.ohchr.org/zh/human-rights/universal-declaration/translations/chinese",
            "urls": [
                "https://www.ohchr.org/sites/default/files/UDHR/Documents/UDHR_Translations/chn.pdf",
            ],
        },
        {
            "category": "manuals",
            "filename": "RFC793_TCP.pdf",
            "title": "RFC 793 TCP Specification",
            "source": "https://www.rfc-editor.org/rfc/rfc793",
            "urls": [
                "https://www.rfc-editor.org/rfc/pdfrfc/rfc793.txt.pdf",
            ],
        },
        {
            "category": "manuals",
            "filename": "ISO_C_Language_Draft_n1570.pdf",
            "title": "ISO/IEC 9899:201x Committee Draft n1570（技术手册长文档）",
            "source": "https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf",
            "urls": [
                "https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf",
            ],
        },
    ]

    for item in candidates:
        dest_dir = POLICIES if item["category"] == "policies" else MANUALS
        dest = dest_dir / item["filename"]
        ok = False
        if dest.exists() and dest.stat().st_size > 10_000 and dest.read_bytes()[:4] == b"%PDF":
            print(f"[extra] exists: {dest.name}")
            ok = True
        else:
            for url in item["urls"]:
                try:
                    print(f"[extra] ↓ {url}")
                    download_file(url, dest)
                    print(f"  ✓ saved {dest.name} ({dest.stat().st_size // 1024} KB)")
                    ok = True
                    break
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! {exc}")
        if ok:
            results.append(
                {
                    "category": item["category"],
                    "title": item["title"],
                    "source": item["source"],
                    "url": item["urls"][0],
                    "path": str(dest.relative_to(ROOT)),
                    "bytes": dest.stat().st_size,
                }
            )
            sources.append(results[-1])
    return results


def write_short_docx_samples() -> list[dict]:
    """Create controllable Word samples for gold-answer demos without external deps if possible."""
    # Prefer python-docx if available; otherwise write a minimal .txt companion and skip docx
    results = []
    try:
        from docx import Document  # type: ignore
    except ImportError:
        # Write plain text stand-ins that the ingest pipeline can also accept later
        samples = [
            (
                MANUALS / "演示产品参数手册.txt",
                "演示产品参数手册\n\n"
                "产品名称：DocMind Agent Pro\n"
                "版本：1.0.0\n"
                "支持格式：PDF、Word、Markdown\n"
                "最大文档页数：100\n"
                "向量库：Chroma\n"
                "默认模型：通义千问 / DeepSeek\n"
                "关键参数：\n"
                "- 切片大小：500 tokens\n"
                "- TopK：5\n"
                "- 工具调用上限：5\n"
                "- 问答响应目标：≤3s\n",
            ),
            (
                POLICIES / "演示企业文档管理制度.txt",
                "演示企业文档管理制度\n\n"
                "第一条 目的\n本制度用于规范企业内部文档的创建、存储、检索与归档。\n\n"
                "第二条 适用范围\n适用于全体员工及外包协作人员。\n\n"
                "第三条 保密等级\n公开、内部、秘密、机密四级。\n\n"
                "第四条 保存期限\n普通文档不少于3年，财务与合规文档不少于10年。\n\n"
                "第五条 违规处理\n未经授权外传机密文档，按公司纪律条例处理。\n",
            ),
        ]
        for path, text in samples:
            path.write_text(text, encoding="utf-8")
            results.append(
                {
                    "category": "policies" if "制度" in path.name else "manuals",
                    "title": path.stem,
                    "source": "project-generated controllable sample",
                    "url": "",
                    "path": str(path.relative_to(ROOT)),
                    "bytes": path.stat().st_size,
                }
            )
        return results

    doc1 = Document()
    doc1.add_heading("演示产品参数手册", level=1)
    doc1.add_paragraph("产品名称：DocMind Agent Pro")
    doc1.add_paragraph("版本：1.0.0")
    doc1.add_paragraph("支持格式：PDF、Word、Markdown")
    doc1.add_paragraph("最大文档页数：100")
    for line in [
        "切片大小：500 tokens",
        "TopK：5",
        "工具调用上限：5",
        "问答响应目标：≤3s",
    ]:
        doc1.add_paragraph(line, style="List Bullet")
    p1 = MANUALS / "演示产品参数手册.docx"
    doc1.save(p1)
    results.append(
        {
            "category": "manuals",
            "title": "演示产品参数手册",
            "source": "project-generated",
            "url": "",
            "path": str(p1.relative_to(ROOT)),
            "bytes": p1.stat().st_size,
        }
    )

    doc2 = Document()
    doc2.add_heading("演示企业文档管理制度", level=1)
    for title, body in [
        ("第一条 目的", "本制度用于规范企业内部文档的创建、存储、检索与归档。"),
        ("第二条 适用范围", "适用于全体员工及外包协作人员。"),
        ("第三条 保密等级", "公开、内部、秘密、机密四级。"),
        ("第四条 保存期限", "普通文档不少于3年，财务与合规文档不少于10年。"),
        ("第五条 违规处理", "未经授权外传机密文档，按公司纪律条例处理。"),
    ]:
        doc2.add_heading(title, level=2)
        doc2.add_paragraph(body)
    p2 = POLICIES / "演示企业文档管理制度.docx"
    doc2.save(p2)
    results.append(
        {
            "category": "policies",
            "title": "演示企业文档管理制度",
            "source": "project-generated",
            "url": "",
            "path": str(p2.relative_to(ROOT)),
            "bytes": p2.stat().st_size,
        }
    )
    return results


def write_manifest(items: list[dict]) -> None:
    lines = [
        "# Demo Data Sources",
        "",
        "本目录文件仅用于本地开发、演示与评测，不用于商业再分发。",
        "上市公司年报来自巨潮资讯网（证监会指定信息披露平台）公开披露文件。",
        "",
        "| 类别 | 标题/说明 | 本地路径 | 来源 | 大小 |",
        "|------|-----------|----------|------|------|",
    ]
    for it in items:
        kb = f"{it['bytes'] / 1024:.1f} KB"
        source = it.get("url") or it.get("source") or ""
        lines.append(
            f"| {it.get('category','')} | {it.get('title', it.get('name',''))} | `{it['path']}` | {source} | {kb} |"
        )
    lines.append("")
    MANIFEST.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {MANIFEST}")


def main() -> int:
    for d in (ANNUAL, POLICIES, MANUALS):
        d.mkdir(parents=True, exist_ok=True)

    sources: list[dict] = []
    sources.extend(download_annual_reports(sources))
    sources.extend(download_public_extras(sources))
    sources.extend(write_short_docx_samples())
    # Deduplicate by path
    uniq = {}
    for s in sources:
        uniq[s["path"]] = s
    items = list(uniq.values())
    write_manifest(items)

    print("\nSummary:")
    for it in items:
        print(f" - {it['path']} ({it['bytes'] // 1024} KB)")
    if not any(it["category"] == "annual_reports" for it in items):
        print("WARNING: no annual reports downloaded", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
