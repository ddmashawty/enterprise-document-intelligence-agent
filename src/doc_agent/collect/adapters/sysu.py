"""中山大学 graduate.sysu.edu.cn/zsw (Drupal).

- The pager links point at the site root (``/?page=N``) instead of ``/zsw/postgraduate?page=N``.
- Articles are ``/zsw/article/<auto-increment id>``: probe the next few ids for new notices.
"""

from __future__ import annotations

import re

from doc_agent.collect.adapters.probing import GONE, failed
from doc_agent.collect.base import ProbeContext, ProbeResult
from doc_agent.collect.generic_list import GenericListAdapter
from doc_agent.collect.http import PoliteClient

_ROOT_PAGER = re.compile(r"^https?://graduate\.sysu\.edu\.cn/?\?(?:[^#]*&)?page=(\d+)")
LIST_URL = "https://graduate.sysu.edu.cn/zsw/postgraduate"


def fix_page_url(url: str) -> str:
    m = _ROOT_PAGER.match(url)
    return f"{LIST_URL}?page={m.group(1)}" if m else url


class SysuAdapter(GenericListAdapter):
    def next_page_url(self, html: str, url: str) -> str | None:
        nxt = super().next_page_url(html, url)
        return fix_page_url(nxt) if nxt else None

    def probes(self, client: PoliteClient, ctx: ProbeContext) -> list[ProbeResult]:
        cfg = self.site.probe
        if not cfg.get("article_url"):
            return []
        rx = re.compile(cfg["article_id_regex"])
        template = cfg["article_url"]
        ids = [int(m.group(1)) for u in [*ctx.known_urls, *(d.url for d in ctx.discovered)] if (m := rx.search(u))]
        if not ids:
            return [ProbeResult("article_id", template, "skipped", "没有已知文章 ID")]
        start = max(ids) + 1
        results: list[ProbeResult] = []
        misses = 0
        for article_id in range(start, start + max(ctx.probe_ids, 1)):
            url = template.format(id=article_id)
            res = client.get(url)
            if res.ok:
                misses = 0
                results.append(ProbeResult("article_id", url, "new", found={
                    "id": article_id, "title": self.article_title(res.text)}))
            elif res.status in GONE and not res.skipped:
                misses += 1
                if misses >= 2:
                    break
            else:
                results.append(failed("article_id", res))
                break
        if not results:
            results.append(ProbeResult("article_id", template.format(id=start), "not_found",
                                       f"已知最大 ID {start - 1}，之后未发现新文章"))
        return results
