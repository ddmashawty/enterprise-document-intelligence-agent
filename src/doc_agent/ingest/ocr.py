"""Pluggable OCR backends for images and scanned PDF pages.

- ``none`` (default): nothing is recognized; documents are flagged ``needs_ocr``.
- ``rapidocr``: local ONNX OCR (``requirements-ocr.txt``); returns text boxes, tables are
  rebuilt from the ruling lines by :mod:`doc_agent.ingest.ocr_table`.
- ``vision``: OpenAI-compatible multimodal chat endpoint (``VISION_*`` settings); the model
  transcribes tables as Markdown.

Results are cached per image sha256 under ``OCR_CACHE_DIR`` (git-ignored).
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import httpx

if TYPE_CHECKING:
    from doc_agent.config import Settings

PLANNED_BACKENDS = ("paddleocr",)
_CJK = r"\u2e80-\u9fff\uf900-\ufaff"


@dataclass
class OCRBox:
    text: str
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 in image pixels
    score: float = 1.0

    @property
    def center(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.box
        return (x0 + x1) / 2, (y0 + y1) / 2


@dataclass
class OCRResult:
    text: str
    backend: str
    lines: list[str] = field(default_factory=list)
    boxes: list[OCRBox] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OCRResult:
        boxes = [OCRBox(b["text"], tuple(b["box"]), b.get("score", 1.0)) for b in d.get("boxes") or []]  # type: ignore[arg-type]
        return cls(text=d.get("text", ""), backend=d.get("backend", ""), lines=list(d.get("lines") or []),
                   boxes=boxes, tables=[list(map(list, t)) for t in d.get("tables") or []])


class OCRBackend(Protocol):
    name: str

    def available(self) -> bool: ...

    def recognize(self, image: bytes) -> OCRResult | None: ...


class NoOCR:
    name = "none"

    def available(self) -> bool:
        return False

    def recognize(self, image: bytes) -> OCRResult | None:
        return None


# -- text helpers ----------------------------------------------------------------


def fix_cjk_punct(text: str) -> str:
    """OCR often returns ASCII brackets / commas inside Chinese text: 英语(一) → 英语（一）."""
    text = re.sub(rf"(?<=[{_CJK}])\(|\((?=[{_CJK}])", "（", text)
    text = re.sub(rf"(?<=[{_CJK}])\)|\)(?=[{_CJK}])", "）", text)
    text = re.sub(r"\s+(?=[（）])|(?<=[（）])\s+", "", text)
    return re.sub(rf"(?<=[{_CJK}（）]),(?=[{_CJK}（）])", "，", text)


def join_pieces(pieces: list[str]) -> str:
    """Join OCR fragments of one line / cell: no space next to CJK, one space between Latin words."""
    out = ""
    for piece in (p.strip() for p in pieces):
        if not piece:
            continue
        if out and not (re.search(rf"[{_CJK}\u3000-\u303f\uff00-\uffef]$", out)
                        or re.match(rf"[{_CJK}\u3000-\u303f\uff00-\uffef]", piece)):
            out += " "
        out += piece
    return out


def group_lines(boxes: list[OCRBox]) -> list[str]:
    """Reading-order lines: boxes whose vertical centers are within half a line height."""
    if not boxes:
        return []
    heights = sorted(b.box[3] - b.box[1] for b in boxes)
    tol = max(heights[len(heights) // 2] * 0.5, 4.0)
    rows: list[list[OCRBox]] = []
    for b in sorted(boxes, key=lambda b: b.center[1]):
        if rows and abs(b.center[1] - rows[-1][-1].center[1]) <= tol:
            rows[-1].append(b)
        else:
            rows.append([b])
    return [join_pieces([b.text for b in sorted(row, key=lambda b: b.box[0])]) for row in rows]


# -- rapidocr ----------------------------------------------------------------------


@lru_cache(maxsize=1)
def _rapid_engine() -> Any:
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


class RapidOCRBackend:
    name = "rapidocr"
    cache_key = "rapidocr"

    def available(self) -> bool:
        try:
            import rapidocr_onnxruntime  # noqa: F401
        except ImportError:
            return False
        return True

    def recognize(self, image: bytes) -> OCRResult | None:
        result, _elapsed = _rapid_engine()(image)
        boxes = []
        for points, text, score in result or []:
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            boxes.append(OCRBox(fix_cjk_punct(str(text)), (min(xs), min(ys), max(xs), max(ys)), float(score)))
        lines = group_lines(boxes)
        return OCRResult(text="\n".join(lines), backend=self.name, lines=lines, boxes=boxes)


# -- vision (OpenAI-compatible multimodal) ---------------------------------------------

VISION_PROMPT = """你是表格转写员。只转写图片里看得到的文字，不推断、不补全、不改写数字。
- 表格用 Markdown 表格输出，表头照抄；合并单元格的内容在它覆盖的每个格子里重复写一遍。
- 表格以外的文字按原顺序逐行输出。
- 看不清的字写 [?]，不要猜。"""

_MD_SEPARATOR = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")


def markdown_tables(text: str) -> tuple[list[list[list[str]]], list[str]]:
    """Split a Markdown answer into tables (rows of cells) and the remaining text lines."""
    tables: list[list[list[str]]] = []
    lines: list[str] = []
    current: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("|"):
            if not _MD_SEPARATOR.match(line):
                current.append([c.strip() for c in line.strip("|").split("|")])
            continue
        if current:
            tables.append(current)
            current = []
        if line and not line.startswith("```"):
            lines.append(line)
    if current:
        tables.append(current)
    return tables, lines


def _image_mime(image: bytes) -> str:
    if image.startswith(b"\x89PNG"):
        return "image/png"
    if image[:3] == b"GIF":
        return "image/gif"
    return "image/jpeg"


class VisionBackend:
    name = "vision"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        *,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport

    @property
    def cache_key(self) -> str:
        return "vision-" + re.sub(r"[^A-Za-z0-9._-]+", "_", self.model)

    def available(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)

    def recognize(self, image: bytes) -> OCRResult | None:
        data_url = f"data:{_image_mime(image)};base64,{base64.b64encode(image).decode()}"
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": VISION_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": "请转写这张图片。"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]},
            ],
        }
        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            resp = client.post(f"{self.base_url}/chat/completions", json=payload,
                               headers={"Authorization": f"Bearer {self.api_key}"})
            resp.raise_for_status()
        content = str(resp.json()["choices"][0]["message"]["content"] or "")
        tables, lines = markdown_tables(content)
        return OCRResult(text=content.strip(), backend=self.name, lines=lines, tables=tables)


# -- cache -----------------------------------------------------------------------------


class CachedOCR:
    """Wraps a backend; results are stored as ``<cache_dir>/<backend key>/<sha256>.json``."""

    def __init__(self, inner: OCRBackend, cache_dir: Path) -> None:
        self.inner = inner
        self.name = inner.name
        self.dir = Path(cache_dir) / str(getattr(inner, "cache_key", inner.name))

    def available(self) -> bool:
        return self.inner.available()

    def path_for(self, image: bytes) -> Path:
        return self.dir / f"{hashlib.sha256(image).hexdigest()}.json"

    def recognize(self, image: bytes) -> OCRResult | None:
        path = self.path_for(image)
        if path.exists():
            return OCRResult.from_dict(json.loads(path.read_text(encoding="utf-8")))
        result = self.inner.recognize(image)
        if result is not None:
            self.dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result.to_dict(), ensure_ascii=False), encoding="utf-8")
        return result


def get_ocr_backend(name: str | None = "none", settings: Settings | None = None) -> OCRBackend:
    """Backend by name; with ``settings`` the result is cached under ``settings.ocr_cache_path``."""
    key = (name or "none").strip().lower()
    backend: OCRBackend
    if key == "none":
        return NoOCR()
    if key == "rapidocr":
        backend = RapidOCRBackend()
    elif key == "vision":
        if settings is None:
            raise ValueError("OCR backend 'vision' needs settings (VISION_BASE_URL / VISION_MODEL / VISION_API_KEY)")
        backend = VisionBackend(settings.vision_base_url, settings.vision_model, settings.vision_api_key,
                                timeout=settings.vision_timeout)
    elif key in PLANNED_BACKENDS:
        raise ValueError(f"OCR backend '{key}' is not implemented yet; use 'rapidocr' or 'vision'")
    else:
        raise ValueError(f"Unknown OCR backend '{key}'; supported: none, rapidocr, vision")
    return CachedOCR(backend, settings.ocr_cache_path) if settings is not None else backend
