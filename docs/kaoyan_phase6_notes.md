# 考研改造 K6：采集层说明

- **日期：** 2026-10-07
- **分支：** `feat/kaoyan`
- **版本：** `0.4.0`
- **范围：** 礼貌地抓取四校研招官网（列表页 → 文章 → 附件），发现新文档并登记到 `kaoyan.db.documents`，已有文档按 sha256 / 正文判断是否变化；站点探测提示新年份的目录 / 章程。测试全部用 `httpx.MockTransport`，不联网

## 交付项

| 能力 | 实现 |
|------|------|
| 礼貌 HTTP | `collect/http.py` `PoliteClient`：UA + 联系方式（`CRAWL_CONTACT`）；同 host 串行、间隔 ≥3 s（`HostThrottle`，进程内共享；配置低于 3 s 时强制 3 s）；robots.txt 按 RFC 9309（4xx 视为全部允许，5xx / 网络错误视为全部禁止）；5xx / 传输错误最多重试 2 次、指数退避，4xx 不重试；手动跟随重定向，跳到登录 / 统一认证路径时把该 host 标 `blocked`，之后不再请求；复查时用 ETag / If-Modified-Since（`cache/http_validators.json`）；每校请求上限（robots.txt 不计） |
| 规范化 / 去重 | `collect/dedupe.py`：URL 规范化（https、小写 host、去默认端口 / 片段 / 末尾斜杠）、sha256、正文指纹（只取 `content_selector` 内的文字 + 链接 / 附件地址，去脚本和浏览计数；取不到时用整页文字） |
| 列表解析 | `collect/generic_list.py`：按 `sites.json` 的文章 URL 正则识别条目，生成文章 key；发布日期取 URL（`/YYYY/MMDD/`、`/a/YYYYMMDD/`）或链接附近文字；标题按 `title` 属性 > 内层 `.title` > 链接文字取；“下一页”链接或分页模板翻页 |
| 站点适配器 | `collect/adapters/`：中大（分页 URL 修正、文章 ID 递增探测）、华工（多栏目 `a{ID}` 去重、目录系统可访问性 + 年度下拉）、暨南（只爬 `/tzgg/` 主列表，跳过空栏目 `/33003/`、`/32993/` 和已 410 的 `/33059/`；探测下一年目录栏目）、华师（WebForms `__VIEWSTATE` 回发、目录年份下拉、full 模式按学院抓目录分页） |
| 站点配置 | `collect/sites.json` 由 `sources.json.schools[]` 生成（`collect/sites.py`），规则键 `adapter / lists_override / article_patterns / skip_url_patterns / content_selector / probe` 在重新生成时保留；`--sync-sites` 重新生成 |
| 运行编排 | `collect/crawler.py` `Crawler.run()`：写 `crawl_runs`（mode、学校、状态、统计）；逐校：列表 → 探测 → （非 dry-run）登记新文章 → 复查已知文章 → （full）附件 / 华师目录 |
| 登记 / 变化 | 新文章存到 `data/kaoyan/cache/<school>/<sha12>_<标题>`，id `{school}-w{sha1(key)[:8]}`，按标题猜 doc_type / 招生年份 / 是否含个人信息，标题先过 `redact_text`；复查：304 → 未变化，sha256 相同 → 未变化，正文指纹相同 → 未变化（只刷新 `last_seen`），否则登记新版本 `{id}-v{n}`（`parent_doc_id` 指向上一版）；404 / 410 → `removed`；被拦 → `blocked` |
| 提醒 | 标题出现比库里最新简章 / 目录更新的年份（推免类跳过）；探测结果为 `new` |
| 手动导入 | `import_manual()` / `crawl_kaoyan.py --import FILE --school … --title …`：复制到 cache，id `{school}-m{sha256[:8]}`；华工被拦时走这条 |
| API | `POST /v1/crawl`（202，返回 `run_id`，后台执行）；`GET /v1/crawl/{run_id}`；错误信封 `school_not_found` / `crawl_site_not_configured` / `crawl_run_not_found` / 422 |
| CLI | `scripts/crawl_kaoyan.py --school jnu --mode probe [--no-dry-run] [--max-pages N] [--list-pages N] [--json]` |
| 配置 | `CRAWL_USER_AGENT`、`CRAWL_CONTACT`、`CRAWL_MIN_INTERVAL_SEC`、`CRAWL_RESPECT_ROBOTS`、`CRAWL_TIMEOUT`、`CRAWL_MAX_RETRIES`、`CRAWL_BACKOFF_SEC`、`CRAWL_MAX_PAGES`、`CRAWL_PROBE_IDS`、`CRAWL_CACHE_DIR`（见 `.env.example`） |

## 模式

| mode | 列表 | 探测 | 文章 | 附件 / 华师目录 |
|------|------|------|------|----------------|
| `probe` | 每个列表第 1 页 | 是 | 非 dry-run 时登记 / 复查 | 否 |
| `list` | 每个列表最多 `list_pages` 页（默认 3） | 是 | 同上 | 否 |
| `full` | 同 `list` | 是 | 同上 | 是 |

`dry_run=true`（默认）只请求列表页和探测 URL，不写 `documents`，`crawl_runs` 照常记录。

## 约束落实

- **礼貌抓取：** 同 host ≥3 s 且串行；遵守 robots；每校请求上限；不绕过登录 / 验证码（302 到 `/rump_frontend/login` 等 → `blocked`，走手动导入）；研招网签名接口不抓。
- **个人信息：** 名单类标题（名单 / 名册 / 复试结果 / 录取结果 / 成绩公示 / 拟录取公示）标 `contains_personal_data=1`，原文只存在被忽略的 `cache/`；登记标题经过脱敏；CLI / 日志只输出标题和统计。
- **不入库：** `data/kaoyan.db`、`data/kaoyan/cache/`（含下载文件和条件请求缓存）都被 `.gitignore` 忽略。

## 验收结果

### 单元测试

`PYTHONPATH=src pytest -q`：**223 passed**（196 + 27）。新增 `tests/test_kaoyan_collect.py` 覆盖：限速与串行、robots 规则、重试 / 不重试、条件 GET、请求上限与 3 s 下限、华工 302 → blocked 且只请求一次 / 可访问时读年度下拉、URL 规范化、浏览计数忽略、正文指纹忽略边栏 / 上一篇下一篇但能发现 PDF 替换、华工多栏目去重、中大分页与日期、中大 ID 探测、华师 WebForms 回发与分页、华师年份下拉、WebPlus 双链接标题、暨南年份探测与跳过栏目、dry-run 不写库、登记与 sha256 未变化、正文未变 / 新版本 / 410 下架、full 模式附件（同 sha 去重）、预算用尽、未知学校、手动导入、标题规则、`sites.json` 与 `sources.json` 同步、crawl API。

### 真实 probe（2026-10-07）

| 运行 | 请求 | 耗时 | 文章（新 / 已知） | 登记 | 未变化 | 提醒 | 错误 / blocked |
|------|------|------|------------------|------|--------|------|----------------|
| dry-run | 11 | 42.4 s | 93（79 / 14） | 0 | 0 | 7 | 0 / 0 |
| 非 dry-run | 80 | 321.1 s | 93（79 / 14） | 67 | 2 | 7 | 0 / 0 |
| 补跑非 dry-run（每校上限 40） | 104 | 437.4 s | 93（12 / 81） | 12 | 76 | 3 | 0 / 0 |

- 第一次非 dry-run：`documents` 97 → 164；华工 `scut-043`、`scut-051` 复查时 sha256 相同 → 未变化。每校 20 次请求用完，暨南 2 篇、华师 10 篇未登记，其余已知文章未复查。
- 补跑：12 篇全部登记（→ 176）；第一次登记的 67 篇复查全部未变化。华师 5 篇种子文档因边栏 / 上一篇下一篇不同被误判为变化，加 `content_selector` 后离线复核均为未变化，误建的版本记录已删除。
- 首轮 dry-run 暴露的三个问题已修复：中大 robots.txt WAF 403、华师栏目改版 404（`lists_override`）、暨南标题混入摘要。分校明细见 `progress.md`，站点事实见 `findings.md`。

## 说明

- 按标题猜的 doc_type / 年份只用于排序和提醒，新登记文档未做抽取（K4 抽取器按 doc_id 绑定），也未进考研索引；需要时运行 `scripts/ingest_kaoyan.py` / `extract_kaoyan.py`。
- 华工目录系统本次可直接访问，但 `sources.json` 仍记为 blocked；适配器每次探测都会如实报告，不改种子。
- 标题提醒会把联培项目的“2027 年招生简章”也报出来，属于可接受的误报。
