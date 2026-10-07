"""暨南大学 yz.jnu.edu.cn (WebPlus).

- Only ``/tzgg/list.htm`` … ``list18.htm`` is crawled; ``/33003/`` and ``/32993/`` are empty and
  ``/33059/list.htm`` is 410 (skip patterns in sites.json).
- The catalog lives at ``/{year}nssyjszszyml/list.htm``: probe the year after the newest known one.
"""

from __future__ import annotations

from doc_agent.collect.adapters.probing import GONE, failed
from doc_agent.collect.base import ProbeContext, ProbeResult
from doc_agent.collect.generic_list import GenericListAdapter
from doc_agent.collect.http import PoliteClient

_MISSING_COLUMN = ("找不到对应的栏目", "页面不存在", "404")


class JnuAdapter(GenericListAdapter):
    def probes(self, client: PoliteClient, ctx: ProbeContext) -> list[ProbeResult]:
        template = self.site.probe.get("catalog_year_url")
        if not template or ctx.latest_catalog_year is None:
            return []
        year = ctx.latest_catalog_year + 1
        url = template.format(year=year)
        res = client.get(url)
        if res.ok:
            text = res.text
            title = self.article_title(text)
            if any(marker in title for marker in _MISSING_COLUMN) or "找不到对应的栏目" in text[:5000]:
                return [ProbeResult("catalog_year", url, "not_found", f"{year} 目录栏目不存在")]
            return [ProbeResult("catalog_year", url, "new", f"{year} 招生专业目录已上线",
                                found={"year": year, "title": title})]
        if res.status in GONE and not res.skipped:
            return [ProbeResult("catalog_year", url, "not_found", f"{year} 目录未发布（HTTP {res.status}）")]
        return [failed("catalog_year", res)]
