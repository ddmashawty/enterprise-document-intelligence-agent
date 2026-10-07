"""Config-driven notice-list adapter.

Entries are recognized by the site's article URL patterns (``sites.json``), not by CSS
selectors: list templates differ per CMS, article URLs do not. The publish date comes from
the URL when it carries one (WebPlus ``/YYYY/MMDD/``, DedeCMS ``/a/YYYYMMDD/``), otherwise
from a date next to the link.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from doc_agent.collect.base import (
    DiscoveredDoc,
    ListSource,
    ProbeContext,
    ProbeResult,
    SiteConfig,
)
from doc_agent.collect.dedupe import host_of, normalize_url
from doc_agent.collect.http import PoliteClient
from doc_agent.ingest.redact import redact_text

# Used when a site has no article patterns configured yet.
DEFAULT_PATTERNS = (
    r"^https?://[^/]+/(?:[\w-]+/)*\d{4}/\d{4}/c\d+a(?P<id>\d+)/page\.(?:htm|psp)$",
    r"^https?://[^/]+/a/(?P<date>\d{8})/(?P<id>\d+)\.html$",
    r"^https?://[^/]+/(?:[\w-]+/)*article/(?P<id>\d+)$",
)
_URL_DATE = (
    re.compile(r"/(?P<y>20\d{2})/(?P<m>\d{2})(?P<d>\d{2})/"),
    re.compile(r"/a/(?P<y>20\d{2})(?P<m>\d{2})(?P<d>\d{2})/"),
)
_TEXT_DATE = re.compile(r"(?P<y>20\d{2})\s*[-./年]\s*(?P<m>\d{1,2})\s*[-./月]\s*(?P<d>\d{1,2})")
_NEXT_TEXT = {"下一页", "下页", "后页", ">", "›", "»", "next", "next ›", "下一页>", "下一页 >"}
_FILLER = re.compile(r"^\s*(?:\[\s*)?20\d{2}[-./]\d{1,2}[-./]\d{1,2}(?:\s*\])?\s*|\s*(?:\[\s*)?20\d{2}[-./]\d{1,2}[-./]\d{1,2}(?:\s*\])?\s*$")
_GENERIC_TITLES = {"更多", "more", "详细", "查看", "阅读全文", "详情", ">>", "more>>", "更多>>"}


def _ymd(m: re.Match[str]) -> str:
    return f"{int(m['y']):04d}-{int(m['m']):02d}-{int(m['d']):02d}"


def _clean_title(text: str) -> str:
    text = " ".join(text.split())
    return _FILLER.sub("", text).strip()


class GenericListAdapter:
    def __init__(self, site: SiteConfig) -> None:
        self.site = site
        raw = [p.regex for p in site.article_patterns] or list(DEFAULT_PATTERNS)
        keys = [p.key for p in site.article_patterns] or ["{host}:{id}"] * len(DEFAULT_PATTERNS)
        self._patterns = [(re.compile(r), k) for r, k in zip(raw, keys, strict=True)]
        self._skips = [re.compile(s) for s in site.skip_url_patterns]

    @property
    def school_id(self) -> str:
        return self.site.school_id

    # -- pagination ---------------------------------------------------------

    def page_url(self, source: ListSource, n: int) -> str | None:
        if n == 1:
            return source.url
        if source.page_template:
            return source.page_template.format(n=n, n0=n - 1)
        return None

    def next_page_url(self, html: str, url: str) -> str | None:
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True).lower()
            if text in _NEXT_TEXT or (a.get("title") or "").strip() in {"下一页", "Next page"}:
                href = str(a["href"]).strip()
                if href and not href.startswith(("javascript:", "#")):
                    nxt = urljoin(url, href)
                    return nxt if normalize_url(nxt) != normalize_url(url) else None
        return None

    def skip(self, url: str) -> bool:
        return any(p.search(url) for p in self._skips)

    # -- entries ------------------------------------------------------------

    def article_key(self, url: str) -> str:
        norm = normalize_url(url)
        for regex, key in self._patterns:
            m = regex.match(url) or regex.match(norm)
            if m:
                groups = {k: v for k, v in m.groupdict().items() if v is not None}
                return f"{self.school_id}:" + key.format(host=host_of(url), **groups)
        return norm

    def is_article(self, url: str) -> bool:
        norm = normalize_url(url)
        return any(regex.match(url) or regex.match(norm) for regex, _ in self._patterns)

    @staticmethod
    def _date(url: str, a: Tag) -> str | None:
        for rx in _URL_DATE:
            m = rx.search(url)
            if m:
                return _ymd(m)
        node: Tag | None = a
        for _ in range(3):
            node = node.parent if node is not None else None
            if node is None:
                break
            m = _TEXT_DATE.search(node.get_text(" ", strip=True))
            if m:
                return _ymd(m)
        return None

    @staticmethod
    def _title(a: Tag) -> tuple[str, int]:
        """Best title of an entry link and its quality: title attribute (2) > inner title element (1) >
        link text (0). WebPlus wraps date and summary in a second link, so plain text is the last resort."""
        attr = _clean_title(str(a.get("title") or ""))
        if attr and attr.lower() not in _GENERIC_TITLES:
            return attr, 2
        inner = a.find(class_=re.compile(r"(?:^|[-_])(?:title|tit)(?:$|[-_])"))
        if isinstance(inner, Tag):
            text = _clean_title(inner.get_text(" ", strip=True))
            if text:
                return text, 1
        text = _clean_title(a.get_text(" ", strip=True))
        return ("", 0) if text.lower() in _GENERIC_TITLES else (text, 0)

    def parse_list(self, html: str, page_url: str) -> list[DiscoveredDoc]:
        soup = BeautifulSoup(html, "lxml")
        found: dict[str, tuple[DiscoveredDoc, int]] = {}
        for a in soup.find_all("a", href=True):
            href = str(a["href"]).strip()
            if not href or href.startswith(("javascript:", "#", "mailto:")):
                continue
            url = urljoin(page_url, href)
            if not self.is_article(url) or self.skip(url):
                continue
            title, quality = self._title(a)
            if not title:
                continue
            key = self.article_key(url)
            doc = DiscoveredDoc(
                school_id=self.school_id,
                url=url,
                key=key,
                title=redact_text(title),
                publish_date=self._date(url, a),
                source=page_url,
            )
            prev = found.get(key)
            if prev is None or (quality, len(doc.title)) > (prev[1], len(prev[0].title)):
                if prev is not None and doc.publish_date is None:
                    doc.publish_date = prev[0].publish_date
                found[key] = (doc, quality)
        return [doc for doc, _ in found.values()]

    def article_title(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for sel in ("h1", ".arti_title", ".article-title", "h2"):
            node = soup.select_one(sel)
            if node and node.get_text(strip=True):
                return redact_text(_clean_title(node.get_text(" ", strip=True)))
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        return redact_text(_clean_title(title))

    # -- probes -------------------------------------------------------------

    def probes(self, client: PoliteClient, ctx: ProbeContext) -> list[ProbeResult]:
        return []
