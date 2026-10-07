"""Shared types of the collection layer: site config, fetch results, discovered documents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from doc_agent.ingest.loaders import decode_html

if TYPE_CHECKING:
    from doc_agent.collect.http import PoliteClient

DocKind = Literal["article", "attachment", "catalog"]


@dataclass(frozen=True)
class ListSource:
    url: str
    desc: str = ""
    # "{n}" = 1-based page number, "{n0}" = 0-based; None → follow the "下一页" link.
    page_template: str | None = None


@dataclass(frozen=True)
class ArticlePattern:
    regex: str
    # Formatted with host / id / date; same key = same article (e.g. SCUT "a{id}" across columns).
    key: str = "{host}:{id}"


@dataclass(frozen=True)
class SiteConfig:
    school_id: str
    name: str
    short: str = ""
    adapter: str = "generic"
    domains: tuple[str, ...] = ()
    lists: tuple[ListSource, ...] = ()
    article_patterns: tuple[ArticlePattern, ...] = ()
    skip_url_patterns: tuple[str, ...] = ()
    blocked_hosts: tuple[str, ...] = ()
    catalog_systems: tuple[dict[str, Any], ...] = ()
    probe: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SiteConfig:
        return cls(
            school_id=d["school_id"],
            name=d.get("name", d["school_id"]),
            short=d.get("short", ""),
            adapter=d.get("adapter", "generic"),
            domains=tuple(d.get("domains") or ()),
            lists=tuple(ListSource(**x) for x in d.get("lists_override") or d.get("lists") or ()),
            article_patterns=tuple(ArticlePattern(**x) for x in d.get("article_patterns") or ()),
            skip_url_patterns=tuple(d.get("skip_url_patterns") or ()),
            blocked_hosts=tuple(d.get("blocked_hosts") or ()),
            catalog_systems=tuple(d.get("catalog_systems") or ()),
            probe=dict(d.get("probe") or {}),
        )


@dataclass
class FetchResult:
    url: str
    method: str = "GET"
    status: int | None = None
    final_url: str = ""
    content: bytes = field(default=b"", repr=False)
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    attempts: int = 0
    elapsed: float = 0.0
    not_modified: bool = False
    blocked: str = ""
    error: str = ""
    # robots / blocked_host / budget: the request was not sent
    skipped: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200 and not (self.blocked or self.error or self.skipped)

    @property
    def text(self) -> str:
        return decode_html(self.content) if self.content else ""

    def brief(self) -> dict[str, Any]:
        out: dict[str, Any] = {"url": self.url, "status": self.status}
        if self.final_url and self.final_url != self.url:
            out["final_url"] = self.final_url
        for key in ("blocked", "error", "skipped"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        if self.not_modified:
            out["not_modified"] = True
        return out


@dataclass
class DiscoveredDoc:
    school_id: str
    url: str
    key: str
    title: str
    publish_date: str | None = None
    kind: DocKind = "article"
    source: str = ""
    parent_url: str | None = None
    ext: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "")}


@dataclass
class ProbeResult:
    kind: str
    url: str
    status: Literal["new", "unchanged", "not_found", "blocked", "error", "skipped"]
    detail: str = ""
    found: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", {})}


@dataclass
class ProbeContext:
    """What a probe may consult: known documents and items discovered in this run."""

    latest_catalog_year: int | None
    known_urls: list[str]
    discovered: list[DiscoveredDoc]
    probe_ids: int = 3


class SiteAdapter(Protocol):
    site: SiteConfig

    @property
    def school_id(self) -> str: ...

    def page_url(self, source: ListSource, n: int) -> str | None: ...

    def next_page_url(self, html: str, url: str) -> str | None: ...

    def skip(self, url: str) -> bool: ...

    def parse_list(self, html: str, page_url: str) -> list[DiscoveredDoc]: ...

    def article_key(self, url: str) -> str: ...

    def article_title(self, html: str) -> str: ...

    def probes(self, client: PoliteClient, ctx: ProbeContext) -> list[ProbeResult]: ...
