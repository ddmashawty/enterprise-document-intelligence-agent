"""Pluggable OCR backends.

Only ``none`` exists so far: images and scanned PDF pages are flagged ``needs_ocr``
instead of failing. ``rapidocr`` / ``paddleocr`` / ``vision`` plug in here later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

PLANNED_BACKENDS = ("rapidocr", "paddleocr", "vision")


@dataclass
class OCRResult:
    text: str
    backend: str
    lines: list[str] = field(default_factory=list)


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


_BACKENDS: dict[str, type] = {"none": NoOCR}


def get_ocr_backend(name: str | None = "none") -> OCRBackend:
    key = (name or "none").strip().lower()
    if key in _BACKENDS:
        return _BACKENDS[key]()
    if key in PLANNED_BACKENDS:
        raise ValueError(f"OCR backend '{key}' is not implemented yet; use 'none'")
    raise ValueError(f"Unknown OCR backend '{key}'; supported: {', '.join(_BACKENDS)}")
