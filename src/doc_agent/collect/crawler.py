"""Crawl runs: list pages → probes → compare with ``documents`` → (unless dry_run) fetch,
register new documents, detect changes by sha256.

- ``probe``: first list page of each source + site probes;
- ``list``: up to ``list_pages`` list pages per source + probes;
- ``full``: like ``list``, and also downloads attachments of fetched articles (and SCNU catalog pages).

``dry_run`` (default) only fetches list pages and probe URLs: nothing is downloaded or written
to ``documents``. Every run is recorded in ``crawl_runs``. Downloads go to the cache dir
(ignored by git). Titles are redacted before they are stored or reported.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from doc_agent.collect.adapters import build_adapter
from doc_agent.collect.adapters.scnu import ScnuAdapter
from doc_agent.collect.attachments import discover_attachments
from doc_agent.collect.base import DiscoveredDoc, FetchResult, ProbeContext
from doc_agent.collect.dedupe import (
    normalize_url,
    safe_filename,
    sha256_bytes,
    short_hash,
    text_fingerprint,
)
from doc_agent.collect.generic_list import GenericListAdapter
from doc_agent.collect.http import PoliteClient
from doc_agent.collect.sites import load_sites
from doc_agent.config import Settings, get_settings
from doc_agent.ingest.redact import redact_text
from doc_agent.kaoyan.db import KaoyanStore
from doc_agent.kaoyan.models import Document

logger = logging.getLogger(__name__)

MODES = ("probe", "list", "full")
DEFAULT_LIST_PAGES = 3

_DOC_TYPE_RULES: tuple[tuple[str, str], ...] = (
    (r"推免.*(?:名单|名册)|接收推免", "tm_admit_list"),
    (r"拟录取|录取名单|录取结果", "admission_list"),
    (r"复试名单|入围|复试结果|复试成绩", "retest_list"),
    (r"推免.*目录", "tm_catalog"),
    (r"专业目录", "catalog"),
    (r"简章|章程", "brochure"),
    (r"分数线|基本要求|成绩要求", "score_line"),
    (r"复试", "retest_rules"),
    (r"推免|推荐免试", "tm_policy"),
    (r"初试科目|科目调整", "subject_change"),
    (r"计划", "plan_quota"),
    (r"学费|奖助", "fees"),
)
_PERSONAL_TITLE = re.compile(r"名单|名册|复试结果|录取结果|成绩公示|拟录取.{0,12}公示|公示.{0,12}拟录取")
_TITLE_YEAR = re.compile(r"(20\d{2})\s*(?:年|级)")
_NEW_YEAR_TITLE = re.compile(r"(20\d{2})\s*年?.{0,20}?(招生简章|招生章程|专业目录)")
_FORMATS = {".html": "html", ".htm": "html", ".pdf": "pdf", ".xlsx": "xlsx", ".xls": "xls",
            ".doc": "doc", ".docx": "docx", ".jpg": "img", ".jpeg": "img", ".png": "img", ".gif": "img"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def guess_doc_type(title: str) -> str:
    for pattern, doc_type in _DOC_TYPE_RULES:
        if re.search(pattern, title):
            return doc_type
    return "notice"


def guess_intake_year(title: str, publish_date: str | None) -> int | None:
    m = _TITLE_YEAR.search(title)
    if m:
        return int(m.group(1))
    if publish_date and len(publish_date) >= 7:
        year, month = int(publish_date[:4]), int(publish_date[5:7])
        return year + 1 if month >= 9 else year
    return None


def looks_personal(title: str) -> bool:
    return bool(_PERSONAL_TITLE.search(title))


def doc_format(name: str) -> str:
    return _FORMATS.get(Path(name).suffix.lower(), "file")


@dataclass
class CrawlOptions:
    schools: list[str]
    mode: str = "probe"
    dry_run: bool = True
    max_pages: int | None = None
    list_pages: int | None = None

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {self.mode!r}")


# -- crawl_runs ---------------------------------------------------------------


def create_run(store: KaoyanStore, opts: CrawlOptions) -> str:
    run_id = f"crawl_{uuid4().hex[:12]}"
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO crawl_runs (id, started_at, school_ids, mode, status, stats_json) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, now_iso(), ",".join(opts.schools), opts.mode, "queued",
             json.dumps({"params": asdict(opts)}, ensure_ascii=False)),
        )
    return run_id


def update_run(store: KaoyanStore, run_id: str, **fields: Any) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    with store.transaction() as conn:
        conn.execute(f"UPDATE crawl_runs SET {sets} WHERE id = ?", [*fields.values(), run_id])


def get_run(store: KaoyanStore, run_id: str) -> dict[str, Any] | None:
    row = store.query_one("SELECT * FROM crawl_runs WHERE id = ?", (run_id,))
    if row is None:
        return None
    stats = json.loads(row.pop("stats_json") or "{}")
    params = stats.get("params") or {}
    row["run_id"] = row.pop("id")
    row["school_ids"] = [s for s in (row.get("school_ids") or "").split(",") if s]
    row["dry_run"] = params.get("dry_run")
    row["max_pages"] = params.get("max_pages")
    row["stats"] = stats
    return row


# -- known documents ----------------------------------------------------------


class KnownDocs:
    def __init__(self, docs: list[dict[str, Any]], adapter: GenericListAdapter) -> None:
        self.adapter = adapter
        self.by_key: dict[str, list[dict[str, Any]]] = {}
        self.by_attachment: dict[str, dict[str, Any]] = {}
        self.by_sha: dict[str, dict[str, Any]] = {}
        self.parents: set[str] = set()
        self.docs: list[dict[str, Any]] = []
        for d in docs:
            self.add(d)

    def add(self, d: dict[str, Any]) -> None:
        self.docs.append(d)
        if d.get("page_url"):
            self.by_key.setdefault(self.adapter.article_key(d["page_url"]), []).append(d)
        if d.get("attachment_url"):
            self.by_attachment.setdefault(normalize_url(d["attachment_url"]), d)
        if d.get("sha256"):
            self.by_sha.setdefault(d["sha256"], d)
        if d.get("parent_doc_id"):
            self.parents.add(d["parent_doc_id"])

    def article_docs(self, key: str) -> list[dict[str, Any]]:
        return self.by_key.get(key, [])

    def page_doc(self, key: str) -> dict[str, Any] | None:
        """The document for the article page itself (latest version), if registered."""
        pages = [d for d in self.article_docs(key) if not d.get("attachment_url")
                 and str(d.get("format") or "").startswith("html")]
        latest = [d for d in pages if d["id"] not in self.parents]
        return (latest or pages or [None])[-1]

    def latest_year(self, *doc_types: str) -> int | None:
        years = [d["intake_year"] for d in self.docs if d.get("doc_type") in doc_types and d.get("intake_year")]
        return max(years) if years else None

    @property
    def page_urls(self) -> list[str]:
        return [d["page_url"] for d in self.docs if d.get("page_url")]


# -- crawler ------------------------------------------------------------------


@dataclass
class SchoolReport:
    school: str
    list_pages: list[dict[str, Any]] = field(default_factory=list)
    discovered: int = 0
    new: list[dict[str, Any]] = field(default_factory=list)
    known: list[dict[str, Any]] = field(default_factory=list)
    probes: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    registered: list[dict[str, Any]] = field(default_factory=list)
    unchanged: list[dict[str, Any]] = field(default_factory=list)
    changed: list[dict[str, Any]] = field(default_factory=list)
    removed: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    catalog_pages: list[dict[str, Any]] = field(default_factory=list)
    blocked: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    requests: int = 0
    budget_exhausted: bool = False
    elapsed_sec: float = 0.0

    def failure(self, res: FetchResult, context: str) -> None:
        item = {**res.brief(), "context": context}
        if res.blocked:
            self.blocked.append(item)
        elif res.skipped == "budget":
            self.budget_exhausted = True
        else:
            self.errors.append(item)


_COUNTED = ("new", "known", "registered", "unchanged", "changed", "removed", "attachments",
            "alerts", "blocked", "errors")


class Crawler:
    def __init__(
        self,
        store: KaoyanStore,
        settings: Settings | None = None,
        *,
        client_factory: Callable[[], PoliteClient] | None = None,
        sites_path: Path | None = None,
    ) -> None:
        self.store = store
        self.settings = settings or get_settings()
        self.sites = load_sites(sites_path) if sites_path else load_sites()
        self.client_factory = client_factory or (lambda: PoliteClient.from_settings(self.settings))
        self.cache_dir = self.settings.crawl_cache_path
        self.data_dir = self.settings.kaoyan_data_path
        self.run_id = ""

    def run(self, opts: CrawlOptions, run_id: str | None = None) -> dict[str, Any]:
        unknown = [s for s in opts.schools if s not in self.sites]
        if unknown:
            raise ValueError(f"no crawl config for {unknown}; known: {sorted(self.sites)}")
        self.run_id = run_id or create_run(self.store, opts)
        update_run(self.store, self.run_id, status="running")
        start = time.monotonic()
        report: dict[str, Any] = {"run_id": self.run_id, "params": asdict(opts), "schools": {}}
        status, error = "done", None
        try:
            with self.client_factory() as client:
                for school_id in opts.schools:
                    client.reset_budget(opts.max_pages or self.settings.crawl_max_pages)
                    rep = self.crawl_school(client, build_adapter(self.sites[school_id]), opts)
                    report["schools"][school_id] = asdict(rep)
        except Exception as exc:
            logger.exception("crawl run %s failed", self.run_id)
            status, error = "error", f"{type(exc).__name__}: {exc}"
        report["totals"] = {
            key: sum(len(r[key]) for r in report["schools"].values()) for key in _COUNTED
        } | {
            "discovered": sum(r["discovered"] for r in report["schools"].values()),
            "requests": sum(r["requests"] for r in report["schools"].values()),
        }
        report["elapsed_sec"] = round(time.monotonic() - start, 1)
        update_run(self.store, self.run_id, status=status, finished_at=now_iso(), error=error,
                   stats_json=json.dumps(report, ensure_ascii=False))
        report["status"] = status
        if error:
            report["error"] = error
        return report

    # -- per school -----------------------------------------------------------

    def crawl_school(self, client: PoliteClient, adapter: GenericListAdapter, opts: CrawlOptions) -> SchoolReport:
        start = time.monotonic()
        school_id = adapter.school_id
        rep = SchoolReport(school=school_id)
        known = KnownDocs(self.store.query("SELECT * FROM documents WHERE school_id = ? ORDER BY id", (school_id,)),
                          adapter)
        discovered = self._list(client, adapter, opts, rep)
        rep.discovered = len(discovered)

        ctx = ProbeContext(
            latest_catalog_year=known.latest_year("catalog"),
            known_urls=known.page_urls,
            discovered=list(discovered.values()),
            probe_ids=self.settings.crawl_probe_ids,
        )
        for probe in adapter.probes(client, ctx):
            item = probe.to_dict()
            rep.probes.append(item)
            if probe.status == "new":
                rep.alerts.append({"kind": probe.kind, **item})
            elif probe.status == "blocked":
                rep.blocked.append({"url": probe.url, "blocked": probe.detail, "context": probe.kind})

        fresh: list[DiscoveredDoc] = []
        seen: list[tuple[DiscoveredDoc, list[dict[str, Any]]]] = []
        for d in discovered.values():
            docs = known.article_docs(d.key)
            if docs:
                seen.append((d, docs))
                rep.known.append({"key": d.key, "title": d.title, "doc_ids": [x["id"] for x in docs]})
            else:
                fresh.append(d)
                rep.new.append({**d.to_dict(), "doc_type": guess_doc_type(d.title),
                                "intake_year": guess_intake_year(d.title, d.publish_date),
                                "contains_personal_data": looks_personal(d.title)})
        rep.alerts.extend(self._title_alerts(fresh, known))

        if not opts.dry_run:
            for d in fresh:
                self._register_article(client, adapter, d, known, opts, rep)
            for d, _docs in seen:
                self._recheck(client, d, known, rep)
            if opts.mode == "full" and isinstance(adapter, ScnuAdapter):
                self._scnu_catalog(client, adapter, known, rep)
        rep.requests = client.pages
        rep.budget_exhausted = rep.budget_exhausted or client.budget_left == 0
        rep.elapsed_sec = round(time.monotonic() - start, 1)
        return rep

    def _list(
        self, client: PoliteClient, adapter: GenericListAdapter, opts: CrawlOptions, rep: SchoolReport
    ) -> dict[str, DiscoveredDoc]:
        depth = 1 if opts.mode == "probe" else max(opts.list_pages or DEFAULT_LIST_PAGES, 1)
        found: dict[str, DiscoveredDoc] = {}
        for source in adapter.site.lists:
            html, prev = "", ""
            for n in range(1, depth + 1):
                url = adapter.page_url(source, n) if n == 1 else (
                    adapter.page_url(source, n) or adapter.next_page_url(html, prev))
                if not url or adapter.skip(url):
                    break
                res = client.get(url)
                entry = res.brief()
                if not res.ok:
                    rep.list_pages.append(entry)
                    rep.failure(res, "list")
                    break
                items = adapter.parse_list(res.text, res.final_url or url)
                entry["items"] = len(items)
                rep.list_pages.append(entry)
                for d in items:
                    prev_doc = found.get(d.key)
                    if prev_doc is None or len(d.title) > len(prev_doc.title):
                        found[d.key] = d
                if not items:
                    break
                html, prev = res.text, res.final_url or url
        return found

    @staticmethod
    def _title_alerts(fresh: list[DiscoveredDoc], known: KnownDocs) -> list[dict[str, Any]]:
        alerts = []
        for d in fresh:
            m = _NEW_YEAR_TITLE.search(d.title)
            if not m or "推免" in d.title:
                continue
            year, word = int(m.group(1)), m.group(2)
            doc_type = "catalog" if word == "专业目录" else "brochure"
            latest = known.latest_year(doc_type)
            if latest is None or year > latest:
                alerts.append({"kind": f"new_{doc_type}", "title": d.title, "url": d.url, "year": year,
                               "latest_known": latest})
        return alerts

    # -- storage --------------------------------------------------------------

    def _save(self, school_id: str, name: str, data: bytes, sha: str) -> str:
        folder = self.cache_dir / school_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{sha[:12]}_{safe_filename(name)}"
        if not path.exists():
            path.write_bytes(data)
        try:
            return str(path.relative_to(self.data_dir))
        except ValueError:
            return str(path)

    def _local_file(self, local_path: str | None) -> Path | None:
        if not local_path:
            return None
        p = Path(local_path)
        p = p if p.is_absolute() else self.data_dir / p
        return p if p.exists() else None

    def _upsert(self, doc: Document) -> None:
        with self.store.transaction() as conn:
            self.store.upsert(conn, "documents", doc)

    def _touch(self, doc_id: str, status: str = "active") -> None:
        with self.store.transaction() as conn:
            conn.execute("UPDATE documents SET last_seen = ?, status = ? WHERE id = ?", (now_iso(), status, doc_id))

    # -- non-dry-run steps ----------------------------------------------------

    def _register_article(
        self,
        client: PoliteClient,
        adapter: GenericListAdapter,
        d: DiscoveredDoc,
        known: KnownDocs,
        opts: CrawlOptions,
        rep: SchoolReport,
    ) -> None:
        res = client.get(d.url)
        if not res.ok:
            rep.failure(res, "article")
            return
        sha = sha256_bytes(res.content)
        title = d.title
        if not title or title.endswith(("...", "…")):
            title = adapter.article_title(res.text) or title
        dup = known.by_sha.get(sha)
        if dup is not None:
            rep.unchanged.append({"url": d.url, "doc_id": dup["id"], "by": "sha256", "note": "内容与已有文档相同"})
            return
        stamp = now_iso()
        doc = Document(
            id=f"{adapter.school_id}-w{short_hash(d.key)}",
            school_id=adapter.school_id,
            title=title,
            publish_date=d.publish_date,
            intake_year=guess_intake_year(title, d.publish_date),
            doc_type=guess_doc_type(title),
            format="html",
            page_url=d.url,
            article_id=d.key.split(":", 1)[-1],
            local_path=self._save(adapter.school_id, f"{title}.html", res.content, sha),
            sha256=sha,
            bytes=len(res.content),
            contains_personal_data=looks_personal(title),
            first_seen=stamp,
            last_seen=stamp,
            notes=f"采集登记 {self.run_id}",
        )
        self._upsert(doc)
        known.add(doc.model_dump())
        rep.registered.append({"doc_id": doc.id, "title": title, "url": d.url, "doc_type": doc.doc_type})
        if opts.mode == "full":
            self._attachments(client, adapter, res, doc, known, rep)

    def _recheck(self, client: PoliteClient, d: DiscoveredDoc, known: KnownDocs, rep: SchoolReport) -> None:
        page = known.page_doc(d.key)
        if page is None:
            for doc in known.article_docs(d.key):
                self._touch(doc["id"])
            rep.unchanged.append({"url": d.url, "doc_ids": [x["id"] for x in known.article_docs(d.key)],
                                  "by": "listed", "note": "只登记了附件，未比对正文"})
            return
        res = client.get(d.url, conditional=True)
        if res.not_modified:
            self._touch(page["id"])
            rep.unchanged.append({"url": d.url, "doc_id": page["id"], "by": "304"})
        elif res.ok:
            sha = sha256_bytes(res.content)
            local = self._local_file(page.get("local_path"))
            if sha == page.get("sha256"):
                self._touch(page["id"])
                rep.unchanged.append({"url": d.url, "doc_id": page["id"], "by": "sha256"})
            elif local is not None and text_fingerprint(local.read_bytes()) == text_fingerprint(res.content):
                self._touch(page["id"])
                rep.unchanged.append({"url": d.url, "doc_id": page["id"], "by": "text",
                                      "note": "字节不同（计数器等），正文相同"})
            else:
                self._new_version(page, res, sha, known, rep)
        elif res.status in (404, 410):
            self._touch(page["id"], status="removed")
            rep.removed.append({"url": d.url, "doc_id": page["id"], "status": res.status})
        else:
            if res.blocked:
                self._touch(page["id"], status="blocked")
            rep.failure(res, "recheck")

    def _new_version(
        self, page: dict[str, Any], res: FetchResult, sha: str, known: KnownDocs, rep: SchoolReport
    ) -> None:
        existing = {d["id"] for d in known.docs}
        n = 2
        while f"{page['id']}-v{n}" in existing:
            n += 1
        stamp = now_iso()
        fields = {k: v for k, v in page.items() if k in Document.model_fields}
        doc = Document(**{
            **fields,
            "id": f"{page['id']}-v{n}",
            "local_path": self._save(page["school_id"], f"{page['title']}.html", res.content, sha),
            "sha256": sha,
            "bytes": len(res.content),
            "status": "active",
            "first_seen": stamp,
            "last_seen": stamp,
            "parent_doc_id": page["id"],
            "notes": f"内容变化，新版本（{self.run_id}）",
        })
        self._upsert(doc)
        known.add(doc.model_dump())
        rep.changed.append({"url": page.get("page_url"), "doc_id": doc.id, "parent_doc_id": page["id"]})

    def _attachments(
        self,
        client: PoliteClient,
        adapter: GenericListAdapter,
        res: FetchResult,
        article: Document,
        known: KnownDocs,
        rep: SchoolReport,
    ) -> None:
        for att in discover_attachments(res.text, res.final_url or res.url):
            name = redact_text(att.name)
            if att.kind == "data_uri":
                hit = known.by_sha.get(att.sha256)
                rep.attachments.append({"name": name, "inline": True, "sha256": att.sha256,
                                        "status": "known" if hit else "inline_only",
                                        **({"doc_id": hit["id"]} if hit else {})})
                continue
            hit = known.by_attachment.get(normalize_url(att.url))
            if hit is not None:
                rep.attachments.append({"name": name, "url": att.url, "status": "known", "doc_id": hit["id"]})
                continue
            got = client.get(att.url)
            if not got.ok:
                rep.failure(got, "attachment")
                continue
            sha = sha256_bytes(got.content)
            dup = known.by_sha.get(sha)
            if dup is not None:
                rep.attachments.append({"name": name, "url": att.url, "status": "duplicate", "doc_id": dup["id"]})
                continue
            stamp = now_iso()
            doc = Document(
                id=f"{adapter.school_id}-w{short_hash(normalize_url(att.url))}",
                school_id=adapter.school_id,
                title=name,
                publish_date=article.publish_date,
                intake_year=article.intake_year,
                doc_type=guess_doc_type(name) if guess_doc_type(name) != "notice" else article.doc_type,
                format=doc_format(name) if doc_format(name) != "file" else doc_format(att.url),
                page_url=article.page_url,
                attachment_url=att.url,
                local_path=self._save(adapter.school_id, name, got.content, sha),
                sha256=sha,
                bytes=len(got.content),
                contains_personal_data=article.contains_personal_data or looks_personal(name),
                first_seen=stamp,
                last_seen=stamp,
                notes=f"采集登记（附件）{self.run_id}",
            )
            self._upsert(doc)
            known.add(doc.model_dump())
            rep.attachments.append({"name": name, "url": att.url, "status": "registered", "doc_id": doc.id})

    def _scnu_catalog(self, client: PoliteClient, adapter: ScnuAdapter, known: KnownDocs, rep: SchoolReport) -> None:
        for college in adapter.site.probe.get("catalog_colleges") or []:
            for i, res in enumerate(adapter.fetch_catalog(client, college), start=1):
                if not res.ok:
                    rep.failure(res, f"catalog {college}")
                    break
                sha = sha256_bytes(res.content)
                path = self._save(adapter.school_id, f"scnu_zsml_{college}_p{i}.html", res.content, sha)
                rep.catalog_pages.append({"college": college, "page": i, "sha256": sha, "local_path": path,
                                          "known": sha in known.by_sha})


# -- manual import ------------------------------------------------------------


def import_manual(
    store: KaoyanStore,
    path: Path,
    *,
    school: str,
    title: str,
    settings: Settings | None = None,
    url: str | None = None,
    page_url: str | None = None,
    doc_type: str | None = None,
    year: int | None = None,
    publish_date: str | None = None,
    personal: bool | None = None,
) -> dict[str, Any]:
    """Register a file downloaded by hand (e.g. from yanzhao.scut.edu.cn behind the login)."""
    s = settings or get_settings()
    if store.query_one("SELECT id FROM schools WHERE id = ?", (school,)) is None:
        raise ValueError(f"unknown school {school!r}; run scripts/seed_kaoyan.py first")
    data = path.read_bytes()
    sha = sha256_bytes(data)
    dup = store.query_one("SELECT id FROM documents WHERE sha256 = ?", (sha,))
    if dup:
        return {"status": "duplicate", "doc_id": dup["id"], "sha256": sha}
    folder = s.crawl_cache_path / school / "manual"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{sha[:12]}_{safe_filename(path.name)}"
    if not dest.exists():
        shutil.copyfile(path, dest)
    try:
        local = str(dest.relative_to(s.kaoyan_data_path))
    except ValueError:
        local = str(dest)
    title = redact_text(title)
    stamp = now_iso()
    doc = Document(
        id=f"{school}-m{sha[:8]}",
        school_id=school,
        title=title,
        publish_date=publish_date,
        intake_year=year or guess_intake_year(title, publish_date),
        doc_type=doc_type or guess_doc_type(title),
        format=doc_format(path.name),
        page_url=page_url,
        attachment_url=url,
        local_path=local,
        sha256=sha,
        bytes=len(data),
        contains_personal_data=looks_personal(title) if personal is None else personal,
        first_seen=stamp,
        last_seen=stamp,
        notes=f"手动导入 {stamp[:10]}",
    )
    with store.transaction() as conn:
        store.upsert(conn, "documents", doc)
    return {"status": "registered", "doc_id": doc.id, "sha256": sha, "local_path": local}
