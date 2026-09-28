"""Which kaoyan bundle files hold personal data (from sources.json)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


@lru_cache(maxsize=8)
def _personal_paths(sources_json: str, mtime: float) -> frozenset[Path]:
    path = Path(sources_json)
    meta = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(
        (path.parent / d["local_path"]).resolve()
        for d in meta.get("documents") or []
        if d.get("contains_personal_data") and d.get("local_path")
    )


def personal_data_paths(data_dir: Path) -> frozenset[Path]:
    sources = data_dir / "sources.json"
    if not sources.exists():
        return frozenset()
    return _personal_paths(str(sources.resolve()), sources.stat().st_mtime)


def is_personal_file(path: Path, data_dir: Path) -> bool:
    return path.resolve() in personal_data_paths(data_dir)
