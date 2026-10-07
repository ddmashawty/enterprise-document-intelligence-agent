"""Collection layer (K6): all HTTP goes through httpx.MockTransport and a fake clock."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from doc_agent.collect.adapters import build_adapter
from doc_agent.collect.adapters.scnu import (
    DRP_COLLEGE,
    DRP_YEAR,
    ScnuAdapter,
    webforms_state,
)
from doc_agent.collect.adapters.sysu import fix_page_url
from doc_agent.collect.base import ListSource, ProbeContext
from doc_agent.collect.crawler import (
    Crawler,
    CrawlOptions,
    get_run,
    guess_doc_type,
    import_manual,
    looks_personal,
)
from doc_agent.collect.dedupe import normalize_url, page_text, safe_filename
from doc_agent.collect.http import HostThrottle, PoliteClient, ValidatorCache
from doc_agent.collect.sites import SITES_PATH, build_sites, load_sites
from doc_agent.config import Settings
from doc_agent.kaoyan.db import KaoyanStore

DATA = Path(__file__).resolve().parents[1] / "data" / "kaoyan"
RAW = DATA / "raw"
SITES = load_sites()

Route = tuple[int, bytes | str, dict[str, str]] | Callable[[httpx.Request], httpx.Response]


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class MockSite:
    """URL → (status, body, headers) or a callable; /robots.txt is 404 unless given."""

    def __init__(self, routes: dict[str, Route] | None = None, robots: str | None = None,
                 clock: FakeTime | None = None, robots_status: int = 404) -> None:
        self.routes: dict[str, Route] = dict(routes or {})
        self.robots = robots
        self.robots_status = robots_status
        self.clock = clock
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append({"method": request.method, "url": url, "headers": dict(request.headers),
                           "body": request.content, "t": self.clock.now if self.clock else None})
        if request.url.path == "/robots.txt":
            if self.robots is not None:
                return httpx.Response(200, text=self.robots)
            return httpx.Response(self.robots_status)
        route = self.routes.get(url)
        if route is None:
            return httpx.Response(404, text="not found")
        if callable(route):
            return route(request)
        status, body, headers = route
        content = body.encode("utf-8") if isinstance(body, str) else body
        return httpx.Response(status, content=content, headers=headers)

    def hits(self, url: str) -> int:
        return sum(1 for c in self.calls if c["url"] == url)


def make_client(site: MockSite, fake: FakeTime | None = None, **kw: Any) -> PoliteClient:
    fake = fake or site.clock or FakeTime()
    site.clock = fake
    return PoliteClient(
        user_agent="kaoyan-test/0.1 (+https://example.invalid)",
        transport=httpx.MockTransport(site),
        throttle=HostThrottle(3.0, clock=fake.clock, sleep=fake.sleep),
        backoff=1.0,
        **kw,
    )


def ok(body: str | bytes, **headers: str) -> Route:
    return (200, body, headers)


@pytest.fixture()
def store(kaoyan_store: KaoyanStore, tmp_path: Path) -> KaoyanStore:
    db = tmp_path / "kaoyan.db"
    shutil.copyfile(kaoyan_store.db_path, db)
    return KaoyanStore(db)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, llm_api_key="", kaoyan_data_dir=str(DATA),
                    crawl_cache_dir=str(tmp_path / "cache"), crawl_probe_ids=3, crawl_max_pages=20)


def crawler(store: KaoyanStore, settings: Settings, site: MockSite) -> Crawler:
    return Crawler(store, settings, client_factory=lambda: make_client(site))


# -- http: throttle / robots / retry / conditional GET / budget / login redirect ----


def test_same_host_serial_with_min_interval() -> None:
    fake = FakeTime()
    site = MockSite({u: ok("x") for u in ("https://a.edu.cn/1", "https://a.edu.cn/2", "https://b.edu.cn/1",
                                          "https://a.edu.cn/3")}, clock=fake)
    client = make_client(site, fake)
    for url in ("https://a.edu.cn/1", "https://a.edu.cn/2", "https://b.edu.cn/1", "https://a.edu.cn/3"):
        assert client.get(url).ok
    for host in ("a.edu.cn", "b.edu.cn"):
        times = [c["t"] for c in site.calls if f"//{host}/" in c["url"]]
        assert all(b - a >= 3.0 for a, b in pairwise(times)), (host, times)
    first_b = next(c["t"] for c in site.calls if "b.edu.cn" in c["url"])
    last_a_before = max(c["t"] for c in site.calls if "a.edu.cn/2" in c["url"])
    assert first_b == last_a_before  # another host is not delayed by a.edu.cn
    assert client.pages == 4  # robots.txt not counted


def test_robots_rules() -> None:
    site = MockSite({"https://a.edu.cn/public/1": ok("x"), "https://a.edu.cn/private/1": ok("x")},
                    robots="User-agent: *\nDisallow: /private/\n")
    client = make_client(site)
    assert client.get("https://a.edu.cn/public/1").ok
    res = client.get("https://a.edu.cn/private/1")
    assert res.skipped == "robots" and site.hits("https://a.edu.cn/private/1") == 0
    assert site.hits("https://a.edu.cn/robots.txt") == 1  # cached per host

    down = MockSite({"https://c.edu.cn/x": ok("x")}, robots_status=503)
    assert make_client(down).get("https://c.edu.cn/x").skipped == "robots"  # 5xx robots → disallow (RFC 9309)
    assert down.hits("https://c.edu.cn/robots.txt") == 2 and down.hits("https://c.edu.cn/x") == 0
    forbidden = MockSite({"https://f.edu.cn/x": ok("x")}, robots_status=403)
    assert make_client(forbidden).get("https://f.edu.cn/x").ok  # 4xx robots (WAF 403 on SYSU) → allow
    assert make_client(MockSite({"https://d.edu.cn/x": ok("x")}, robots_status=503),
                       respect_robots=False).get("https://d.edu.cn/x").ok


def test_retry_5xx_and_transport_errors_but_not_4xx() -> None:
    fake = FakeTime()
    statuses = iter([503, 502, 200])
    site = MockSite({
        "https://a.edu.cn/flaky": lambda r: httpx.Response(next(statuses), text="ok"),
        "https://a.edu.cn/gone": (404, "", {}),
        "https://a.edu.cn/down": (500, "", {}),
    }, clock=fake)
    client = make_client(site, fake)
    res = client.get("https://a.edu.cn/flaky")
    assert res.ok and res.attempts == 3 and {1.0, 2.0} <= set(fake.sleeps)
    gone = client.get("https://a.edu.cn/gone")
    assert gone.status == 404 and gone.attempts == 1 and site.hits("https://a.edu.cn/gone") == 1
    down = client.get("https://a.edu.cn/down")
    assert down.status == 500 and down.attempts == 3  # 1 + max_retries(2)

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    flaky = make_client(MockSite({"https://e.edu.cn/x": boom}), respect_robots=False)
    err = flaky.get("https://e.edu.cn/x")
    assert err.error.startswith("ConnectTimeout") and err.attempts == 3 and not err.ok


def test_conditional_get_and_validator_cache(tmp_path: Path) -> None:
    def page(request: httpx.Request) -> httpx.Response:
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, text="body", headers={"ETag": '"v1"', "Last-Modified": "Mon, 01 Jun 2026 00:00:00 GMT"})

    cache = ValidatorCache(tmp_path / "v.json")
    site = MockSite({"https://a.edu.cn/p": page})
    client = make_client(site, validators=cache)
    assert client.get("https://a.edu.cn/p", conditional=True).ok
    again = client.get("https://a.edu.cn/p", conditional=True)
    assert again.not_modified and again.status == 304 and not again.content
    assert site.calls[-1]["headers"]["if-none-match"] == '"v1"'
    plain = client.get("https://a.edu.cn/p")
    assert plain.ok and "if-none-match" not in site.calls[-1]["headers"]  # list pages: never conditional
    cache.save()
    assert ValidatorCache(tmp_path / "v.json").headers("https://a.edu.cn/p")["If-None-Match"] == '"v1"'


def test_page_budget() -> None:
    site = MockSite({f"https://a.edu.cn/{i}": ok("x") for i in range(5)})
    client = make_client(site, max_pages=2)
    results = [client.get(f"https://a.edu.cn/{i}") for i in range(3)]
    assert [r.ok for r in results] == [True, True, False] and results[2].skipped == "budget"
    assert site.hits("https://a.edu.cn/2") == 0 and client.budget_left == 0


def test_settings_cannot_go_below_three_seconds(tmp_path: Path) -> None:
    s = Settings(_env_file=None, llm_api_key="", crawl_min_interval_sec=0.5, crawl_cache_dir=str(tmp_path),
                 crawl_contact="me@example.org")
    client = PoliteClient.from_settings(s)
    assert client.throttle.min_interval == 3.0 and client.user_agent.endswith("(me@example.org)")
    client.close()


def test_scut_yanzhao_login_redirect_is_blocked_once() -> None:
    url = "https://yanzhao.scut.edu.cn/open/Master/Zsml_view.aspx"
    login = "https://yanzhao.scut.edu.cn/rump_frontend/login?service=x"
    site = MockSite({url: (302, "", {"Location": login}), login: ok("<form>login</form>")})
    client = make_client(site)
    adapter = build_adapter(SITES["scut"])
    (probe,) = adapter.probes(client, ProbeContext(None, [], []))
    assert probe.status == "blocked" and "rump_frontend/login" in probe.detail
    assert site.hits(url) == 1 and site.hits(login) == 0  # not retried, login page never requested
    again = client.get("https://yanzhao.scut.edu.cn/open/Master/Fsfa.aspx")
    assert again.skipped == "blocked_host" and again.blocked
    assert site.hits("https://yanzhao.scut.edu.cn/open/Master/Fsfa.aspx") == 0

    form = ('<html><title>华南理工大学硕士研究生招生专业目录</title><select name="ctl00$contentParent$drpNd">'
            '<option selected="selected" value="2027">2027</option></select></html>')
    (open_probe,) = adapter.probes(make_client(MockSite({url: ok(form)})), ProbeContext(None, [], []))
    assert open_probe.status == "new" and open_probe.found["years"] == [2027] and "2027" in open_probe.detail


# -- dedupe --------------------------------------------------------------------


def test_normalize_url() -> None:
    a = "http://YZ.scut.edu.cn:80/2026/0313/c30111a619995/page.htm#top"
    assert normalize_url(a) == normalize_url("https://yz.scut.edu.cn/2026/0313/c30111a619995/page.htm")
    assert normalize_url("https://a.edu.cn/list/") == normalize_url("https://a.edu.cn/list")
    encoded = "https://graduate.sysu.edu.cn/zsw/sites/default/files/2026-03/%E4%B8%AD%E5%B1%B1.pdf"
    assert normalize_url(encoded) == normalize_url("https://graduate.sysu.edu.cn/zsw/sites/default/files/2026-03/中山.pdf")
    assert normalize_url("https://a.edu.cn/x?page=1") != normalize_url("https://a.edu.cn/x?page=2")


def test_page_text_ignores_view_counters() -> None:
    a = "<html><body><h1>通知</h1><p>浏览次数：12</p><script>var t=1</script></body></html>"
    b = "<html><body><h1>通知</h1><p>浏览次数：345</p><script>var t=2</script></body></html>"
    assert page_text(a) == page_text(b) == "通知"
    assert safe_filename('a/b:c*?.pdf') == "a_b_c_.pdf"


SCUT_LIST = """
<ul class="news_list">
  <li><a href="/2026/0313/c30111a619995/page.htm" title="华南理工大学2026年硕士研究生复试初试成绩基本要求">华南理工大学2026年硕士…</a><span>2026-03-13</span></li>
  <li><a href="/2026/0313/c30108a619995/page.htm">华南理工大学2026年硕士研究生复试初试成绩基本要求</a></li>
  <li><a href="https://yz.scut.edu.cn/2026/0313/c30381a619995/page.htm">更多</a></li>
  <li><a href="/2026/0920/c30111a635999/page.htm">关于2027年硕士研究生招生章程的通知</a></li>
  <li><a href="/sszs/list2.htm">下一页</a></li>
</ul>"""


def test_scut_same_article_under_several_columns() -> None:
    adapter = build_adapter(SITES["scut"])
    docs = adapter.parse_list(SCUT_LIST, "https://yz.scut.edu.cn/sszs/list.htm")
    assert len(docs) == 2
    first = next(d for d in docs if d.key == "scut:a619995")
    assert first.title == "华南理工大学2026年硕士研究生复试初试成绩基本要求" and first.publish_date == "2026-03-13"
    mirror = "https://www2.scut.edu.cn/cs/_t2382/2026/0313/c45223a619995/page.psp"
    assert adapter.article_key(mirror) == "scut:a619995"
    assert adapter.page_url(SITES["scut"].lists[0], 3) == "https://yz.scut.edu.cn/sszs/list3.htm"


SYSU_LIST = """
<div class="view-content">
  <div class="views-row"><a href="/zsw/article/540">中山大学2027年推荐免试研究生招生录取工作办法</a>
    <span class="date">2026-09-10</span></div>
  <div class="views-row"><a href="/zsw/article/521">中山大学2026年硕士研究生招生考试复试基本分数线</a>
    <span class="date">2026/3/13</span></div>
</div>
<ul class="pager"><li><a href="https://graduate.sysu.edu.cn/?page=1" title="Go to next page">下一页 ›</a></li></ul>"""


def test_sysu_pager_fix_and_dates() -> None:
    adapter = build_adapter(SITES["sysu"])
    list_url = "https://graduate.sysu.edu.cn/zsw/postgraduate"
    docs = {d.key: d for d in adapter.parse_list(SYSU_LIST, list_url)}
    assert docs["sysu:graduate:540"].publish_date == "2026-09-10"
    assert docs["sysu:graduate:521"].publish_date == "2026-03-13"
    assert fix_page_url("https://graduate.sysu.edu.cn/?page=3") == list_url + "?page=3"
    assert adapter.page_url(SITES["sysu"].lists[0], 2) == list_url + "?page=1"
    assert adapter.next_page_url(SYSU_LIST.replace("下一页 ›", "next ›"), list_url) == list_url + "?page=1"
    no_template = ListSource(url=list_url)
    assert adapter.page_url(no_template, 2) is None


def test_sysu_article_id_probe() -> None:
    base = "https://graduate.sysu.edu.cn/zsw/article/"
    site = MockSite({base + "541": ok("<html><h1>中山大学2027年硕士研究生招生章程</h1></html>")})
    adapter = build_adapter(SITES["sysu"])
    ctx = ProbeContext(2026, [base + "540", "https://cse.sysu.edu.cn/article/3475"], [], probe_ids=3)
    results = adapter.probes(make_client(site), ctx)
    assert [r.status for r in results] == ["new"]
    assert results[0].found == {"id": 541, "title": "中山大学2027年硕士研究生招生章程"}
    assert site.hits(base + "542") == 1 and site.hits(base + "543") == 1
    empty = adapter.probes(make_client(MockSite()), ctx)
    assert [r.status for r in empty] == ["not_found"]


# -- SCNU WebForms / JNU year probe ---------------------------------------------


SCNU_P1 = RAW / "scnu" / "scnu_2026_招生专业目录_Zsml_View_019_p1.html"


def test_scnu_webforms_postback_and_paging() -> None:
    if not SCNU_P1.exists():
        pytest.skip("SCNU catalog fixture missing")
    form = SCNU_P1.read_text(encoding="utf-8")
    viewstate = webforms_state(form)["__VIEWSTATE"]
    pager = form.replace("</form>", "<a href=\"javascript:__doPostBack('ctl00$contentParent$dgData$ctl20$lnkPage2','')\">2</a></form>")
    posts: list[dict[str, str]] = []

    def catalog(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=form)
        data = dict(httpx.QueryParams(request.content.decode()))
        posts.append(data)
        return httpx.Response(200, text=pager if len(posts) == 1 else form)

    adapter = build_adapter(SITES["scnu"])
    assert isinstance(adapter, ScnuAdapter)
    site = MockSite({adapter.catalog_url: catalog})
    pages = adapter.fetch_catalog(make_client(site), "019")
    assert len(pages) == 2 and all(p.ok for p in pages)
    first, second = posts
    assert first["__EVENTTARGET"] == DRP_COLLEGE and first[DRP_COLLEGE] == "019"
    assert first["__VIEWSTATE"] == viewstate and first["__EVENTVALIDATION"] and first[DRP_YEAR] == "2026"
    assert second["__EVENTTARGET"] == "ctl00$contentParent$dgData$ctl20$lnkPage2" and second["__EVENTARGUMENT"] == ""


def test_scnu_year_dropdown_probe() -> None:
    if not SCNU_P1.exists():
        pytest.skip("SCNU catalog fixture missing")
    form = SCNU_P1.read_text(encoding="utf-8")
    adapter = build_adapter(SITES["scnu"])
    ctx = ProbeContext(2026, [], [])
    (same,) = adapter.probes(make_client(MockSite({adapter.catalog_url: ok(form)})), ctx)
    assert same.status == "unchanged" and same.found["years"] == [2026, 2025, 2024]
    newer = form.replace('<option selected="selected" value="2026">', '<option value="2027">2027</option><option selected="selected" value="2026">')
    assert newer != form
    (new,) = adapter.probes(make_client(MockSite({adapter.catalog_url: ok(newer)})), ctx)
    assert new.status == "new" and new.found["year"] == 2027


WEBPLUS_TWO_LINKS = """
<li class="list-S">
  <a class="tit" href="/2026/0910/c33059a862951/page.htm" title="暨南大学2027年推免生复试方案">暨南大学2027年推免生复试方案<span>2026-09-10</span></a>
  <div class="list"><a href="/2026/0910/c33059a862951/page.htm" title="暨南大学2027年推免生复试方案">
    <div class="time"><p class="month_day">09-10</p><p class="year">2026</p></div>
    <div class="list-right"><p class="title"> 暨南大学2027年推免生复试方案</p>
      <p class="content">001经济学院2027年推免生复试方案.pdf002产业经济研究院…</p></div></a></div>
</li>
<li class="list-S"><div class="list"><a href="/2026/0907/c33059a862686/page.htm">
    <div class="time"><p class="month_day">09-07</p><p class="year">2026</p></div>
    <div class="list-right"><p class="title">暨南大学关于做好2027年推免生复试录取工作的通知</p>
      <p class="content">各研究生招生单位：根据学校…</p></div></a></div></li>"""


def test_webplus_list_prefers_title_attribute() -> None:
    adapter = build_adapter(SITES["jnu"])
    docs = {d.key: d for d in adapter.parse_list(WEBPLUS_TWO_LINKS, "https://yz.jnu.edu.cn/tzgg/list.htm")}
    assert docs["jnu:a862951"].title == "暨南大学2027年推免生复试方案"
    assert docs["jnu:a862686"].title == "暨南大学关于做好2027年推免生复试录取工作的通知"  # inner .title, no summary
    assert docs["jnu:a862686"].publish_date == "2026-09-07"


def test_jnu_catalog_year_probe_and_skips() -> None:
    adapter = build_adapter(SITES["jnu"])
    url = "https://yz.jnu.edu.cn/2028nssyjszszyml/list.htm"
    (missing,) = adapter.probes(make_client(MockSite()), ProbeContext(2027, [], []))
    assert missing.status == "not_found" and missing.url == url
    page = "<html><head><title>2028年硕士研究生招生专业目录</title></head><body><table><tr><td>052</td></tr></table></body></html>"
    (online,) = adapter.probes(make_client(MockSite({url: ok(page)})), ProbeContext(2027, [], []))
    assert online.status == "new" and online.found["year"] == 2028
    assert adapter.skip("https://yz.jnu.edu.cn/33059/list.htm") and not adapter.skip("https://yz.jnu.edu.cn/tzgg/list.htm")


# -- crawler: dry run, registration, change detection, attachments ----------------


JNU_KNOWN = "https://yz.jnu.edu.cn/2026/0320/c33059a852118/page.htm"
JNU_NEW = "https://yz.jnu.edu.cn/2026/1005/c32995a870001/page.htm"
JNU_LIST = f"""
<ul class="wp_article_list">
  <li><a href="{JNU_KNOWN}">关于公布2026年各学院硕士生复试方案的通知</a></li>
  <li><a href="/2026/0320/c33003a852118/page.htm">关于公布2026年各学院硕士生复试方案的通知</a></li>
  <li><a href="{JNU_NEW}" title="暨南大学2027年硕士研究生招生简章">暨南大学2027年硕士研究生招生简章</a></li>
</ul>"""


def jnu_site(**extra: Route) -> MockSite:
    return MockSite({"https://yz.jnu.edu.cn/tzgg/list.htm": ok(JNU_LIST), **extra})


def test_probe_dry_run_writes_nothing(store: KaoyanStore, settings: Settings) -> None:
    before = store.count("documents")
    site = jnu_site()
    report = crawler(store, settings, site).run(CrawlOptions(schools=["jnu"]))
    rep = report["schools"]["jnu"]
    assert report["status"] == "done" and store.count("documents") == before
    assert rep["discovered"] == 2 and [d["url"] for d in rep["new"]] == [JNU_NEW]
    assert rep["known"][0]["doc_ids"][0] == "jnu-001"  # plus its xlsx attachments (same page_url)
    assert rep["new"][0]["doc_type"] == "brochure" and rep["new"][0]["intake_year"] == 2027
    assert {a["kind"] for a in rep["alerts"]} == {"new_brochure"}
    assert rep["probes"][0]["status"] == "not_found" and "2028" in rep["probes"][0]["url"]
    assert site.hits(JNU_NEW) == 0 and site.hits(JNU_KNOWN) == 0  # dry run: articles not fetched
    assert rep["requests"] == 2  # list page + year probe
    run = get_run(store, report["run_id"])
    assert run and run["status"] == "done" and run["dry_run"] is True and run["school_ids"] == ["jnu"]
    assert run["stats"]["totals"]["new"] == 1 and run["finished_at"]


def test_register_new_and_unchanged_by_sha256(store: KaoyanStore, settings: Settings) -> None:
    known_bytes = (RAW / "jnu" / "jnu_2026_各学院硕士复试方案_20260320.html").read_bytes()
    site = jnu_site(**{JNU_KNOWN: ok(known_bytes), JNU_NEW: ok("<html><h1>暨南大学2027年硕士研究生招生简章</h1></html>")})
    report = crawler(store, settings, site).run(CrawlOptions(schools=["jnu"], dry_run=False))
    rep = report["schools"]["jnu"]
    (reg,) = rep["registered"]
    doc = store.get_document(reg["doc_id"])
    assert doc and doc["page_url"] == JNU_NEW and doc["doc_type"] == "brochure" and doc["intake_year"] == 2027
    assert doc["sha256"] and Path(doc["local_path"]).exists() and doc["first_seen"] and not doc["contains_personal_data"]
    assert rep["unchanged"] == [{"url": JNU_KNOWN, "doc_id": "jnu-001", "by": "sha256"}]
    assert store.get_document("jnu-001")["last_seen"] != "2026-09-25"

    again = crawler(store, settings, site).run(CrawlOptions(schools=["jnu"], dry_run=False))["schools"]["jnu"]
    assert again["new"] == [] and again["registered"] == [] and len(again["unchanged"]) == 2


def test_change_detection_text_vs_new_version(store: KaoyanStore, settings: Settings) -> None:
    raw = (RAW / "jnu" / "jnu_2026_各学院硕士复试方案_20260320.html").read_text(encoding="utf-8")
    counter = raw.replace("</body>", "<span>浏览次数：999</span></body>")
    site = jnu_site(**{JNU_KNOWN: ok(counter)})
    rep = crawler(store, settings, site).run(CrawlOptions(schools=["jnu"], dry_run=False))
    unchanged = rep["schools"]["jnu"]["unchanged"]
    assert unchanged and unchanged[0]["by"] == "text"

    edited = raw.replace("</body>", "<p>补充通知：010 学院复试时间调整。</p></body>")
    site = jnu_site(**{JNU_KNOWN: ok(edited)})
    changed = crawler(store, settings, site).run(CrawlOptions(schools=["jnu"], dry_run=False))
    assert len(changed["schools"]["jnu"]["changed"]) == 1, changed["schools"]["jnu"]
    (item,) = changed["schools"]["jnu"]["changed"]
    assert item == {"url": JNU_KNOWN, "doc_id": "jnu-001-v2", "parent_doc_id": "jnu-001"}
    v2 = store.get_document("jnu-001-v2")
    assert v2 and v2["parent_doc_id"] == "jnu-001" and v2["doc_type"] == "retest_rules"
    assert store.get_document("jnu-001")["sha256"] != v2["sha256"]

    site = jnu_site(**{JNU_KNOWN: (410, "", {})})
    gone = crawler(store, settings, site).run(CrawlOptions(schools=["jnu"], dry_run=False))
    assert gone["schools"]["jnu"]["removed"][0]["doc_id"] == "jnu-001-v2"
    assert store.get_document("jnu-001-v2")["status"] == "removed"


SCUT_CS_HTML = RAW / "scut" / "scut_cs_2026_统考入围复试名单_20260316.html"


def test_full_mode_attachments(store: KaoyanStore, settings: Settings) -> None:
    if not SCUT_CS_HTML.exists():
        pytest.skip("SCUT cs fixture missing")
    article = "https://www2.scut.edu.cn/cs/2026/1010/c45223a640001/page.htm"
    extra = ('<a href="/_upload/article/files/aa/bb/new1.pdf">2027复试名单补充.pdf</a>'
             '<a href="/_upload/article/files/aa/bb/new2.pdf">2027复试名单补充（重复）.pdf</a>')
    html = SCUT_CS_HTML.read_text(encoding="utf-8").replace("</body>", extra + "</body>")
    listing = f'<li><a href="{article}">计算机学院2027年统考入围复试名单</a></li>'
    site = MockSite({
        "https://yz.scut.edu.cn/sszs/list.htm": ok(listing),
        "https://yz.scut.edu.cn/sszs_30381/list.htm": ok("<ul></ul>"),
        "https://yanzhao.scut.edu.cn/open/Master/Zsml_view.aspx": (302, "", {"Location": "/rump_frontend/login"}),
        article: ok(html),
        "https://www2.scut.edu.cn/_upload/article/files/aa/bb/new1.pdf": ok(b"%PDF-1.4 same"),
        "https://www2.scut.edu.cn/_upload/article/files/aa/bb/new2.pdf": ok(b"%PDF-1.4 same"),
    })
    report = crawler(store, settings, site).run(CrawlOptions(schools=["scut"], mode="full", dry_run=False))
    rep = report["schools"]["scut"]
    (reg,) = rep["registered"]
    assert store.get_document(reg["doc_id"])["contains_personal_data"] == 1
    status = {a["name"]: a["status"] for a in rep["attachments"]}
    assert status["2026学硕.pdf"] == status["2026专硕.pdf"] == "known"
    assert status["2027复试名单补充.pdf"] == "registered" and status["2027复试名单补充（重复）.pdf"] == "duplicate"
    new_att = next(a for a in rep["attachments"] if a["status"] == "registered")
    doc = store.get_document(new_att["doc_id"])
    assert doc["attachment_url"].endswith("new1.pdf") and doc["page_url"] == article
    assert doc["contains_personal_data"] == 1 and doc["format"] == "pdf"
    assert rep["blocked"] and rep["blocked"][0]["context"] == "catalog_access"
    assert site.hits("https://www2.scut.edu.cn/_upload/article/files/d2/d5/b0f6adff46f699eda84585c02dcc/"
                     "a538a047-379c-4717-809d-eff7e4b00c10.pdf") == 0  # known attachment not re-downloaded


def test_budget_stops_school(store: KaoyanStore, settings: Settings) -> None:
    site = jnu_site(**{JNU_NEW: ok("<h1>x</h1>"), JNU_KNOWN: ok("<h1>y</h1>")})
    rep = crawler(store, settings, site).run(CrawlOptions(schools=["jnu"], dry_run=False, max_pages=2))
    jnu = rep["schools"]["jnu"]
    assert jnu["budget_exhausted"] and jnu["requests"] == 2 and jnu["registered"] == []


def test_unknown_school_rejected(store: KaoyanStore, settings: Settings) -> None:
    with pytest.raises(ValueError):
        crawler(store, settings, MockSite()).run(CrawlOptions(schools=["pku"]))
    with pytest.raises(ValueError):
        CrawlOptions(schools=["jnu"], mode="deep")


def test_manual_import(store: KaoyanStore, settings: Settings, tmp_path: Path) -> None:
    f = tmp_path / "华工2026硕士专业目录.pdf"
    f.write_bytes(b"%PDF-1.4 manual")
    first = import_manual(store, f, school="scut", title="华南理工大学2026年硕士研究生招生专业目录", settings=settings,
                          url="https://yanzhao.scut.edu.cn/open/Master/Zsml_view.aspx")
    doc = store.get_document(first["doc_id"])
    assert first["status"] == "registered" and doc["doc_type"] == "catalog" and doc["intake_year"] == 2026
    assert doc["format"] == "pdf" and Path(doc["local_path"]).exists() and "手动导入" in doc["notes"]
    assert import_manual(store, f, school="scut", title="x", settings=settings)["status"] == "duplicate"
    with pytest.raises(ValueError):
        import_manual(store, f, school="pku", title="x", settings=settings)


def test_title_heuristics() -> None:
    assert guess_doc_type("华南理工大学2026年拟录取硕士名单公示") == "admission_list"
    assert guess_doc_type("2027年接收推荐免试研究生章程") == "brochure"
    assert guess_doc_type("2027年推免硕士招生专业目录") == "tm_catalog"
    assert guess_doc_type("关于2026年硕士复试基本分数线的通知") == "score_line"
    assert looks_personal("计算机学院2026统考复试拟录取名单公示") and not looks_personal("2026年硕士招生简章")


# -- sites.json / API ---------------------------------------------------------


def test_sites_json_in_sync_with_sources() -> None:
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    committed = json.loads(SITES_PATH.read_text(encoding="utf-8"))
    assert build_sites(sources, committed) == committed
    assert set(SITES) == {"sysu", "scut", "jnu", "scnu"}
    assert SITES["scut"].blocked_hosts == ("yanzhao.scut.edu.cn",)
    assert SITES["scnu"].lists[0].url.endswith("/tongzhigonggao/ssgg/")  # lists_override wins
    fresh = build_sites({"schools": [{"id": "pku", "name": "北京大学", "notice_list_pages": [{"url": "https://x/list.htm"}]}]})
    assert fresh["sites"][0]["adapter"] == "generic" and fresh["sites"][0]["lists"][0]["url"] == "https://x/list.htm"


@pytest.fixture()
def api(store: KaoyanStore, settings: Settings) -> TestClient:
    from doc_agent.api import create_app
    from doc_agent.api.routes_kaoyan import crawl_runner, kaoyan_query
    from doc_agent.kaoyan.query import KaoyanQuery

    app = create_app()
    app.dependency_overrides[kaoyan_query] = lambda: KaoyanQuery(store)
    app.dependency_overrides[crawl_runner] = lambda: (
        lambda st, opts, run_id: crawler(st, settings, jnu_site()).run(opts, run_id))
    return TestClient(app)


def test_crawl_api(api: TestClient) -> None:
    r = api.post("/v1/crawl", json={"schools": ["暨大"]})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued" and body["dry_run"] is True and body["school_ids"] == ["jnu"]
    done = api.get(f"/v1/crawl/{body['run_id']}").json()
    assert done["status"] == "done" and done["stats"]["totals"]["new"] == 1
    assert done["stats"]["schools"]["jnu"]["new"][0]["url"] == JNU_NEW

    bad = api.post("/v1/crawl", json={"schools": ["北大"]})
    assert bad.status_code == 404 and bad.json()["error"]["code"] == "school_not_found"
    invalid = api.post("/v1/crawl", json={"mode": "deep"})
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "validation_error"
    missing = api.get("/v1/crawl/nope")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "crawl_run_not_found"
