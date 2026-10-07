"""华南师范大学 yz.scnu.edu.cn (DedeCMS-style) + yanzhao.scnu.edu.cn catalog (ASP.NET WebForms).

- Articles are ``/a/YYYYMMDD/<id>.html`` on yz / cs / ai / ds; list pagination follows "下一页".
- The catalog form posts back ``__VIEWSTATE`` / ``__EVENTVALIDATION``; college = ``drpYx``,
  year = ``drpNd``, study mode = ``drpXxfs``; grid pages are ``lnkPage`` postbacks.
  A new year in the ``drpNd`` dropdown means that year's catalog is online.
  (Rewritten from data/kaoyan/scripts/scnu_zsml.py.)
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from doc_agent.collect.adapters.probing import failed
from doc_agent.collect.base import FetchResult, ProbeContext, ProbeResult
from doc_agent.collect.generic_list import GenericListAdapter
from doc_agent.collect.http import PoliteClient

PREFIX = "ctl00$contentParent$"
DRP_YEAR = PREFIX + "drpNd"
DRP_COLLEGE = PREFIX + "drpYx"
DRP_PROGRAM = PREFIX + "drpZy"
DRP_TYPE = PREFIX + "drpZylx"
DRP_MODE = PREFIX + "drpXxfs"
_POSTBACK = re.compile(r"__doPostBack\('([^']+)'\s*,\s*'([^']*)'\)")


def webforms_state(html: str) -> dict[str, str]:
    """Hidden / text inputs and the selected option of every select (what the browser would post)."""
    soup = BeautifulSoup(html, "lxml")
    form: dict[str, str] = {}
    for inp in soup.find_all("input"):
        name = inp.get("name")
        if name and (inp.get("type") or "text").lower() in ("hidden", "text"):
            form[str(name)] = str(inp.get("value") or "")
    for sel in soup.find_all("select"):
        name = sel.get("name")
        if not name:
            continue
        opt = sel.find("option", selected=True) or sel.find("option")
        form[str(name)] = str(opt.get("value") or "") if opt else ""
    return form


def postback(state: dict[str, str], target: str, argument: str = "", **fields: str) -> dict[str, str]:
    data = dict(state)
    data.update(fields)
    data["__EVENTTARGET"] = target
    data["__EVENTARGUMENT"] = argument
    return data


def year_options(html: str) -> list[int]:
    soup = BeautifulSoup(html, "lxml")
    sel = soup.find("select", attrs={"name": DRP_YEAR})
    if sel is None:
        return []
    return sorted({int(v) for o in sel.find_all("option") if (v := str(o.get("value") or "")).isdigit()}, reverse=True)


def pager_target(html: str, page_no: int) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if "lnkPage" in href and a.get_text(strip=True) == str(page_no):
            m = _POSTBACK.search(href)
            if m:
                return m.group(1)
    return None


class ScnuAdapter(GenericListAdapter):
    @property
    def catalog_url(self) -> str:
        return str(self.site.probe.get("catalog_url") or "")

    def probes(self, client: PoliteClient, ctx: ProbeContext) -> list[ProbeResult]:
        url = self.catalog_url
        if not url:
            return []
        res = client.get(url)
        if not res.ok:
            return [failed("catalog_year", res)]
        years = year_options(res.text)
        if not years:
            return [ProbeResult("catalog_year", url, "error", "页面里没有年份下拉框 drpNd")]
        shown = "/".join(map(str, years))
        latest = ctx.latest_catalog_year
        if latest is not None and years[0] > latest:
            return [ProbeResult("catalog_year", url, "new", f"年份下拉出现 {years[0]}（{shown}）",
                                found={"year": years[0], "years": years})]
        return [ProbeResult("catalog_year", url, "unchanged", f"年份下拉: {shown}", found={"years": years})]

    def fetch_catalog(
        self,
        client: PoliteClient,
        college: str,
        *,
        year: int | None = None,
        study_mode: str = "1",
        max_grid_pages: int = 10,
    ) -> list[FetchResult]:
        """GET the form, post back the college (and year / study mode), then walk the grid pages."""
        url = self.catalog_url
        first = client.get(url)
        if not first.ok:
            return [first]
        fields = {DRP_COLLEGE: college, DRP_PROGRAM: "", DRP_TYPE: "", DRP_MODE: study_mode}
        if year is not None:
            fields[DRP_YEAR] = str(year)
        res = client.post(url, postback(webforms_state(first.text), DRP_COLLEGE, **fields))
        pages = [res]
        while res.ok and len(pages) < max_grid_pages:
            target = pager_target(res.text, len(pages) + 1)
            if not target:
                break
            res = client.post(url, postback(webforms_state(res.text), target))
            pages.append(res)
        return pages
