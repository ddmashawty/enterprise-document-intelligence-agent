"""Table structure shared by the HTML / PDF / xlsx / xls loaders.

Merged cells are expanded into a full grid (every covered position carries the
merged value) and ``origins`` remembers which source cell each position came
from, so text rendering can print a horizontally merged cell once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Sequence

Origin = tuple[int, int]
TABLE_MARKER = "[[TABLE:{index}]]"
_MARKER_RE = re.compile(r"\[\[TABLE:(\d+)\]\]")
_WS_RE = re.compile(r"[ \t\u3000\xa0]+")
_CJK = r"\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f"
_WRAP_RE = re.compile(rf"(?<=[{_CJK}])\s*\n\s*|\s*\n\s*(?=[{_CJK}])")


def clean_cell(value: Any) -> str:
    """Normalize a cell: None → '', 11.0 → '11', collapse spaces, keep line breaks as spaces."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).replace("\r", "\n")
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.split("\n")]
    return " ".join(ln for ln in lines if ln)


def join_wrapped(text: str | None) -> str:
    """Undo in-cell line wrapping from PDFs: no space around CJK, one space between Latin words."""
    if not text:
        return ""
    return clean_cell(_WRAP_RE.sub("", text))


@dataclass
class Table:
    cells: list[list[str]]
    source: str = ""
    page: int = 1
    index: int = 0
    title: str = ""
    bbox: tuple[float, float, float, float] | None = None
    origins: list[list[Origin]] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        width = max((len(r) for r in self.cells), default=0)
        self.cells = [list(r) + [""] * (width - len(r)) for r in self.cells]
        if self.origins is None:
            self.origins = [[(r, c) for c in range(width)] for r in range(len(self.cells))]

    @property
    def n_rows(self) -> int:
        return len(self.cells)

    @property
    def n_cols(self) -> int:
        return len(self.cells[0]) if self.cells else 0

    def row_values(self, r: int) -> list[str]:
        """Row cells with horizontal merges collapsed and empty cells dropped."""
        out: list[str] = []
        prev: Origin | None = None
        assert self.origins is not None
        for value, origin in zip(self.cells[r], self.origins[r]):
            if origin == prev:
                continue
            prev = origin
            if value:
                out.append(value)
        return out

    def to_text(self) -> str:
        lines = [" | ".join(vals) for r in range(self.n_rows) if (vals := self.row_values(r))]
        if self.title and lines:
            lines.insert(0, self.title)
        return "\n".join(lines)

    def find_rows(self, *needles: str) -> list[list[str]]:
        """Rows (full grid) where every needle appears in some cell."""
        return [row for row in self.cells if all(any(n in cell for cell in row) for n in needles)]

    def column_index(self, header: str, *, header_rows: int = 5) -> int | None:
        for row in self.cells[:header_rows]:
            for c, cell in enumerate(row):
                if cell.replace(" ", "") == header.replace(" ", ""):
                    return c
        return None

    def ffill(self, columns: Iterable[int] | None = None) -> "Table":
        """Fill empty cells from the row above (xls vertical merges often arrive as blanks)."""
        cols = set(range(self.n_cols) if columns is None else columns)
        cells = [list(r) for r in self.cells]
        origins = [list(r) for r in self.origins or []]
        for r in range(1, len(cells)):
            for c in cols:
                if c < len(cells[r]) and not cells[r][c] and cells[r - 1][c]:
                    cells[r][c] = cells[r - 1][c]
                    origins[r][c] = origins[r - 1][c]
        return replace(self, cells=cells, origins=origins)

    def drop_columns(self, columns: Iterable[int]) -> "Table":
        drop = set(columns)
        keep = [c for c in range(self.n_cols) if c not in drop]
        cells = [[row[c] for c in keep] for row in self.cells]
        origins = [[row[c] for c in keep] for row in self.origins or []]
        return replace(self, cells=cells, origins=origins)


def expand_spans(rows: Sequence[Sequence[tuple[str, int, int]]]) -> tuple[list[list[str]], list[list[Origin]]]:
    """Grid from (text, rowspan, colspan) cells, HTML-style placement."""
    grid: dict[tuple[int, int], tuple[str, Origin]] = {}
    width = 0
    for r, row in enumerate(rows):
        c = 0
        for text, rowspan, colspan in row:
            while (r, c) in grid:
                c += 1
            origin = (r, c)
            for dr in range(max(rowspan, 1)):
                for dc in range(max(colspan, 1)):
                    grid.setdefault((r + dr, c + dc), (text, origin))
            c += max(colspan, 1)
            width = max(width, c)
    height = max((r for r, _ in grid), default=-1) + 1
    height = max(height, len(rows))
    width = max([width] + [c + 1 for _, c in grid])
    cells = [[grid.get((r, c), ("", (r, c)))[0] for c in range(width)] for r in range(height)]
    origins = [[grid.get((r, c), ("", (r, c)))[1] for c in range(width)] for r in range(height)]
    return cells, origins


def expand_merged_ranges(
    values: Sequence[Sequence[str]],
    ranges: Iterable[tuple[int, int, int, int]],
) -> tuple[list[list[str]], list[list[Origin]]]:
    """Spreadsheet merges given as (row_lo, row_hi_exclusive, col_lo, col_hi_exclusive), 0-based."""
    width = max((len(r) for r in values), default=0)
    cells = [list(r) + [""] * (width - len(r)) for r in values]
    origins = [[(r, c) for c in range(width)] for r in range(len(cells))]
    for rlo, rhi, clo, chi in ranges:
        if rlo >= len(cells) or clo >= width:
            continue
        value = cells[rlo][clo]
        for r in range(rlo, min(rhi, len(cells))):
            for c in range(clo, min(chi, width)):
                cells[r][c] = value
                origins[r][c] = (rlo, clo)
    return cells, origins


def split_blocks(
    cells: list[list[str]],
    origins: list[list[Origin]],
) -> list[tuple[list[str], list[list[str]], list[list[Origin]]]]:
    """Split a sheet on blank rows into (prose lines, table cells, table origins) blocks.

    Rows holding a single (possibly merged) value are titles / notes and go to prose
    when they precede the table part of a block.
    """
    blocks: list[tuple[list[str], list[list[str]], list[list[Origin]]]] = []
    prose: list[str] = []
    rows: list[list[str]] = []
    rows_o: list[list[Origin]] = []

    def flush() -> None:
        nonlocal prose, rows, rows_o
        if prose or rows:
            blocks.append((prose, rows, rows_o))
        prose, rows, rows_o = [], [], []

    for row, row_o in zip(cells, origins):
        distinct = {o for v, o in zip(row, row_o) if v}
        if not distinct:
            flush()
            continue
        if len(distinct) == 1 and not rows:
            prose.append(next(v for v in row if v))
            continue
        rows.append(row)
        rows_o.append(row_o)
    flush()
    return blocks


def render_page(prose: str, tables: Sequence[Table]) -> str:
    """Substitute ``[[TABLE:n]]`` markers with rendered tables; unplaced tables go to the end."""
    by_index = {t.index: t for t in tables}
    used: set[int] = set()

    def sub(m: re.Match[str]) -> str:
        idx = int(m.group(1))
        table = by_index.get(idx)
        if table is None:
            return ""
        used.add(idx)
        return "\n" + table.to_text() + "\n"

    text = _MARKER_RE.sub(sub, prose)
    rest = [t.to_text() for t in tables if t.index not in used]
    parts = [text] + rest
    lines = [ln.strip() for part in parts for ln in part.splitlines()]
    return "\n".join(ln for ln in lines if ln)
