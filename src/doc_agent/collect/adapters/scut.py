"""华南理工大学 yz.scut.edu.cn / www2.scut.edu.cn (WebPlus).

- The same article appears under several column ids (c30108 / c30111 / c30381): key on ``a{ID}``
  (configured in sites.json).
- College attachments are ``div.wp_pdf_player[pdfsrc]`` (handled by ``collect.attachments``).
- yanzhao.scut.edu.cn (catalog system) redirected to the unified-auth login when the bundle was
  collected: a login redirect is reported ``blocked`` once per run, never retried or worked around
  (data then comes in through manual import). When it answers, it is the same ASP.NET WebForms
  catalog as SCNU's, so its year dropdown is read the same way.
"""

from __future__ import annotations

from doc_agent.collect.adapters.probing import failed
from doc_agent.collect.adapters.scnu import year_options
from doc_agent.collect.base import ProbeContext, ProbeResult
from doc_agent.collect.generic_list import GenericListAdapter
from doc_agent.collect.http import PoliteClient


class ScutAdapter(GenericListAdapter):
    def probes(self, client: PoliteClient, ctx: ProbeContext) -> list[ProbeResult]:
        results = []
        for system in self.site.catalog_systems:
            url = system["url"]
            res = client.get(url)
            if not res.ok:
                results.append(failed("catalog_access", res))
                continue
            years = year_options(res.text)
            shown = f"，年度下拉 {'/'.join(map(str, years))}" if years else ""
            results.append(ProbeResult("catalog_access", url, "new", f"目录系统现在可以访问（sources.json 记为被统一认证拦截）{shown}",
                                       found={"years": years, "title": self.article_title(res.text)}))
        return results
