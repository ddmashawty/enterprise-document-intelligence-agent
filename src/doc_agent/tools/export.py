from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from doc_agent.config import get_settings


def _safe_stem(name: str) -> str:
    stem = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", name.strip())[:60]
    return stem or "export"


def _export_path(filename: str, suffix: str) -> Path:
    settings = get_settings()
    settings.export_path.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if filename.strip():
        stem = _safe_stem(Path(filename).stem)
    else:
        stem = "report"
    path = settings.export_path / f"{ts}_{stem}{suffix}"
    return path


@tool
def export_markdown(title: str, content: str, filename: str = "") -> str:
    """Export a Markdown report to data/exports/. Returns JSON with path and title."""
    path = _export_path(filename or title, ".md")
    body = content if content.lstrip().startswith("#") else f"# {title}\n\n{content}"
    path.write_text(body.strip() + "\n", encoding="utf-8")
    payload = {
        "format": "markdown",
        "title": title,
        "path": str(path.relative_to(get_settings().root)),
        "bytes": path.stat().st_size,
    }
    return json.dumps(payload, ensure_ascii=False)


@tool
def export_excel(title: str, rows_json: str, filename: str = "") -> str:
    """Export tabular data to Excel (.xlsx). rows_json must be a JSON list of objects or list-of-lists."""
    try:
        rows = json.loads(rows_json)
    except json.JSONDecodeError:
        return "rows_json 不是合法 JSON"
    if not isinstance(rows, list) or not rows:
        return "rows_json 需要非空数组"

    try:
        from openpyxl import Workbook
    except ImportError:
        return "缺少 openpyxl，请 pip install openpyxl"

    wb = Workbook()
    ws = wb.active
    ws.title = (title or "Sheet1")[:31]

    if isinstance(rows[0], dict):
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            if not isinstance(row, dict):
                continue
            ws.append([_cell(row.get(h)) for h in headers])
    elif isinstance(rows[0], (list, tuple)):
        for row in rows:
            ws.append([_cell(v) for v in row])
    else:
        return "rows_json 元素须为对象或数组"

    path = _export_path(filename or title, ".xlsx")
    wb.save(path)
    payload = {
        "format": "excel",
        "title": title,
        "path": str(path.relative_to(get_settings().root)),
        "rows": len(rows),
        "bytes": path.stat().st_size,
    }
    return json.dumps(payload, ensure_ascii=False)


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False)
