#!/usr/bin/env python3
"""Check data/kaoyan/raw against raw/manifest.csv (sha256).

Missing local-only files (commit_to_git=false) only warn; missing committed files
or hash mismatches fail.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_agent.config import get_settings  # noqa: E402


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify(data_dir: Path) -> dict[str, list[str] | int]:
    with (data_dir / "raw" / "manifest.csv").open(encoding="utf-8-sig", newline="") as f:
        entries = list(csv.DictReader(f))
    ok = 0
    missing_local: list[str] = []
    missing_committed: list[str] = []
    mismatched: list[str] = []
    for e in entries:
        path = data_dir / e["local_path"]
        if not path.exists():
            (missing_committed if e["commit_to_git"] == "True" else missing_local).append(e["local_path"])
            continue
        if sha256_of(path) != e["sha256"]:
            mismatched.append(e["local_path"])
        else:
            ok += 1
    sources = json.loads((data_dir / "sources.json").read_text(encoding="utf-8"))
    doc_paths = {d["local_path"] for d in sources.get("documents") or []}
    manifest_paths = {e["local_path"] for e in entries}
    return {
        "entries": len(entries),
        "ok": ok,
        "missing_local_only": missing_local,
        "missing_committed": missing_committed,
        "sha256_mismatch": mismatched,
        "not_in_sources_json": sorted(manifest_paths - doc_paths),
        "not_in_manifest": sorted(doc_paths - manifest_paths),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(get_settings().kaoyan_data_path))
    args = parser.parse_args()
    result = verify(Path(args.data_dir))
    for path in result["missing_local_only"]:  # type: ignore[union-attr]
        print(f"WARN missing local-only file: {path}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    failed = any(result[k] for k in ("missing_committed", "sha256_mismatch", "not_in_sources_json", "not_in_manifest"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
