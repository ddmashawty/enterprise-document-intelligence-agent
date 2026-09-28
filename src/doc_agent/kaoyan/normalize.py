from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

PROGRAM_CODE_RE = re.compile(r"^\d{4}[0-9A-Z]{2}$")
SAME_AS_ABOVE = {"同上", "同 上", "〃"}

# Static aliases on top of the name / short name / id taken from sources.json.
DEFAULT_SCHOOL_ALIASES: dict[str, tuple[str, ...]] = {
    "sysu": ("中山大学", "中大", "中山", "SYSU"),
    "scut": ("华南理工大学", "华工", "华南理工", "SCUT"),
    "jnu": ("暨南大学", "暨大", "暨南", "JNU"),
    "scnu": ("华南师范大学", "华师", "华南师范", "华南师大", "SCNU"),
}

_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
_UPPER_BOUND_CHARS = ("≤", "<=", "＜=", "不超过")


@dataclass(frozen=True)
class CountValue:
    value: int | None
    is_upper_bound: bool = False
    pool_scope: str | None = None
    text: str = ""

    @property
    def is_empty(self) -> bool:
        return self.value is None


@dataclass(frozen=True)
class Subject:
    code: str
    name: str


@dataclass(frozen=True)
class SubjectLines:
    politics: int | None
    foreign_lang: int | None
    subject1: int | None
    subject2: int | None
    note: str = ""


@dataclass(frozen=True)
class CollegeName:
    code: str | None
    name: str
    campus: str | None


def clean(text: str | None) -> str:
    if text is None:
        return ""
    return str(text).replace("\u3000", " ").replace("\xa0", " ").strip()


def parse_count(text: str | None) -> CountValue:
    """Parse plan/推免 cells: '55', '≤41', '（0812合计≤19）', ''."""
    raw = clean(text)
    if not raw:
        return CountValue(None, text=raw)
    m = re.fullmatch(r"[（(]\s*(\d{4})\s*合计\s*(?:≤|<=)\s*(\d+)\s*[）)]", raw)
    if m:
        return CountValue(int(m.group(2)), True, m.group(1), raw)
    for mark in _UPPER_BOUND_CHARS:
        if raw.startswith(mark):
            num = re.match(r"\d+", raw[len(mark):].strip())
            if num:
                return CountValue(int(num.group(0)), True, None, raw)
    if re.fullmatch(r"\d+", raw):
        return CountValue(int(raw), False, None, raw)
    return CountValue(None, text=raw)


def parse_total_tm(text: str | None) -> tuple[int | None, int | None]:
    """'48(17)' → (48, 17): 华师目录“总(推免)”; '20' → (20, None)."""
    raw = clean(text).replace(" ", "")
    m = re.fullmatch(r"(\d+)[（(](\d+)[)）]", raw)
    if m:
        return int(m.group(1)), int(m.group(2))
    if re.fullmatch(r"\d+", raw):
        return int(raw), None
    return None, None


def resolve_same(value: str | None, previous: str | None) -> str:
    """'同上' inherits the previous row's value in the same column."""
    v = clean(value)
    if v in SAME_AS_ABOVE:
        return clean(previous)
    return v


def fill_same_as_above(rows: Sequence[Sequence[str]], columns: Iterable[int] | None = None) -> list[list[str]]:
    out: list[list[str]] = []
    cols = set(columns) if columns is not None else None
    for row in rows:
        cur = [clean(c) for c in row]
        if out:
            prev = out[-1]
            for i, cell in enumerate(cur):
                if (cols is None or i in cols) and cell in SAME_AS_ABOVE and i < len(prev):
                    cur[i] = prev[i]
        out.append(cur)
    return out


def parse_subject(text: str | None) -> Subject | None:
    raw = clean(text).lstrip(_CIRCLED).strip()
    m = re.match(r"^(\d{3})\s*(.+)$", raw)
    if not m:
        return None
    return Subject(code=m.group(1), name=m.group(2).strip())


def split_subjects(text: str | None) -> list[Subject]:
    """'①101思想政治理论②204英语（二）…' or newline-separated → subjects."""
    raw = clean(text)
    if not raw:
        return []
    parts = re.split(rf"[{_CIRCLED}\n\r]+|\s{{2,}}|(?<=[\u4e00-\u9fff）)])\s+(?=\d{{3}})", raw)
    subjects: list[Subject] = []
    for part in parts:
        s = parse_subject(part)
        if s:
            subjects.append(s)
    return subjects


def is_408(subjects: Iterable[Subject]) -> bool:
    return any(s.code == "408" for s in subjects)


def normalize_program_code(text: str | None) -> str | None:
    """Merge codes split by in-cell line breaks ('0854\\n04' → '085404')."""
    raw = re.sub(r"\s+", "", clean(text)).upper()
    return raw if PROGRAM_CODE_RE.fullmatch(raw) else None


def parse_subject_lines(text: str | None) -> SubjectLines:
    """Single-subject lines: '政治50/外语50/业务课一60/业务课二60', '业务一53/业务二53',
    '政治50/外语50/业务课70/70（学校基本线）', '30/30/48/48'."""
    raw = clean(text)
    if not raw:
        return SubjectLines(None, None, None, None)
    note = ""
    m_note = re.search(r"[（(]([^）)]*)[）)]\s*$", raw)
    if m_note:
        note = m_note.group(1)
        raw = raw[: m_note.start()]
    nums = [int(n) for n in re.findall(r"\d+", raw)]
    if len(nums) == 4:
        return SubjectLines(nums[0], nums[1], nums[2], nums[3], note)
    if len(nums) == 3:
        return SubjectLines(nums[0], nums[1], nums[2], nums[2], note)
    return SubjectLines(None, None, None, None, note or raw)


def parse_college(text: str | None) -> CollegeName:
    """'041人工智能学院（佛山南海）' → ('041', '人工智能学院', '佛山南海')."""
    raw = clean(text)
    campus = None
    m = re.search(r"[（(]([^）)]+)[）)]\s*$", raw)
    if m:
        campus = m.group(1)
        raw = raw[: m.start()].strip()
    m = re.match(r"^(\d{3})\s*(.+)$", raw)
    if m:
        return CollegeName(m.group(1), m.group(2).strip(), campus)
    return CollegeName(None, raw, campus)


def parse_year(text: str | None) -> int | None:
    m = re.match(r"\s*(\d{4})", clean(text))
    return int(m.group(1)) if m else None


def split_source_urls(text: str | None) -> list[str]:
    """'url1（说明） ; url2' → ['url1', 'url2'] (drops trailing Chinese/English bracket notes)."""
    urls: list[str] = []
    for seg in clean(text).split(" ; "):
        url = re.split(r"[（(]", seg, maxsplit=1)[0].strip()
        if url:
            urls.append(url)
    return urls


def build_school_aliases(
    schools: Iterable[Mapping[str, object]] | None = None,
    extra: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, str]:
    """alias (lower-cased) → school id, from sources.json schools[] plus static extras."""
    mapping: dict[str, str] = {}
    for sid, aliases in (extra if extra is not None else DEFAULT_SCHOOL_ALIASES).items():
        mapping[sid.lower()] = sid
        for a in aliases:
            mapping[str(a).lower()] = sid
    for s in schools or []:
        sid = str(s.get("id") or "")
        if not sid:
            continue
        mapping[sid.lower()] = sid
        for key in ("name", "short", "short_name"):
            val = s.get(key)
            if val:
                mapping[str(val).lower()] = sid
    return mapping


def resolve_school(text: str | None, aliases: Mapping[str, str] | None = None) -> str | None:
    raw = clean(text).lower()
    if not raw:
        return None
    table = aliases or build_school_aliases()
    if raw in table:
        return table[raw]
    return None


def find_schools(text: str | None, aliases: Mapping[str, str] | None = None) -> list[str]:
    """All schools mentioned in free text, longest alias first, in order of appearance."""
    raw = clean(text).lower()
    table = aliases or build_school_aliases()
    hits: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for alias in sorted(table, key=len, reverse=True):
        start = raw.find(alias)
        while start != -1:
            end = start + len(alias)
            ascii_alias = alias.isascii()
            boundary_ok = not ascii_alias or (
                (start == 0 or not raw[start - 1].isalnum())
                and (end == len(raw) or not raw[end].isalnum())
            )
            overlaps = any(s < end and start < e for s, e in taken)
            if boundary_ok and not overlaps:
                hits.append((start, table[alias]))
                taken.append((start, end))
            start = raw.find(alias, end)
    out: list[str] = []
    for _, sid in sorted(hits):
        if sid not in out:
            out.append(sid)
    return out
