from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from doc_agent.tools import export as export_mod


def test_export_markdown_and_excel(tmp_path: Path, monkeypatch):
    fake = SimpleNamespace(root=tmp_path, export_path=tmp_path)
    monkeypatch.setattr(export_mod, "get_settings", lambda: fake)

    md = json.loads(
        export_mod.export_markdown.invoke(
            {"title": "t", "content": "hello", "filename": "unit_md"}
        )
    )
    assert md["format"] == "markdown"
    assert (tmp_path / Path(md["path"]).name).exists()

    xlsx = json.loads(
        export_mod.export_excel.invoke(
            {
                "title": "t",
                "rows_json": json.dumps([{"a": 1, "b": 2}]),
                "filename": "unit_xlsx",
            }
        )
    )
    assert xlsx["format"] == "excel"
    assert xlsx["rows"] == 1
    assert (tmp_path / Path(xlsx["path"]).name).exists()
