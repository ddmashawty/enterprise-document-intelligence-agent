"""Polite HTTP client for official admission sites.

- one request at a time per host, at least ``min_interval`` seconds apart (shared across clients);
- robots.txt is read once per host and obeyed (RFC 9309: any 4xx incl. 401/403 → allow all,
  5xx / network error → disallow all);
- timeouts and 5xx are retried at most ``max_retries`` times with exponential backoff; 4xx never;
- redirects are followed by hand; a redirect to a login / CAS page marks the host ``blocked``
  and later requests to it are skipped (never retried, never worked around);
- conditional GET (ETag / Last-Modified) on request; validators persist in the cache dir;
- a per-run page budget (``max_pages``); robots.txt does not count.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Self
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from doc_agent.collect.base import FetchResult
from doc_agent.collect.dedupe import host_of

logger = logging.getLogger(__name__)

_LOGIN_PATH = re.compile(r"login|/cas/|authserver|/sso/|rump_frontend|passport|统一身份认证", re.IGNORECASE)
_MAX_REDIRECTS = 5


class HostThrottle:
    """Serializes requests per host and keeps them ``min_interval`` seconds apart."""

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self.clock = clock
        self.sleep = sleep
        self._last: dict[str, float] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, host: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(host, threading.Lock())

    @contextmanager
    def slot(self, host: str) -> Iterator[None]:
        with self._lock(host):
            last = self._last.get(host)
            if last is not None:
                wait = last + self.min_interval - self.clock()
                if wait > 0:
                    self.sleep(wait)
            try:
                yield
            finally:
                self._last[host] = self.clock()


_SHARED: dict[float, HostThrottle] = {}
_SHARED_GUARD = threading.Lock()


def shared_throttle(min_interval: float) -> HostThrottle:
    """Process-wide throttle, so concurrent crawl runs still hit each host serially."""
    with _SHARED_GUARD:
        return _SHARED.setdefault(min_interval, HostThrottle(min_interval))


class ValidatorCache:
    """ETag / Last-Modified per URL, persisted as JSON when a path is given."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._data: dict[str, dict[str, str]] = {}
        if path and path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._data = {}

    def headers(self, url: str) -> dict[str, str]:
        v = self._data.get(url) or {}
        out = {}
        if v.get("etag"):
            out["If-None-Match"] = v["etag"]
        if v.get("last_modified"):
            out["If-Modified-Since"] = v["last_modified"]
        return out

    def update(self, url: str, headers: httpx.Headers) -> None:
        etag, lm = headers.get("etag"), headers.get("last-modified")
        if etag or lm:
            self._data[url] = {k: v for k, v in (("etag", etag), ("last_modified", lm)) if v}

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8")


class PoliteClient:
    def __init__(
        self,
        *,
        user_agent: str,
        min_interval: float = 3.0,
        timeout: float = 20.0,
        max_retries: int = 2,
        backoff: float = 2.0,
        respect_robots: bool = True,
        max_pages: int | None = None,
        transport: httpx.BaseTransport | None = None,
        throttle: HostThrottle | None = None,
        validators: ValidatorCache | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.robots_agent = user_agent.split("/")[0].split()[0]
        self.max_retries = max_retries
        self.backoff = backoff
        self.respect_robots = respect_robots
        self.max_pages = max_pages
        self.pages = 0
        self.throttle = throttle or shared_throttle(min_interval)
        self.validators = validators or ValidatorCache()
        # Hosts that sent us to a login page in this run → host: reason.
        self.blocked: dict[str, str] = {}
        self.robots: dict[str, RobotFileParser | None] = {}
        self.log: list[dict[str, Any]] = []
        self._http = httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": user_agent, "Accept-Language": "zh-CN,zh;q=0.9"},
        )

    @classmethod
    def from_settings(cls, settings: Any, **kw: Any) -> PoliteClient:
        cache = settings.crawl_cache_path / "http_validators.json"
        params: dict[str, Any] = {
            "user_agent": settings.crawl_user_agent_full,
            "min_interval": max(settings.crawl_min_interval_sec, 3.0),
            "timeout": settings.crawl_timeout,
            "max_retries": settings.crawl_max_retries,
            "backoff": settings.crawl_backoff_sec,
            "respect_robots": settings.crawl_respect_robots,
            "max_pages": settings.crawl_max_pages,
            "validators": ValidatorCache(cache),
        }
        params.update(kw)
        return cls(**params)

    def close(self) -> None:
        self.validators.save()
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- budget -------------------------------------------------------------

    def reset_budget(self, max_pages: int | None) -> None:
        self.max_pages = max_pages
        self.pages = 0

    @property
    def budget_left(self) -> int | None:
        return None if self.max_pages is None else max(self.max_pages - self.pages, 0)

    # -- robots -------------------------------------------------------------

    def _robots_for(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self.robots:
            return self.robots[origin]
        robots_url = origin + "/robots.txt"
        parser = RobotFileParser(robots_url)
        res = self._send("GET", robots_url, retries=1)
        if res.status == 200:
            parser.parse(res.text.splitlines())
        elif res.status is not None and 400 <= res.status < 500:
            # Includes 401/403: several sites' WAF answers 403 for robots.txt only.
            parser.allow_all = True
        else:
            # 5xx / network error / login redirect: assume everything is disallowed (RFC 9309).
            parser.disallow_all = True
        self.robots[origin] = parser
        return parser

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parser = self._robots_for(url)
        return parser is None or parser.can_fetch(self.robots_agent, url)

    # -- requests -----------------------------------------------------------

    def get(self, url: str, *, conditional: bool = False) -> FetchResult:
        return self.request("GET", url, conditional=conditional)

    def post(self, url: str, data: dict[str, str]) -> FetchResult:
        return self.request("POST", url, data=data)

    def request(
        self, method: str, url: str, *, data: dict[str, str] | None = None, conditional: bool = False
    ) -> FetchResult:
        host = host_of(url)
        if self.budget_left == 0:
            return FetchResult(url=url, method=method, skipped="budget")
        allowed = host in self.blocked or self.allowed(url)
        if host in self.blocked:
            return FetchResult(url=url, method=method, skipped="blocked_host", blocked=self.blocked[host])
        if not allowed:
            self._record(method, url, None, "robots")
            return FetchResult(url=url, method=method, skipped="robots")
        self.pages += 1
        headers = self.validators.headers(url) if conditional and method == "GET" else {}
        res = self._send(method, url, data=data, headers=headers, retries=self.max_retries)
        if conditional and res.status == 200:
            self.validators.update(url, httpx.Headers(res.headers))
        return res

    def _send(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        retries: int = 0,
    ) -> FetchResult:
        result = FetchResult(url=url, method=method)
        start = time.monotonic()
        current, current_method, current_data = url, method, data
        for _hop in range(_MAX_REDIRECTS + 1):
            resp, error, attempts = self._attempt(current_method, current, current_data, headers, retries)
            result.attempts += attempts
            if resp is None:
                result.error = error
                break
            result.status = resp.status_code
            result.final_url = current
            result.headers = dict(resp.headers)
            if resp.is_redirect and resp.headers.get("location"):
                target = urljoin(current, resp.headers["location"])
                if _LOGIN_PATH.search(urlsplit(target).path + "?" + urlsplit(target).query):
                    reason = f"{resp.status_code} → {target}"
                    result.blocked = reason
                    result.final_url = target
                    self.blocked[host_of(url)] = reason
                    break
                if resp.status_code in (301, 302, 303):
                    current_method, current_data = "GET", None
                current = target
                continue
            if resp.status_code == 304:
                result.not_modified = True
            result.content = resp.content
            break
        else:
            result.error = "too many redirects"
        result.elapsed = round(time.monotonic() - start, 3)
        self._record(method, url, result.status, result.blocked or result.error or None)
        return result

    def _attempt(
        self,
        method: str,
        url: str,
        data: dict[str, str] | None,
        headers: dict[str, str] | None,
        retries: int,
    ) -> tuple[httpx.Response | None, str, int]:
        error = ""
        for attempt in range(retries + 1):
            if attempt:
                self.throttle.sleep(self.backoff * 2 ** (attempt - 1))
            try:
                with self.throttle.slot(host_of(url)):
                    resp = self._http.request(method, url, data=data, headers=headers)
            except httpx.HTTPError as exc:
                error = f"{type(exc).__name__}: {exc}"
                logger.info("crawl %s %s failed (attempt %d): %s", method, url, attempt + 1, error)
                continue
            if resp.status_code >= 500 and attempt < retries:
                error = f"HTTP {resp.status_code}"
                continue
            return resp, "", attempt + 1
        return None, error, retries + 1

    def _record(self, method: str, url: str, status: int | None, note: str | None) -> None:
        self.log.append({"method": method, "url": url, "status": status, "note": note})
        logger.info("crawl %s %s -> %s%s", method, url, status, f" ({note})" if note else "")
