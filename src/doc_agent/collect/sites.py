"""``collect/sites.json``: crawl config per school.

Names, domains, list pages, catalog systems and blocked hosts are generated from
``data/kaoyan/sources.json`` ``schools[]``; crawl rules (adapter, article URL patterns,
list page templates, ``lists_override`` when a site moved its columns, skip patterns, probe
settings) are maintained in sites.json and kept when regenerating. Adding a school = add it
to sources.json, regenerate, fill in its rules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from doc_agent.collect.base import SiteConfig
from doc_agent.collect.dedupe import host_of

SITES_PATH = Path(__file__).with_name("sites.json")
_RULE_KEYS = ("adapter", "lists_override", "article_patterns", "skip_url_patterns", "content_selector", "probe")


def build_sites(sources: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    prev = {s["school_id"]: s for s in (previous or {}).get("sites", [])}
    sites = []
    for school in sources.get("schools") or []:
        old = prev.get(school["id"], {})
        templates = {x["url"]: x.get("page_template") for x in old.get("lists", [])}
        lists = []
        for page in school.get("notice_list_pages") or []:
            entry = {"url": page["url"], "desc": page.get("desc", "")}
            if templates.get(page["url"]):
                entry["page_template"] = templates[page["url"]]
            lists.append(entry)
        catalog = []
        for system in school.get("catalog_systems") or []:
            item = {"url": system["url"], "year": system.get("year"), "desc": system.get("desc", "")}
            if system.get("status"):
                item["status"] = system["status"]
            catalog.append(item)
        blocked = sorted({host_of(c["url"]) for c in catalog if str(c.get("status", "")).startswith("blocked")})
        site = {
            "school_id": school["id"],
            "name": school["name"],
            "short": school.get("short", ""),
            "adapter": old.get("adapter", "generic"),
            "domains": list(school.get("official_domains") or []),
            "lists": lists,
            "lists_override": old.get("lists_override", []),
            "article_patterns": old.get("article_patterns", []),
            "skip_url_patterns": old.get("skip_url_patterns", []),
            "content_selector": old.get("content_selector", ""),
            "blocked_hosts": blocked,
            "catalog_systems": catalog,
            "probe": old.get("probe", {}),
        }
        sites.append({k: site[k] for k in site if k not in _RULE_KEYS or site[k] or k == "adapter"})
    return {
        "generated_from": "data/kaoyan/sources.json schools[]",
        "rules_note": "adapter / lists_override / article_patterns / lists[].page_template / skip_url_patterns / "
                      "content_selector / probe 为手工维护，重新生成时保留",
        "sites": sites,
    }


def load_sites(path: Path = SITES_PATH) -> dict[str, SiteConfig]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {s["school_id"]: SiteConfig.from_dict(s) for s in data["sites"]}


def write_sites(sources_path: Path, path: Path = SITES_PATH) -> dict[str, Any]:
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    data = build_sites(sources, previous)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data
