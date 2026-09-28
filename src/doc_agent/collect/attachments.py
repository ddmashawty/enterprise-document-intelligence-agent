"""Find attachments in an article page.

Handles plain ``<a href>`` file links, WebPlus PDF players (``div[pdfsrc]`` with the
real file name in ``sudyfile-attr``), ``<img src>``, inline ``data:`` images and
relative paths such as ``../../docs/...``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from doc_agent.ingest.loaders import decode_data_uri
from doc_agent.ingest.tables import clean_cell

AttachmentKind = Literal["link", "pdf_player", "image", "data_uri"]

FILE_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".zip", ".rar", ".7z",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
)
_SUDY_TITLE = re.compile(r"""['"]title['"]\s*:\s*['"]([^'"]+)['"]""")
_MIME_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}


@dataclass(frozen=True)
class Attachment:
    url: str
    name: str
    kind: AttachmentKind
    ext: str = ""
    mime: str = ""
    sha256: str = ""
    data: bytes | None = field(default=None, repr=False, compare=False)


def _ext(value: str) -> str:
    suffix = PurePosixPath(unquote(urlparse(value).path)).suffix.lower()
    return suffix if suffix in FILE_EXTENSIONS else ""


def _name_ext(name: str) -> str:
    suffix = PurePosixPath(name).suffix.lower()
    return suffix if suffix in FILE_EXTENSIONS else ""


def _sudy_title(tag) -> str:
    m = _SUDY_TITLE.search(str(tag.get("sudyfile-attr") or ""))
    return clean_cell(m.group(1)) if m else ""


def _basename(url: str) -> str:
    return PurePosixPath(unquote(urlparse(url).path)).name


def discover_attachments(html: str | BeautifulSoup, base_url: str = "", *, include_images: bool = True) -> list[Attachment]:
    soup = html if isinstance(html, BeautifulSoup) else BeautifulSoup(html, "lxml")
    base_tag = soup.find("base", href=True)
    base = urljoin(base_url, str(base_tag["href"])) if base_tag else base_url
    found: list[Attachment] = []
    seen: set[str] = set()

    def add(att: Attachment) -> None:
        key = att.sha256 if att.kind == "data_uri" else att.url
        if key and key not in seen:
            seen.add(key)
            found.append(att)

    for player in soup.select("[pdfsrc]"):
        src = str(player.get("pdfsrc") or "").strip()
        if not src:
            continue
        url = urljoin(base, src)
        name = _sudy_title(player) or _basename(url)
        add(Attachment(url=url, name=name, kind="pdf_player", ext=_name_ext(name) or _ext(url) or ".pdf"))

    for a in soup.find_all("a", href=True):
        href = str(a["href"]).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        url = urljoin(base, href)
        text = clean_cell(a.get_text(" ", strip=True))
        sudy = _sudy_title(a)
        ext = _ext(url) or _name_ext(text) or _name_ext(sudy)
        if not ext:
            continue
        if _name_ext(text):
            name = text
        elif _name_ext(sudy):
            name = sudy
        else:
            name = f"{text}{ext}" if text else _basename(url)
        add(Attachment(url=url, name=name, kind="link", ext=ext))

    if include_images:
        for img in soup.find_all("img"):
            src = str(img.get("src") or "").strip()
            if not src:
                continue
            alt = clean_cell(img.get("alt"))
            if src.startswith("data:"):
                decoded = decode_data_uri(src)
                if decoded is None:
                    continue
                mime, data = decoded
                sha = hashlib.sha256(data).hexdigest()
                ext = _MIME_EXT.get(mime, "")
                add(Attachment(url="", name=alt or f"inline_{sha[:12]}{ext}", kind="data_uri", ext=ext,
                               mime=mime, sha256=sha, data=data))
            else:
                url = urljoin(base, src)
                add(Attachment(url=url, name=alt or _basename(url), kind="image", ext=_ext(url)))
    return found
