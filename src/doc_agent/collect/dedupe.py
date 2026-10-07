"""URL normalization, article keys and content fingerprints."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from doc_agent.ingest.loaders import decode_html

_DEFAULT_PORTS = {"http": "80", "https": "443"}
# Characters kept literally when re-encoding a decoded path / query.
_PATH_SAFE = "/:@!$&'()*+,;=-._~"
_QUERY_SAFE = "=&/:@!$'()*+,;-._~"
# Page furniture that changes on every view (visit counters, render timestamps).
_VOLATILE = re.compile(
    r"(?:浏览|阅读|点击|访问)(?:次数|量|数)?\s*[:：]?\s*\d+\s*次?|"
    r"(?:当前时间|生成时间|更新时间)\s*[:：]\s*[\d\-/: ]+"
)


def normalize_url(url: str) -> str:
    """Comparison key for a URL: https, lower-case host, no default port / fragment / trailing slash,
    path and query decoded then re-encoded (so %E4%B8%AD and 中 compare equal)."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme == "http":
        scheme = "https"
    host = (parts.hostname or "").lower()
    if parts.port and str(parts.port) != _DEFAULT_PORTS.get(parts.scheme.lower(), ""):
        host = f"{host}:{parts.port}"
    path = quote(unquote(parts.path), safe=_PATH_SAFE) or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    query = quote(unquote(parts.query), safe=_QUERY_SAFE)
    return urlunsplit((scheme, host, path, query, ""))


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_hash(text: str, n: int = 8) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def page_text(raw: bytes | str) -> str:
    """Visible text of an HTML page without scripts, styles and view counters."""
    html = decode_html(raw) if isinstance(raw, bytes) else raw
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    return " ".join(_VOLATILE.sub(" ", soup.get_text(" ")).split())


def text_fingerprint(raw: bytes | str) -> str:
    return sha256_bytes(page_text(raw).encode("utf-8"))


_UNSAFE = re.compile(r'[\\/:*?"<>|\s]+')


def safe_filename(name: str, limit: int = 80) -> str:
    cleaned = _UNSAFE.sub("_", name).strip("._") or "file"
    if len(cleaned) <= limit:
        return cleaned
    stem, dot, ext = cleaned.rpartition(".")
    if dot and 0 < len(ext) <= 5:
        return stem[: limit - len(ext) - 1] + "." + ext
    return cleaned[:limit]
