"""Flatten /v1/programs payloads into table rows. Every number keeps its year, 口径 and source."""

from __future__ import annotations

from typing import Any

MISSING = "未取得"


def source_url(source: dict[str, Any] | None) -> str | None:
    if not source:
        return None
    return source.get("url") or source.get("attachment_url") or None


def _latest(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(items, key=lambda x: x.get("year") or 0) if items else None


def subjects_cell(program: dict[str, Any]) -> tuple[str, str, str | None]:
    """(科目, 408, 来源) from the latest exam_subjects entry (or the search summary)."""
    entry = _latest(program.get("exam_subjects") or []) or program.get("subjects")
    if not entry:
        return MISSING, "未知", None
    status = entry.get("status")
    year = entry.get("year")
    if status == "no_exam":
        text = f"不考统考（{entry.get('unknown_reason') or '仅招推免'}）"
        return text, "否", source_url(entry.get("source"))
    if status == "unknown":
        return f"未知：{entry.get('unknown_reason') or MISSING}", "未知", source_url(entry.get("source"))
    codes = entry.get("codes") or "/".join(s.get("code") or "?" for s in entry.get("subjects") or [])
    is_408 = entry.get("is_408")
    flag = "是" if is_408 else ("否" if is_408 is False else "未知")
    return f"{codes}（{year}）" if year else codes, flag, source_url(entry.get("source"))


def _main_line(program: dict[str, Any]) -> dict[str, Any] | None:
    lines = program.get("score_lines") or []
    main = [s for s in lines if s.get("scope") in ("college", "school_baseline", "program")]
    return _latest(main or lines)


def program_row(program: dict[str, Any]) -> dict[str, Any]:
    subjects, is_408, subjects_src = subjects_cell(program)
    line = _main_line(program)
    plans = program.get("public_plan") or []
    catalog = _latest([p for p in program.get("plans") or [] if p.get("kind") == "catalog_total"])
    unknown = program.get("public_plan_unknown") or []
    plan_src = (plans[0].get("sources") or [None])[0] if plans else (catalog or {}).get("source")
    return {
        "学校": program.get("school_name") or program.get("school", ""),
        "学院": " ".join(x for x in (program.get("college_code"), program.get("college")) if x),
        "专业": f"{program.get('code', '')} {program.get('name', '')}".strip(),
        "类型": " · ".join(x for x in (program.get("degree_type"), program.get("study_mode")) if x),
        "初试科目": subjects,
        "408": is_408,
        "复试线": (f"{line['total']}（{line['singles']}）" if line.get("singles") else str(line["total"]))
        if line else MISSING,
        "复试线口径": f"{line.get('year')} {line.get('label')}" if line else "",
        "目录计划（含推免）": _catalog_text(catalog) if catalog else MISSING,
        "统招": "；".join(_plan_text(p) for p in plans) or (f"未知：{unknown[0]}" if unknown else MISSING),
        "复试线来源": source_url((line or {}).get("source")),
        "计划来源": source_url(plan_src),
        "科目来源": subjects_src,
        "program_id": program.get("program_id", ""),
    }


def _catalog_text(plan: dict[str, Any]) -> str:
    pool = f"，{plan['pool_scope']} 合计" if plan.get("pool_scope") else ""
    return f"{plan.get('value_text')}（{plan.get('year')}{pool}）"


def _plan_text(plan: dict[str, Any]) -> str:
    value = plan.get("formula") or plan.get("text") or str(plan.get("value"))
    return f"{value}（{plan.get('year')} {plan.get('label')}）"


def program_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [program_row(p) for p in payload.get("programs") or []]


def unknown_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Programs the filters could not decide (e.g. public plan only as an upper bound)."""
    return [
        {
            "学校": p.get("school_name") or p.get("school", ""),
            "学院": " ".join(x for x in (p.get("college_code"), p.get("college")) if x),
            "专业": f"{p.get('code', '')} {p.get('name', '')}".strip(),
            "原因": "；".join(p.get("reasons") or p.get("public_plan_unknown") or []),
        }
        for p in payload.get("unknown") or []
    ]


def fact_lines(program: dict[str, Any]) -> list[str]:
    """Markdown bullets for the detail view: value, 口径, year, verified flag and source link."""
    out: list[str] = []

    def bullet(text: str, fact: dict[str, Any], source: dict[str, Any] | None) -> None:
        url = source_url(source)
        title = (source or {}).get("title") or url or "无来源"
        link = f"[{title}]({url})" if url else title
        mark = "已核对" if fact.get("verified") else "未核对"
        out.append(f"- {text} · {mark} · 来源：{link}")

    for p in program.get("plans") or []:
        bullet(f"**{p.get('label')}** {p.get('value_text')}（{p.get('year')}，{p.get('definition')}）", p, p.get("source"))
    for s in program.get("score_lines") or []:
        singles = f"（{s['singles']}）" if s.get("singles") else ""
        bullet(f"**{s.get('label')}** {s.get('total')}{singles}（{s.get('year')}，{s.get('definition')}）", s, s.get("source"))
    for e in program.get("exam_subjects") or []:
        if e.get("status") == "known":
            text = "、".join(f"{x.get('code')}{x.get('name')}" for x in e.get("subjects") or [])
        else:
            text = f"{e.get('status')}：{e.get('unknown_reason')}"
        bullet(f"**初试科目** {text}（{e.get('year')}）", e, e.get("source"))
    for a in program.get("admission_stats") or []:
        bullet(f"**{a.get('label') or a.get('kind')}** {a.get('value')}（{a.get('year')}，{a.get('definition')}）",
               a, a.get("source"))
    return out
