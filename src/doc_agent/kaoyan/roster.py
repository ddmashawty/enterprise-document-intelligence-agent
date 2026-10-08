"""Head counts from scanned admission lists via OCR.

Only counts leave this module: one row per OCR line that carries exactly one program
code. Names, exam numbers and scores are never returned, logged or written; the raw
OCR stays in the git-ignored OCR cache like the source PDF itself.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from doc_agent.ingest.ocr import OCRBackend, OCRResult, group_lines

PROGRAM_CODE_RE = re.compile(r"(?<![0-9A-Za-z])((?:0[1-9]|1[0-4])\d{2}[0-9A-Z]{2})(?![0-9A-Za-z])")


@dataclass
class RosterCount:
    counts: Counter[str] = field(default_factory=Counter)
    pages: int = 0
    pages_failed: list[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def summary(self) -> dict[str, object]:
        return {"total": self.total, "by_program_code": dict(sorted(self.counts.items())),
                "pages": self.pages, "pages_failed": self.pages_failed}


def count_lines(lines: Iterable[str]) -> Counter[str]:
    """Rows per program code: a line counts when it carries exactly one program code."""
    counts: Counter[str] = Counter()
    for line in lines:
        codes = set(PROGRAM_CODE_RE.findall(line))
        if len(codes) == 1:
            counts[codes.pop()] += 1
    return counts


def count_results(results: Iterable[OCRResult | None]) -> RosterCount:
    out = RosterCount()
    for page_no, result in enumerate(results, start=1):
        out.pages += 1
        if result is None:
            out.pages_failed.append(page_no)
            continue
        lines = group_lines(result.boxes) if result.boxes else result.lines
        out.counts.update(count_lines(lines))
    return out


def roster_counts(path: Path, backend: OCRBackend, pages: list[int] | None = None) -> RosterCount:
    """OCR the given (default: all) pages of a scanned roster PDF and count rows per program code."""
    from pypdf import PdfReader

    from doc_agent.ingest.loaders import render_pdf_pages

    if not backend.available():
        raise RuntimeError(f"OCR backend '{backend.name}' is not available")
    numbers = pages or list(range(1, len(PdfReader(str(path)).pages) + 1))

    def results() -> Iterable[OCRResult | None]:
        for n in numbers:
            try:
                yield backend.recognize(render_pdf_pages(path, [n])[n])
            except Exception:  # noqa: BLE001
                yield None

    out = count_results(results())
    out.pages_failed = [numbers[i - 1] for i in out.pages_failed]
    return out
