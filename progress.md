# 进度日志

## 会话：2026-10-08（M0 工程骨架，不调 LLM）

- **状态：** 代码在分支 `m0/skeleton`，未提交
- **计划：** `docs/kaoyan_improvement_plan.md`。本阶段记录：`docs/kaoyan_m0_notes.md`
- **做了：** `pyproject.toml`、MIT `LICENSE`、README 版权说明、CI（ruff + pytest）、评测集说明、18 题迁入 `data/gold/kaoyan_eval_v2.jsonl`（split=dev）、60 道模板候选 `data/gold/candidates_m0.jsonl`、`run_agent` 汇总 token
- **没做：** 不跑 `smoke_kaoyan.py`（18 题要花 DeepSeek）。`docs/baseline_2026-10.json` 不存在。2024–2025 复试线没有去官网逐份核对
- **验证：** `ruff check` 通过；`pytest -q` 253 passed（原 250 + 本阶段 3）

## 会话：2026-10-07（考研改造 K7：OCR / 视觉 + 前端 + 文档）

### K7
- **状态：** complete（待用户看 diff 摘要后提交）
- 新增 `ingest/ocr_table.py`（按线框还原表格、合并格展开）、`kaoyan/roster.py` + `scripts/roster_stats.py`（扫描名单只出每个专业代码的行数）、`kaoyan/extract/scut_baseline_img.py`、`scut_subjects_img.py`、`requirements-ocr.txt`、`frontend/kaoyan_view.py`、`frontend/components/programs_panel.py`、`tests/test_kaoyan_ocr.py`、`tests/test_frontend_kaoyan_view.py`、`docs/kaoyan_phase7_notes.md`
- 修改 `ingest/ocr.py`（rapidocr / vision / 缓存）、`loaders.py`（图片 OCR、扫描 PDF 页渲染 + OCR）、`pipeline.py`（名单文件强制不 OCR）、`config.py` + `.env.example`（`OCR_CACHE_DIR`、`VISION_*`）、`extract/run.py`（`extraction_method=ocr`）、`extract/evaluate.py`（未复现原因）、`sysu_retest_html.py`（也匹配图片）、两个脚本加 `--ocr`、`requirements*.txt` 显式写出 Pillow / pypdfium2、前端 `api_client.py` / `app.py` / `ingest_panel.py`、README、`data/README.md`
- `PYTHONPATH=src pytest -q`：250 passed（223 + 27；vision 用 MockTransport，rapidocr 真实识别在缺依赖 / 缺图片时 skip）
- 6 张图片 OCR（rapidocr，首次 6.5 s、缓存 0.2 s）：61 条事实，17 条与种子一致（`verified=1`），15 条种子没有（`verified=0`），29 条在 37 个专业以外，0 冲突；评估报告种子复现 363 → 380
- 本机 `data/kaoyan.db` 已用 `--ocr rapidocr` 重新抽取（写入 32 条 OCR 事实）；运行前备份 `/tmp/kaoyan_before_k7.db`
- 前端：本机起 API + Streamlit 检查“专业筛选”页（37 个专业、口径 / 来源链接、详情）和 18 条演示问句
- 未能真实验证：vision（`.env` 无 `VISION_*`）；scut-044 扫描名单本机没有（本地专用文件）

## 五问重启检查（K7）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K7 完成，等用户看 diff 摘要后提交；K0–K7 全部完成 |
| 我要去哪里？ | 可选：包改名（单独 PR，等用户决定）；配置多模态模型后对比 vision 与 rapidocr；下载 scut-044 后人工核对名单计数 |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 政府 / 高校通知里的表格图片线框规整，用“长墨迹 = 线”就能还原合并格，比让 OCR 猜表结构可靠；彩色表头是实心带，要把它的两条边当分隔线；OCR 与种子键不同（门类线 vs 按专业展开）时宁可不命中，也不替人展开口径 |
| 我做了什么？ | 两个 OCR 后端 + 缓存、表格还原、扫描页 OCR、名单计数、2 个图片抽取器、专业筛选页、4 个前端客户端方法、27 条新测试、README / data README / 阶段说明 |

## 会话：2026-10-07（考研改造 K6：采集层）

### K6
- **状态：** complete（已提交 `13dab2a`；补跑与正文指纹修复已提交 `6e11eac`）
- 新增 `collect/base.py`、`dedupe.py`、`http.py`（`PoliteClient`：按 host 串行 ≥3 s、robots、重试 / 退避、条件 GET、每校请求上限、登录跳转 → blocked）、`generic_list.py`、`adapters/{sysu,scut,jnu,scnu}.py`、`sites.py` + `sites.json`、`crawler.py`（运行编排、登记 / 版本 / 下架、附件、手动导入）、`scripts/crawl_kaoyan.py`
- 修改 `config.py`（`crawl_*`）、`.env.example`、`api/routes_kaoyan.py` + `schemas_kaoyan.py`（`POST /v1/crawl` → 202 + `run_id`，`GET /v1/crawl/{run_id}`）
- `PYTHONPATH=src pytest -q`：223 passed（196 + 27，全部 MockTransport，不联网）
- 文档：`docs/kaoyan_phase6_notes.md`

### 真实 probe（2026-10-07，本机网络，UA `kaoyan-info-agent/0.4`）
命令：`python scripts/crawl_kaoyan.py --mode probe [--no-dry-run]`，四校、每校列表第 1 页、同 host 间隔 ≥3 s、每校上限 20 次请求。

| 运行 | run_id | 请求 | 耗时 | 文章（新 / 已知） | 登记 | 未变化 | 提醒 | 错误 / blocked |
|------|--------|------|------|------------------|------|--------|------|----------------|
| dry-run（修复前） | `crawl_c58eb0ae290e` | 8 | 41.9 s | 中大被 robots 跳过、华师 404、暨南标题混摘要 | — | — | — | — |
| dry-run | `crawl_0a8a4af50229` | 11 | 42.4 s | 93（79 / 14） | 0 | 0 | 7 | 0 / 0 |
| 非 dry-run | `crawl_41795309a6f4` | 80 | 321.1 s | 93（79 / 14） | 67 | 2 | 7 | 0 / 0 |

非 dry-run 分校：

| 学校 | 请求 | 耗时 | 列表条目 | 新 / 已知 | 登记 | 未变化 | 探测 |
|------|------|------|----------|-----------|------|--------|------|
| 中大 | 20 | 61.2 s | 20 | 17 / 3 | 17 | 0 | 文章 ID 543 起无新文章 |
| 华工 | 20 | 58.7 s | 13 + 6（两个栏目） | 15 / 3 | 15 | 2（`scut-043`、`scut-051`，sha256 相同） | 目录系统可访问，年度下拉 2027 |
| 暨南 | 20 | 84.6 s | 23 | 20 / 3 | 18 | 0 | 2028 目录栏目 410（未发布） |
| 华师 | 20 | 116.5 s | 22 + 20（两个栏目） | 27 / 5 | 17 | 0 | 目录年份下拉出现 2027 |

- `documents` 97 → 164（全部 `active`）；新登记 4 篇按标题标为含个人信息（拟录取 / 递补复试名单、咨询人员名单），只存在被忽略的 `data/kaoyan/cache/`（本机 5.9 MB）
- 每校预算都用完：新文章先登记，暨南 2 篇、华师 10 篇未登记，中大 / 暨南 / 华师的已知文章未复查，下次运行补上
- 7 条提醒：中大 / 华工 2027 招生章程、华工 2 个联培项目 2027 简章（误报，可接受）、华工目录系统可访问、华师 2027 目录（文章 + 下拉）
- 运行前已备份本机库到 `/tmp/kaoyan_before_k6.db`；库文件、缓存不入 git

### 补跑非 dry-run（2026-10-07 10:50，`--max-pages 40`）
| run_id | 请求 | 耗时 | 新 / 已知 | 登记 | 未变化 | 变化 | 下架 | 错误 / blocked |
|--------|------|------|-----------|------|--------|------|------|----------------|
| `crawl_99061ce8e6ac` | 104 | 437.4 s | 12 / 81 | 12 | 76 | 5 → 0（误判，已清理） | 0 | 0 / 0 |

| 学校 | 请求 | 耗时 | 新 / 已知 | 登记 | 未变化 | 变化 |
|------|------|------|-----------|------|--------|------|
| 中大 | 23 | 70.4 s | 0 / 20 | 0 | 20 | 0 |
| 华工 | 21 | 61.7 s | 0 / 18 | 0 | 18 | 0 |
| 暨南 | 25 | 96.3 s | 2 / 21 | 2 | 21 | 0 |
| 华师 | 35 | 208.9 s | 10 / 22 | 10 | 17 | 5（误判） |

- 上次没登记的暨南 2 篇、华师 10 篇已登记；第一次登记的 67 篇在复查中全部判为未变化（sha256 / 304 / 正文指纹）
- 华师 5 篇种子文档（`scnu-021 / 028 / 029 / 030 / 033`）被判为“变化”：差异全在边栏（最新消息 / 本周图文 / 热门消息出现 9-28 新发的 2027 目录）和“上一篇 / 下一篇”，正文一字未改。修复：`sites.json` 加每校 `content_selector`，正文指纹只取正文文字 + 正文内链接 / 附件地址；离线用同样的字节复核 5 篇均判为未变化，删除误建的 5 条 `-v2` 记录和缓存文件，父文档 `last_seen` 更新为本次时间
- `documents` 164 → 176，全部 `active`、无版本记录；已知文章全部复查完毕。运行前备份 `/tmp/kaoyan_before_k6_run2.db`

## 五问重启检查（K6）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K6 完成，等用户看 diff 摘要后提交 |
| 我要去哪里？ | K7：OCR / 视觉（rapidocr + 多模态）、专业筛选前端页、README / docs 更新 |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 真实站点和种子记录会漂移：robots.txt 被 WAF 拦、栏目改版 404、原来被统一认证拦的目录系统现在能访问；所以必须先 dry-run 看结果再落库，并让 `sites.json` 能覆盖种子 |
| 我做了什么？ | 礼貌 HTTP 客户端、4 个站点适配器、变化检测与版本、crawl API / CLI、27 条新测试、三次真实 probe（含补跑） |

## 会话：2026-09-29（考研改造 K5：Agent 工具、提示词、API）

### K5
- **状态：** complete（已提交 `a1c5ee7`）
- 新增 `kaoyan/query.py`（查询服务：筛选、统招取值、复试线口径、科目、对比表行、文档元数据）、`tools/kaoyan.py`（6 个结构化工具 + citation / 导出行 / LLM 视图）、`agent/kaoyan_flow.py`（按意图确定性调工具、reflect、finalize 数字校验）、`api/routes_kaoyan.py` + `schemas_kaoyan.py`（`/v1/programs`、`/v1/programs/{id}`、`/v1/score-lines`、`/v1/documents`、`/v1/documents/{id}`）、`scripts/smoke_kaoyan.py`
- 修改 `guardrails.py`（考研意图识别、数字校验）、`prompts.py`（考研 15 条规则）、`nodes.py`（按意图分流，企业路径不变）、`state.py` / `graph.py`（`intent`、`facts`）、`registry.py`（注册工具，`rag_search` 加 `profile`）、`/health` 加可选字段、`__version__` 0.4.0 并用于 `create_app()`
- `PYTHONPATH=src pytest -q`：196 passed（139 + 57）；`test_api_errors.py` 未改
- 真实 DeepSeek 冒烟 `smoke_kaoyan.py`：18/18（数值 14/14、未知 2/2、隐私 1/1、导出 1/1、引用 18/18）；企业 `smoke_chat.py` 3/3
- 文档：`docs/kaoyan_phase5_notes.md`

## 五问重启检查（K5）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K5 完成，等用户看 diff 摘要后提交 |
| 我要去哪里？ | K6：采集层（`collect/`、按 host 限速 ≥3s、robots、`POST /v1/crawl` 默认 dry-run），全部用 MockTransport 测试 |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 工具调用交给规则后，模型失误集中在措辞：会主动讲没问的缺口、用有歧义的“考 408”；数字校验要豁免学科代码这类“看起来像数字”的标识 |
| 我做了什么？ | 查询服务、6 个工具、意图识别、数字校验、考研提示词、Agent 分流、5 个接口、57 条新测试、真实冒烟 18/18 |

## 会话：2026-09-28（考研改造 K4：结构化抽取）

### K4
- **状态：** complete（已提交 `d933603`）
- 新增 `kaoyan/extract/`：10 个规则抽取器（中大细则 / 校线 / 目录 PDF、暨南目录 / 复试方案 xlsx / 推免 PDF、华师目录 / 推免 xls / 复试方案、华工计划）、`apply.py`（专业解析 + 与种子逐键比对 + 幂等写库）、`run.py`、`llm_fallback.py`（证据片段必须在原文中）、`evaluate.py`
- 脚本 `scripts/extract_kaoyan.py`、`scripts/eval_extraction.py` → `docs/kaoyan_extraction_report.md`
- 四类验收逐值一致、冲突 0；450 条种子复现 363 条，其余为名单统计 / 图片 / 种子判断；504 条规则事实全部带来源和证据；本机 `data/kaoyan.db` 已抽取
- `PYTHONPATH=src pytest -q`：139 passed（113 + 26）
- 文档：`docs/kaoyan_phase4_notes.md`

## 五问重启检查（K4）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K4 完成并已提交（`d933603`） |
| 我要去哪里？ | K5：考研结构化工具（search_programs / get_score_lines / …）、考研提示词与数字校验、`/v1/programs` 等接口 |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 真实表格的特殊行靠备注 / 括号说明区分，且备注常在双层表头的另一行；跳过考生表要看表头，不能看数据行 |
| 我做了什么？ | 抽取协议、10 个规则抽取器、比对写库、LLM 证据校验、评估报告、26 条新测试 |

## 会话：2026-09-28（考研改造 K3：检索元数据 + 考研索引）

### K3
- **状态：** complete（已提交 `0aa958f`）
- chunk 带 doc_id / school / college / year / doc_type / title / url / redacted；表格按行切块，重复标题 + 表头 + 学院 / 专业行
- 独立考研索引 `data/chroma_kaoyan/`（`scripts/ingest_kaoyan.py`）：90 文档、1926 chunk、hybrid；检索可按学校 / 年份 / 类型过滤，问题里只有一所学校时自动过滤
- 考研排序先验（名单降权、文档类型 / 学院匹配）；golden hit@5：BM25 16/18、hybrid 15/18
- 企业语料：chunks 逐字节相同、检索结果与工具输出一致、`smoke_chat.py` 3/3
- `PYTHONPATH=src pytest -q`：113 passed（100 + 13）
- 文档：`docs/kaoyan_phase3_notes.md`

## 五问重启检查（K3）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K3 完成，等用户看 diff 摘要后提交 |
| 我要去哪里？ | K4：规则抽取器（暨南目录、华师目录 / 推免 xls、中大细则 / 校线）+ LLM 兜底，与种子逐条比对 |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 名单类文档在词频检索里天然占优，必须用元数据先验压下去；先验只在候选池里生效，池子要够大 |
| 我做了什么？ | chunk 元数据、按行切表、考研索引与过滤、查询扩展与先验、单元格级脱敏、13 条新测试 |

## 会话：2026-09-28（考研改造 K2：多格式解析层）

### K2
- **状态：** complete（已提交 `f6ea30f`）
- 新增 `ingest/{tables,ocr,redact}.py`、`kaoyan/privacy.py`、`collect/attachments.py`；`loaders.py` 支持 html / xlsx / xls / 图片与 PDF 抽表，`ParsedDocument` 带表格 / 图片 / `needs_ocr`
- 个人信息：名单文件在 `load_document` 里脱敏（姓+某、删编号列）；泄漏扫描发现并修复公示正文“拟录取X等N人”首名
- 临时库 ingest `data/kaoyan/raw`：96 文件，90 indexed / 0 failed / 7 needs_ocr / 26 redacted；4187 个姓名 0 泄漏
- `PYTHONPATH=src pytest -q`：100 passed（70 + 30）
- 文档：`docs/kaoyan_phase2_notes.md`

## 五问重启检查（K2）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K2 完成，等用户看 diff 摘要后提交 |
| 我要去哪里？ | K3：chunk 元数据（school / year / doc_type）、独立考研索引、表格按行切块 |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 名单以外的公示正文也会带姓名；泄漏扫描要扫全库而不是只扫名单文件 |
| 我做了什么？ | 多格式解析 + 表格模型、附件发现、OCR 接口、脱敏与统一入口、30 条新测试 |

## 会话：2026-09-27（考研改造 K1：种子库 + golden）

### K1
- **状态：** complete（已提交 `125b5a0`）
- 新增 `src/doc_agent/kaoyan/`（schema / db / models / normalize / seed）、`scripts/seed_kaoyan.py`、`scripts/verify_kaoyan_bundle.py`、`data/gold/kaoyan_qa.json`（18 条）、两组测试
- 联网下载中大 2026 目录 PDF（5.2MB，sha256 与 manifest 一致，本地专用不入库）；verify：96 ok / 1 missing(warn) / 0 bad
- 种子：37 专业、97 文档、`seed_only` 0；K1 七组断言全部通过；幂等
- `PYTHONPATH=src pytest -q`：70 passed（21 + 49）
- 文档：`docs/kaoyan_phase1_notes.md`

## 五问重启检查（K1）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K1 完成，等用户看 diff 摘要后提交 |
| 我要去哪里？ | K2：多格式解析层（html / xlsx / xls / 图片 / 扫描 PDF 识别、附件发现） |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 页面级 URL 对应多个文档，来源要按事实类型打分；一级学科统筹值要带 `pool_scope`，统计表也一样 |
| 我做了什么？ | 建结构化库与种子、备注窄正则（含真实字符串单测）、golden 18 条、包校验脚本 |

## 会话：2026-09-27（考研改造 K0：阅读 + 基线 + 计划）

### K0
- **状态：** in_progress（计划已写，等待用户确认）
- 种子包 `kaoyan_bundle_lite.zip` 解压到 `data/kaoyan/`；`git status` 80 个未跟踪文件，28 条忽略规则生效
- 基线 `PYTHONPATH=src pytest -q`：21 passed
- manifest：95/97 sha256 一致，缺 2 个 >3MB 本地专用文件（lite 包不含）
- 阶段 6 前端按代码核对：F1–F3 已完成，F4 未做；已更正 task_plan
- 计划：`task_plan.md` 阶段 K0–K7

## 五问重启检查（K0）
| 问题 | 答案 |
|------|------|
| 我在哪里？ | K0 完成计划，等用户确认 |
| 我要去哪里？ | 确认后执行 K1（种子库 + golden） |
| 目标是什么？ | 考研信息 Agent：每个数字带来源 / 年份 / 口径，不知道就说不知道 |
| 我学到了什么？ | 备注写法比需求里列的多（暨南 2026 统招计划、拟录取人数等），K1 正则要覆盖 |
| 我做了什么？ | 通读仓库与种子包、跑基线、写 K0–K7 计划 |

## 会话：2026-09-06（终测 + 前端计划）

### 后端终测
- **状态：** complete / 可发布
- pytest 13；phase4 smoke OK；async done；人工 P0–P4 通过
- 修复 smoke_chat 空格判分；结论见 `docs/final_backend_test.md`

### 阶段 6：前端
- **状态：** pending（计划已写）
- 文档：`docs/frontend_implementation_plan.md`

### 阶段 5
- **状态：** complete

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | 后端已终测可推送；前端计划已就绪 |
| 我要去哪里？ | 推送 GitHub 后实施 F1 |
| 目标是什么？ | Streamlit 可视化全流程 |
| 我学到了什么？ | 冒烟判分需归一化中文空格 |
| 我做了什么？ | 终测 + 前端计划 |

---
*每个阶段完成后或遇到错误时更新此文件*
