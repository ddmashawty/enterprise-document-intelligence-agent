"""Checks for handwritten question drafts whose answers come from official text (data/gold/docq_*.json)."""

from __future__ import annotations

import re
from typing import Any

from doc_agent.eval.metrics import contains, normalize_text

_BARE_NUMBER = re.compile(r"^[\d.]+$")
_ELLIPSIS = ("…", "...")


def too_short(alternative: str) -> bool:
    """A bare number under 4 characters ("3", "60", "2.5") matches too much text; it needs its unit."""
    norm = normalize_text(alternative)
    return len(norm) < 2 or (bool(_BARE_NUMBER.match(norm)) and len(norm) < 4)


def _alternatives(item: str | list[str]) -> list[str]:
    return item if isinstance(item, list) else [item]


def check_item(item: dict[str, Any], texts: dict[str, str]) -> list[str]:
    """Problems with one draft question. `texts` maps doc id -> original text; absent docs are not checked."""
    problems: list[str] = []
    qid = item["id"]
    fragments = [*(item.get("evidence") or []), *(item.get("rubric_evidence") or [])]
    if not item.get("evidence"):
        problems.append(f"{qid}: no evidence")
    for frag in fragments:
        if not isinstance(frag, dict) or not {"doc", "text"} <= set(frag):
            problems.append(f"{qid}: evidence must be {{doc, text}} fragments, got {frag!r}")
            continue
        if any(mark in frag["text"] for mark in _ELLIPSIS):
            problems.append(f"{qid}: fragment from {frag['doc']} is spliced with an ellipsis")
        if frag in (item.get("evidence") or []) and frag["doc"] not in item.get("sources", []):
            problems.append(f"{qid}: evidence doc {frag['doc']} is not in sources")
        if frag["doc"] in texts and normalize_text(frag["text"]) not in normalize_text(texts[frag["doc"]]):
            problems.append(f"{qid}: fragment not found verbatim in {frag['doc']}: {frag['text'][:40]}")
    evidence = [f["text"] for f in item.get("evidence") or [] if isinstance(f, dict) and "text" in f]
    for wanted in item.get("must_include") or []:
        short = [alt for alt in _alternatives(wanted) if too_short(alt)]
        if short:
            problems.append(f"{qid}: must_include {short} needs a unit")
        if not any(contains(text, wanted) for text in evidence):
            problems.append(f"{qid}: must_include {wanted!r} is in no evidence fragment")
    checks = item.get("needs_user_check")
    if checks is not None and (not isinstance(checks, list) or not all(isinstance(c, str) and c for c in checks)):
        problems.append(f"{qid}: needs_user_check must be a list of reasons")
    return problems
