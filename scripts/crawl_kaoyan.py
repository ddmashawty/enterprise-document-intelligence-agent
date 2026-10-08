#!/usr/bin/env python3
"""Polite crawl of the official admission sites (collect/sites.json).

    python scripts/crawl_kaoyan.py --school jnu --mode probe            # dry run (default)
    python scripts/crawl_kaoyan.py --school jnu --mode probe --no-dry-run
    python scripts/crawl_kaoyan.py --sync-sites                         # regenerate sites.json
    python scripts/crawl_kaoyan.py --import FILE --school scut --title "…" [--url URL] [--doc-type catalog]

Same host: serial, >= CRAWL_MIN_INTERVAL_SEC (min 3 s) apart; robots.txt obeyed; at most
CRAWL_MAX_PAGES requests per school. Login redirects (yanzhao.scut.edu.cn) are reported as
blocked and never retried — download such files by hand and register them with --import.
Every run is recorded in kaoyan.db crawl_runs. Needs network; run scripts/seed_kaoyan.py first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_agent.collect.crawler import (
    MODES,
    Crawler,
    CrawlOptions,
    import_manual,
)
from doc_agent.collect.sites import load_sites, write_sites
from doc_agent.config import get_settings
from doc_agent.kaoyan.db import KaoyanStore
from doc_agent.kaoyan.normalize import resolve_school


def _summary(report: dict[str, Any]) -> list[str]:
    totals = json.dumps(report["totals"], ensure_ascii=False)
    lines = [f"run {report['run_id']} {report['status']} · {report['elapsed_sec']}s · {totals}"]
    for sid, rep in report["schools"].items():
        lines.append(f"[{sid}] requests={rep['requests']} discovered={rep['discovered']} new={len(rep['new'])} "
                     f"known={len(rep['known'])} registered={len(rep['registered'])} "
                     f"unchanged={len(rep['unchanged'])} changed={len(rep['changed'])} {rep['elapsed_sec']}s")
        for page in rep["list_pages"]:
            lines.append(f"  list {page['url']} -> {page.get('status')} items={page.get('items', 0)}"
                         + "".join(f" {k}={page[k]}" for k in ("blocked", "error", "skipped") if k in page))
        for probe in rep["probes"]:
            lines.append(f"  probe {probe['kind']} {probe['status']}: {probe.get('detail', '')} {probe['url']}")
        for alert in rep["alerts"]:
            lines.append(f"  ALERT {alert['kind']}: {alert.get('title') or alert.get('detail', '')}")
        for item in rep["new"][:10]:
            lines.append(f"  new {item.get('publish_date', '')} {item['title']}")
        if len(rep["new"]) > 10:
            lines.append(f"  … {len(rep['new']) - 10} more new")
        for item in rep["blocked"]:
            lines.append(f"  blocked {item.get('url')}: {item.get('blocked')}")
        for item in rep["errors"]:
            lines.append(f"  error {item.get('url')}: {item.get('error') or item.get('status')}")
    return lines


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=str(settings.kaoyan_db_path), help="SQLite path")
    parser.add_argument("--school", action="append", default=[], help="sysu/scut/jnu/scnu or 中大…; repeatable")
    parser.add_argument("--mode", choices=MODES, default="probe")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True,
                        help="only list pages and probes, write nothing to documents (default on)")
    parser.add_argument("--max-pages", type=int, help=f"requests per school (default {settings.crawl_max_pages})")
    parser.add_argument("--list-pages", type=int, help="list/full: pages per list (default 3)")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    parser.add_argument("--sync-sites", action="store_true", help="regenerate collect/sites.json from sources.json")
    parser.add_argument("--import", dest="import_file", type=Path, help="register a hand-downloaded file")
    parser.add_argument("--title", help="--import: document title")
    parser.add_argument("--url", help="--import: attachment / file URL")
    parser.add_argument("--page-url", help="--import: page the file was found on")
    parser.add_argument("--doc-type", help="--import: catalog / retest_rules / … (guessed from title if omitted)")
    parser.add_argument("--year", type=int, help="--import: intake year")
    args = parser.parse_args()

    if args.sync_sites:
        data = write_sites(settings.kaoyan_data_path / "sources.json")
        print(f"sites.json: {len(data['sites'])} schools")
        return 0

    store = KaoyanStore(settings.resolve(args.db))
    if store.count("schools") == 0:
        print("no schools in DB — run scripts/seed_kaoyan.py first", file=sys.stderr)
        return 1
    sites = load_sites()
    schools = []
    for text in args.school or list(sites):
        sid = resolve_school(text) or text
        if sid not in sites:
            print(f"unknown school {text!r}; configured: {', '.join(sites)}", file=sys.stderr)
            return 2
        schools.append(sid)

    if args.import_file:
        if len(schools) != 1 or not args.title:
            print("--import needs exactly one --school and --title", file=sys.stderr)
            return 2
        result = import_manual(store, args.import_file, school=schools[0], title=args.title, settings=settings,
                               url=args.url, page_url=args.page_url, doc_type=args.doc_type, year=args.year)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    opts = CrawlOptions(schools=schools, mode=args.mode, dry_run=args.dry_run,
                        max_pages=args.max_pages, list_pages=args.list_pages)
    report = Crawler(store, settings).run(opts)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("\n".join(_summary(report)))
    print(f"db: {store.db_path}{' (dry run)' if args.dry_run else ''}")
    return 0 if report["status"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
