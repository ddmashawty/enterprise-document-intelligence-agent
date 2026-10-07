"""Rebuild a ruled table from OCR text boxes.

Ruling lines are found as long runs of dark pixels (text never makes runs that long);
rows / columns are the gaps between them. Each OCR box goes to the cell holding its
center. Where the line between two neighbouring cells is missing, the cells are one
merged cell and every covered position gets the merged text (like ``expand_spans``).
Thick dark bands (coloured header rows) are not treated as lines.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np

from doc_agent.ingest.ocr import OCRBox, join_pieces
from doc_agent.ingest.tables import Origin

_DARK = 160  # gray level below which a pixel counts as ink
_MAX_LINE = 6  # px; thicker runs are filled bands, not ruling lines


@dataclass
class OCRTable:
    cells: list[list[str]]
    origins: list[list[Origin]]
    bbox: tuple[float, float, float, float]


def _longest_runs(ink: np.ndarray) -> np.ndarray:
    """Longest run of consecutive ink pixels in each row (1 px gaps bridged)."""
    bridged = ink.copy()
    bridged[:, 1:-1] |= ink[:, :-2] & ink[:, 2:]
    padded = np.zeros((bridged.shape[0], bridged.shape[1] + 2), dtype=np.int8)
    padded[:, 1:-1] = bridged
    out = np.zeros(bridged.shape[0], dtype=int)
    for i, row in enumerate(np.diff(padded, axis=1)):
        starts, ends = np.flatnonzero(row == 1), np.flatnonzero(row == -1)
        if starts.size:
            out[i] = int((ends - starts).max())
    return out


def _runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) spans where ``flags`` is true."""
    padded = np.concatenate(([0], flags.astype(np.int8), [0]))
    d = np.diff(padded)
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist(), strict=True))


def _lines(ink: np.ndarray, min_len: float) -> list[tuple[int, int]]:
    """Separators along one axis: thin ruling lines as-is; a thick filled band (coloured header)
    contributes zero-width separators at both edges so it becomes a row / column of its own."""
    out: list[tuple[int, int]] = []
    for a, b in _runs(_longest_runs(ink) >= min_len):
        out.extend([(a, b)] if b - a <= _MAX_LINE else [(a, a), (b, b)])
    return out


def _bands(lines: list[tuple[int, int]], size: int) -> list[tuple[int, int]]:
    """Regions between consecutive separators, plus the margins before the first / after the last."""
    edges = [0, *(x for a, b in lines for x in (a, b)), size]
    return [(edges[i], edges[i + 1]) for i in range(0, len(edges), 2) if edges[i + 1] - edges[i] > 2]


def _locate(spans: list[tuple[int, int]], v: float) -> int:
    """Span containing ``v``; a center sitting on a ruling line goes to the nearest span
    (text centered in a merged cell often lands exactly on a line of the next column)."""
    for i, (a, b) in enumerate(spans):
        if a <= v < b:
            return i
    return min(range(len(spans)), key=lambda i: min(abs(v - spans[i][0]), abs(v - spans[i][1])))


def _has_line(ink: np.ndarray, rows: slice, cols: slice, axis: int) -> bool:
    """Whether a ruling line runs through the given strip (most of its length is inked)."""
    strip = ink[rows, cols]
    if strip.size == 0:
        return False
    covered = strip.any(axis=axis)
    return bool(covered.mean() >= 0.7)


def rebuild_table(image: bytes, boxes: list[OCRBox]) -> OCRTable | None:
    """Table grid from a ruled table image; None when the image has no usable grid."""
    from PIL import Image

    if not boxes:
        return None
    gray = np.asarray(Image.open(io.BytesIO(image)).convert("L"))
    ink = gray < _DARK
    h, w = ink.shape
    hlines = _lines(ink, max(0.2 * w, 60))
    vlines = _lines(ink.T, max(0.2 * h, 40))
    if len(hlines) < 2 or len(vlines) < 2:
        return None
    bbox = (float(vlines[0][0]), float(hlines[0][0]), float(vlines[-1][1]), float(hlines[-1][1]))
    inside = [b for b in boxes if inside_bbox(b, bbox)]
    if not inside:
        return None
    rows, cols = _bands(hlines, h), _bands(vlines, w)

    texts: dict[tuple[int, int], list[OCRBox]] = {}
    for b in inside:
        cx, cy = b.center
        texts.setdefault((_locate(rows, cy), _locate(cols, cx)), []).append(b)

    parent = {(r, c): (r, c) for r in range(len(rows)) for c in range(len(cols))}

    def find(x: tuple[int, int]) -> tuple[int, int]:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: tuple[int, int], b: tuple[int, int]) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for r in range(len(rows) - 1):
        y0, y1 = rows[r][1], rows[r + 1][0]
        for c, (x0, x1) in enumerate(cols):
            if not _has_line(ink, slice(max(y0 - 1, 0), y1 + 1), slice(x0 + 3, x1 - 3), axis=0):
                union((r, c), (r + 1, c))
    for c in range(len(cols) - 1):
        x0, x1 = cols[c][1], cols[c + 1][0]
        for r, (y0, y1) in enumerate(rows):
            if not _has_line(ink, slice(y0 + 3, y1 - 3), slice(max(x0 - 1, 0), x1 + 1), axis=1):
                union((r, c), (r, c + 1))

    groups: dict[tuple[int, int], list[OCRBox]] = {}
    for pos, bs in texts.items():
        groups.setdefault(find(pos), []).extend(bs)
    merged = {
        root: join_pieces([b.text for b in sorted(bs, key=lambda b: (round(b.center[1] / 8), b.box[0]))])
        for root, bs in groups.items()
    }
    cells = [[merged.get(find((r, c)), "") for c in range(len(cols))] for r in range(len(rows))]
    origins = [[find((r, c)) for c in range(len(cols))] for r in range(len(rows))]

    keep_r = [r for r in range(len(rows)) if any(cells[r])]
    keep_c = [c for c in range(len(cols)) if any(cells[r][c] for r in range(len(rows)))]
    remap_r = {r: i for i, r in enumerate(keep_r)}
    remap_c = {c: i for i, c in enumerate(keep_c)}
    cells = [[cells[r][c] for c in keep_c] for r in keep_r]
    origins = [[(remap_r.get(origins[r][c][0], 0), remap_c.get(origins[r][c][1], 0)) for c in keep_c] for r in keep_r]
    return OCRTable(cells, origins, bbox)


def inside_bbox(box: OCRBox, bbox: tuple[float, float, float, float], tol: float = 5.0) -> bool:
    cx, cy = box.center
    x0, y0, x1, y1 = bbox
    return x0 - tol <= cx <= x1 + tol and y0 - tol <= cy <= y1 + tol
