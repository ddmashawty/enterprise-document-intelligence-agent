# 任务计划：企业文档智能处理 Agent → 考研（硕士研招）信息 Agent

## 目标
- 阶段 1–6（已完成）：本地文档 ingest → Chroma RAG → LangGraph Agent（规划/工具/反思）→ FastAPI + Streamlit，支撑年报对比、制度问答、参数抽取等演示场景。
- 阶段 K0–K7（本轮）：保留上述骨架，改造成面向硕士研招信息的 Agent：采集（礼貌爬取 + 变化检测）→ 多格式解析 → 结构化抽取入 `data/kaoyan.db`（每个数值带来源文档 / 页码 / 年份 / 口径）→ 按条件筛选、查复试线、对比、导出；每个数字有出处，不知道就说不知道。首批：中大 / 华工 / 暨南 / 华师泛计算机（种子包 `data/kaoyan/`）。企业演示作为“通用文档模式”保留。
- 需求原文：`data/kaoyan/CURSOR_PROMPT.md`；数据说明：`data/kaoyan/README.md`。

## 当前阶段
K0–K7 已完成，`feat/kaoyan` 已合并进 `main`（`98a809c`）。后续按 `docs/kaoyan_improvement_plan.md` 做，执行记录写在 `docs/kaoyan_m0_notes.md` 起的阶段说明里，不再另起一套计划。

M0（2026-10-08，分支 `m0/skeleton`，未提交）：工程骨架、评测集 v2 的 18 题迁移、60 道未核对候选题。旧 18 题的 LLM 基线故意没跑。P1 评测脚本还没开始。

## 各阶段

### 阶段 1：需求与发现
- [x] 阅读 PRD，确认后端范围（不含 Streamlit 优先）
- [x] 确认演示数据已就绪（`data/raw`）
- [x] 将架构/数据源/风险记录到 findings.md
- **状态：** complete

### 阶段 2：规划与结构（后端方案）
- [x] 确定后端分层与目录结构
- [x] 确定 LangGraph 状态机与工具集
- [x] 确定 FastAPI 接口契约与配置模型
- [x] 确定一期/二期/三期后端交付切分
- [x] 用户确认方案后进入实现
- **状态：** complete

### 阶段 3：一期后端 MVP 实现
- [x] 项目初始化（requirements、配置、包结构、.venv py3.12）
- [x] 文档解析 + ingest（PDF+txt → 切片 → 本地 Ollama `qwen3-embedding:0.6b` + Chroma；未配置时回退 BM25）
- [x] RAG 检索工具 + 基础问答链路
- [x] LangGraph 最小图：plan → route → act → finalize
- [x] FastAPI：`/health`、`/ingest`、`/chat`（同步）
- [x] 用 `data/gold/sample_qa.json` 冒烟（3/3）
- [x] 人工验证清单（见 `docs/backend_verification_result.md`）
- [x] 年报召回优化（hybrid + 查询扩展），3.2 复测通过
- **状态：** complete

### 阶段 4：二期后端能力完善
- [x] 双层记忆（会话短期 + SQLite 任务轨迹）
- [x] 结构化输出工具（Markdown / Excel）
- [x] 反思校验节点 + 工具重试（max 5）
- [x] 多文档对比/汇总工具
- **状态：** complete

### 阶段 5：三期工程化与交付
- [x] FastAPI 完善（任务异步、轨迹查询、错误模型）
- [x] 单元/集成测试、性能基线核对
- [x] README、环境变量示例、可复现演示脚本
- [x] （可选）Streamlit 另开前端阶段 — **已拆到阶段 6**
- **状态：** complete

### 阶段 6：Streamlit 前端（可视化）
- [x] F1 骨架联通（health + 同步 chat）— `frontend/app.py`、`frontend/api_client.py`
- [x] F2 全流程可视化（trace/异步/任务中心）— `components/chat_panel.py`、`trace_panel.py`、`tasks_panel.py`
- [x] F3 Ingest + 演示剧本 + 验证清单 — `components/ingest_panel.py`、`DEMO_QUESTIONS`、`docs/frontend_verification_checklist.md`
- [ ] （可选）F4 文档列表 API / 导出下载 — 未做（trace 面板只显示导出路径，无下载；无文档列表接口）
- **状态：** complete（代码，见提交 `a14f23d`、`7a439fb`）；`tests/test_frontend_client.py` 4 条通过；**人工验收结果未落文档**（有 checklist，无 result）
- **计划文档：** `docs/frontend_implementation_plan.md`
- **说明：** 2026-09-27 按代码核对后更正（原状态 pending 已过时）

### 阶段 K0：考研改造 — 阅读、基线、计划（不写代码）
- [x] 通读仓库文档、`src/doc_agent/` 全部模块、`tests/`、`scripts/`、`frontend/`
- [x] 通读种子包：`data/kaoyan/README.md`、`sources.md`、`sources.json`（schools 4 / documents 97）、`majors.csv`（37 行）、`raw/manifest.csv`
- [x] 基线：`PYTHONPATH=src pytest -q` → **21 passed**（旧文档写 13，之后新增了 docx/frontend 测试）
- [x] 种子包复制到 `data/kaoyan/`；`git status` 只出现 80 个未跟踪文件（11 个包文件 + 69 个 raw），28 条忽略规则生效
- [x] manifest 校验：97 条中 95 个本地存在且 sha256 一致；缺 2 个 >3MB 文件（`scut_2026_拟录取硕士名单_不含推免.pdf`、`sysu_2026_硕士招生学科专业目录.pdf`，lite 包本就不含）
- [x] `majors.csv` 来源 URL 按 ` ; ` 切分 + 去括号说明后，全部能精确匹配 `sources.json` 的 `page_url/attachment_url`
- [x] 写出 K0–K7 计划（本文件）
- [x] 用户确认计划（2026-09-27）
- **状态：** complete

### 阶段 K1：种子库 + golden（不联网、不调 LLM）
- **新增：** `src/doc_agent/kaoyan/{__init__.py, schema.sql, db.py, models.py, normalize.py, seed.py}`、`scripts/seed_kaoyan.py`、`scripts/verify_kaoyan_bundle.py`、`data/gold/kaoyan_qa.json`（第 6 节 18 条）、`tests/test_kaoyan_normalize.py`、`tests/test_kaoyan_seed.py`
- **修改：** `config.py`（`kaoyan_db`、`kaoyan_data_dir`，其余 K 阶段配置在用到时再加）、`.env.example`、`data/README.md`（指向 `data/kaoyan/README.md`）、`requirements-embedding.txt`（补齐已漂移的 `python-docx`、`openpyxl`）
- **做法：**
  - `schema.sql`：`schools / colleges / documents / programs / directions / exam_subjects / plans / score_lines / admission_stats / crawl_runs` + 视图 `v_program_facts`；每条事实带 `source_doc_id, page, year, definition, evidence_text, extraction_method, verified`
  - `KaoyanStore`：sqlite3 + `threading.Lock`（仿 `memory.TaskStore`），`init_schema()`、upsert、查询；种子幂等（先删 `extraction_method in (manual_seed, seed_note_regex)` 的事实再重写，或按自然键 upsert）
  - `normalize.py`：`48(17)`、`同上`、`≤41`、`（0812合计≤19）`、科目串拆分（①②③④ / 换行 / 空格；“408…基础综合”≡408）、格内换行的专业代码、单科线（`政治50/外语50/业务课一60/业务课二60`、`业务一53/业务二53`、`业务课70/70（学校基本线）`）、学校别名
  - `seed.py`：列 → 事实映射按 CURSOR_PROMPT 第 4 节；推免数默认口径（中大 = 学院细则已招推免 / 华师 = 目录“总(推免)” / 暨南 = 2027 推免复试方案）写入 `definition`
  - 备注窄正则：已把 37 行备注全过一遍，在 CURSOR_PROMPT 列出的变体之外还需覆盖（每个变体都配真实字符串单测）：
    - 细则计划：`学院细则：总8/已招推免7/公开1`、`学院细则：总15/推免15/公开0`
    - 专项：`另退役大学生计划1名（线335）`、`少数民族骨干1名，线270（40/40/55/55）`、`另退役3；退役线288（…）`
    - 华师：`复试方案中计划为54（推免5）`（无“含联培”）、`拟招22/已招推免1`、`拟招20/推免0`
    - 华工：`统考计划18，另有中法南特联培项目5`、`统考可用计划10（学校2025-10-22 PDF）`、`统考可用计划21。`
    - 暨南 2026 口径（用例 7、15 需要）：`2026：目录53；统招计划29，复试58人，1:2.00` → `plans(year=2026, catalog_total / public_exam)` + `admission_stats(retest_count)`；`2026目录中分专业计划：081201 5、081202 3、081203 6、0812Z3 10`
    - 人数统计（用例 17 需要，只存统计）：`统考拟录取36人`、`统考拟录取23人（含南特5）`、`复试名单56人（339–416）` → `admission_stats`
- **验收：** 37 个 program；`documents` 97 条且无 `seed_only`；CURSOR_PROMPT K1 列出的 7 组断言全部成立（中大 670 085404 线 379 且来源 `cse.sysu.edu.cn/article/3475`；暨大 052 085412 348 / 2027 目录 62 / 推免 25；华师 019 085404 348 + 退役 288；华工 085404 科目 unknown、校线 305、`college_exam_plan` 35 与 `available_exam` 21 并存；暨大 010 0812 四个二级学科 `catalog_total` 空、`tm` 为一级学科合计上限 19；中大 757 083900 `no_exam`）；`verify_kaoyan_bundle.py` 输出 96 ok / 1 missing(warn) / 0 bad（中大 2026 目录 PDF 已联网下载并校验 sha256）
- **测试：** `test_kaoyan_normalize.py`、`test_kaoyan_seed.py`（种子写到 `tmp_path`，不碰 `data/kaoyan.db`）；旧 21 条不变
- **结果：** 70 passed（21 + 49）；种子 4 校 / 16 学院 / 97 文档 / 37 专业 / 144 plans / 49 score_lines / 60 admission_stats，`seed_only` 0，二次种子计数不变。“0812 `catalog_total` 空”按 **2027 无专业级数值** 落实（2027 只有 `pool_scope='0812'` 合计 24；2026 分专业计划按 2026 年保存，golden #7 允许补充）。详见 `docs/kaoyan_phase1_notes.md`
- **状态：** complete

### 阶段 K2：多格式解析层
- **新增：** `src/doc_agent/ingest/tables.py`（`Table`：cells、合并单元格展开、page、bbox；HTML / PDF / xlsx / xls 抽表）、`src/doc_agent/ingest/ocr.py`（`OCRBackend` 接口，本阶段只实现 `none`）、`src/doc_agent/collect/__init__.py`、`src/doc_agent/collect/attachments.py`（`<a href>`、`div[pdfsrc]`+`sudyfile-attr`、`<img src>`、data URI、相对路径）、`tests/test_kaoyan_tables.py`、`tests/test_kaoyan_attachments.py`
- **修改：** `ingest/loaders.py`：新增 `ParsedDocument(LoadedDocument)`（多 `tables / images / meta`）；`load_file()` 分发 `.html/.htm/.xlsx/.xls/.jpg/.png`；无字符层 PDF 页 → `needs_ocr`；`.doc` 仍抛错；`.csv` 不进 `_SOURCE_SUFFIXES`。`ingest/pipeline.py`：`needs_ocr` 文档不报错，结果里带标记。`config.py` 加 `ocr_backend`；`requirements.txt` 加 `pdfplumber`、`beautifulsoup4`、`lxml`、`xlrd`
- **测试（全部用已入库夹具，断言值先开文件核对）：** CURSOR_PROMPT K2 列出的 8 条（中大 cse 细则表行 379/50/50/60/60；暨南 2027 目录 085412=62、052 学院行 116、010 备注“指标为24个”；华师 019 目录 `48(17)`、`50(4)`；华师 2027 推免 xls ffill 后 019/041 的 085410 推免 3/8；中大校线 PDF“工学[08] 280 45 60”；sece data URI PNG sha256=`19cedf27…6209`；华工 cs 页 2 个 `pdfsrc` 附件“2026学硕.pdf / 2026专硕.pdf”；`iter_source_files` 新后缀 + 仍跳过 csv）
- **验收：** `POST /v1/ingest {"paths":["data/kaoyan/raw"]}` 可跑通，失败文件在 `docs_failed` 带原因；图片 / 扫描件在 `ocr_backend=none` 时标 `needs_ocr` 不报错；`tests/test_docx_loader.py` 不改仍通过
- **计划外新增（脱敏决策落地）：** `ingest/redact.py`（表头驱动：姓名 → 姓+某、编号列删除、续页表沿用表头、文本兜底、“拟录取X等N人”首名）、`kaoyan/privacy.py`（读 `contains_personal_data`）、`pipeline.load_document()`（ingest 与 `parse_document` 共用）、`tests/test_redact.py`；`IngestResponse` 加 `docs_needs_ocr`、`docs_redacted`
- **结果：** 100 passed（70 + 30）。临时库 ingest `data/kaoyan/raw`：96 文件，90 indexed / 0 failed / 7 needs_ocr / 26 redacted，1344 chunks；26 个名单文件 4187 个姓名 0 泄漏、0 个 15 位编号。PDF 默认仍走 pypdf，只有 `data/kaoyan/` 下的文件抽表。详见 `docs/kaoyan_phase2_notes.md`
- **状态：** complete

### 阶段 K3：检索元数据 + 考研索引
- **修改：** `ingest/chunking.py`（`TextChunk` 加可选 `doc_id/school/college/year/doc_type/title/url`；考研 chunk_id 用 `doc_id` 前缀；表格按行切、每块重复表名 + 表头）、`rag/embeddings.py`（`Hit.metadata`）、`rag/store.py`（BM25 路径和 Chroma `where` 支持 school/year/doc_type 过滤；`get_store(profile="enterprise"|"kaoyan")` 按 profile 缓存实例，默认行为不变）、`rag/query_expand.py`（考研意图扩展 + 学校别名表，按 profile 选择；企业规则原样保留）、`tools/registry.py`（`rag_search` 加可选 `school/year/doc_type`，旧调用不变）、`config.py`（`kaoyan_chroma_dir=data/chroma_kaoyan`、`kaoyan_collection=kaoyan_docs`）、根 `.gitignore`（加 `data/chroma_kaoyan/`）
- **新增：** `scripts/ingest_kaoyan.py`（从 `kaoyan.db.documents` / `sources.json` 带元数据导入；`contains_personal_data=true` 的文件经 `load_document` 脱敏后入索引，见决策表；chunk 元数据带 `redacted` 标记）、`tests/test_kaoyan_retrieval.py`
- **测试（纯 BM25，不需要 Ollama）：** `school='jnu'` 只回暨南；`year=2027 + doc_type='catalog'` 命中 2027 目录；表格块保留表头；企业 profile 检索结果与改动前一致
- **验收：** 以上测试通过；有 key 时 `scripts/smoke_chat.py` 仍 3/3
- **实际做法补充：** 元数据来自 `sources.json`（`kaoyan/index.py` `ingest_kaoyan()`，不依赖先跑种子）；块开头额外重复当前学院行 / 专业行；考研 profile 的排序先验（名单 ×0.5、文档类型匹配意图 ×1.2、学院名命中 ×1.2、候选池 `max(8k,60)`）；`RAG_PROFILE` 配置；`redact_document` 兜底落到单元格（按单元格切块后仍然有效）
- **结果：** 113 passed（100 + 13）。正式索引 90 文档 / 1926 chunk / hybrid，26 个名单文件自身 0 泄漏；golden 18 题 hit@5：BM25 16、hybrid 15（#6 图片待 K7；#17 名单降权属设计；hybrid 另漏 #13、#14）。企业语料：`chunks.jsonl` 逐字节相同，8 个问题检索结果 / 分数 / 工具输出一致；`smoke_chat.py` 3/3。详见 `docs/kaoyan_phase3_notes.md`
- **状态：** complete

### 阶段 K4：结构化抽取
- **新增：** `src/doc_agent/kaoyan/extract/`（`base.py` 抽取器协议 + `Fact` 输出；规则抽取器：`jnu_catalog_html.py`、`scnu_zsml_html.py`、`scnu_tm_xls.py`、`sysu_retest_html.py`、`sysu_baseline_pdf.py`、`scut_plan_html.py`；`llm_fallback.py`：JSON 输出，必须给证据原文片段，否则丢弃）、`scripts/extract_kaoyan.py`、`scripts/eval_extraction.py`（→ `docs/kaoyan_extraction_report.md`）、`tests/test_kaoyan_extract.py`
- **验收：** 已入库文字类文档中、`majors.csv` 覆盖到的事实，规则抽取与种子完全一致（中大各学院复试线、暨南 2027 目录计划、华师目录总(推免)、华师 2027 推免数）；每条事实有 `source_doc_id + evidence_text`；冲突只记录不覆盖
- **测试：** 规则抽取对夹具断言；LLM 兜底用假模型；依赖本地专用文件（暨南 2026 各学院复试方案 xlsx，含名单）的用例缺文件时 `pytest.skip`
- **注意：** 暨南 2026 学院复试线只在本地专用 xlsx 里；中大 2026 目录 PDF（5.2MB）已下载到本机（被忽略，见开放问题 2），相关用例缺文件时 skip
- **实际做法补充：** 规则抽取器共 10 个（计划外增加 `sysu_catalog_pdf`、`jnu_retest_xlsx`、`jnu_tm_pdf`、`scnu_retest_html`，覆盖种子引用的 PDF / xlsx 来源）；`apply.py` 解析专业 + 按自然键比对 + 幂等写库；`run.py` 运行器；`evaluate.py` 生成报告；schema 给 `directions / exam_subjects` 加 `evidence_text`（老库自动补列），`v_program_facts` 同值同文档去重
- **结果：** 139 passed（113 + 26）。四类验收全部逐值一致（中大学院复试线 14/14、暨南 2027 目录 11/11、华师目录总(推免) 16/16、华师 2027 推免 7/7），冲突 0；450 条种子复现 363 条，未复现的是名单统计 57 / 图片 24 / 种子判断 5 / 招生简章 1 / 名单计数 1（有抽取器的文档内只剩 2 条）；504 条规则事实全部带来源和证据，二次运行不变。详见 `docs/kaoyan_phase4_notes.md`、`docs/kaoyan_extraction_report.md`
- **状态：** complete

### 阶段 K5：Agent 工具、提示词、API
- **新增：** `tools/kaoyan.py`（`search_programs`、`get_score_lines`、`get_exam_subjects`、`compare_programs`、`get_document`、`list_sources`，全部返回 JSON 且每条事实带 source）、`api/routes_kaoyan.py`、`api/schemas_kaoyan.py`、`scripts/smoke_kaoyan.py`、`tests/test_kaoyan_tools.py`、`tests/test_kaoyan_api.py`、`tests/test_kaoyan_guardrails.py`
- **修改：** `tools/registry.py`（注册新工具）、`agent/prompts.py`（考研版规则，CURSOR_PROMPT 3.6 / 第 7 节全部写入）、`agent/nodes.py`（第 0 轮按意图先调结构化工具，叙述类才 `rag_search(goal)`；`_run_tool` 从新工具输出收集 citations；`finalize_node` 前后数字校验，失败重生成一次，再失败删数字写“依据不足”）、`agent/guardrails.py`（考研意图识别 + 数字校验；企业别名逻辑改为仅 enterprise profile 生效，不删）、`agent/state.py`（`intent`、`facts`，`run_agent` 给默认值）、`api/__init__.py`（标题 / 描述换考研，`version=__version__`）、`api/schemas.py`（`HealthResponse` 加可选 `kaoyan_db/programs/documents`）、`api/routes.py`（`/health` 只加字段）、`src/doc_agent/__init__.py`（`__version__ = "0.4.0"`）
- **“统招”取值：** 优先明确的 `public_exam / college_exam_plan / available_exam`（逐条标口径）；否则 `catalog_total − tm`（两者都精确）；`tm` 为上限时只给下限（如“≥13”），不算满足 “>20”；取不到进 `unknown` 并写原因
- **测试：** 工具函数直查临时 `kaoyan.db`；数字校验单测；新接口 TestClient（含 404 / 422 错误信封）；`tests/test_api_errors.py` 不改仍通过
- **验收：** 有 `LLM_API_KEY` 时 `smoke_kaoyan.py`：数值类 ≥90%，“必须回答未知”100%，PII 用例 100% 拒绝，每个答案都有引用
- **实际做法补充：** 查询逻辑放在 `kaoyan/query.py`（工具和 API 共用）；考研流程放在 `agent/kaoyan_flow.py`，`nodes.py` 只按 `intent` 分流：考研题 plan / act / reflect 确定性执行（不让模型选工具），finalize 调模型后做数字校验；企业路径不访问考研库，`_force_compare`（企业别名）只在企业路径运行。统招阈值只看该专业能算出统招的最新一年，明确口径优先于派生值。`rag_search` 加可选 `profile`。新增 `tests/test_kaoyan_agent.py`（假模型跑整张图）和 `tests/conftest.py`（种子包建临时库）
- **结果：** 196 passed（139 + 57）。真实 DeepSeek 冒烟 18/18：数值 14/14、未知 2/2、隐私 1/1、导出 1/1、引用 18/18；企业 `smoke_chat.py` 仍 3/3。详见 `docs/kaoyan_phase5_notes.md`
- **状态：** complete

### 阶段 K6：采集层
- **新增：** `collect/base.py`（`SiteAdapter` 协议、`FetchResult`、`DiscoveredDoc`）、`collect/http.py`（UA、超时、指数退避最多 2 次、4xx 不重试、按 host 串行限速 ≥3s、robots、ETag / If-Modified-Since、页数上限、`dry_run`）、`collect/dedupe.py`、`collect/generic_list.py`、`collect/adapters/{sysu,scut,jnu,scnu}.py`、`collect/sites.json`（由 `sources.json.schools[]` 生成）、`scripts/crawl_kaoyan.py`、`tests/test_kaoyan_collect.py`
- **修改：** `api/routes_kaoyan.py`（`POST /v1/crawl` 默认 `dry_run=true` → `run_id`；`GET /v1/crawl/{run_id}`，记录在 `kaoyan.db.crawl_runs`）、`config.py`（`crawl_*`）
- **测试（全部 `httpx.MockTransport`）：** 限速、robots、重试、URL 规范化 / 文章 ID / sha256 去重、SCUT 多栏目 a{ID} 去重、SYSU 分页 URL 修正、SCNU WebForms 回发参数、JNU 年份探测、`yanzhao.scut.edu.cn` 302 → `blocked` 且不重试
- **验收：** 用户手动跑一次真实 `probe`（每校列表第 1 页、间隔 ≥3 秒），结果与耗时写进 `progress.md`；新文档进 `documents`，已有的按 sha256 识别为未变化
- **实际做法补充：** 列表页按 `sites.json` 里的文章 URL 正则识别（不依赖 CSS 选择器），发布日期取 URL 中的日期，否则取链接附近文字；标题优先取 `title` 属性，其次取内层 `.title`，网站截断的标题（以“…”结尾）登记时用文章页标题补全。`collect/crawler.py` 负责编排：`crawl_runs` 记录、新文章下载到 `cache/<school>/` 并登记（id `{school}-w{hash8}`，按标题猜 doc_type / 年份 / 个人信息，标题过 `redact_text`），已知文章按 304 → sha256 → 正文指纹（忽略浏览计数）判断是否变化，变化时登记新版本 `{id}-v{n}`（`parent_doc_id`），404 / 410 标 `removed`；full 模式下载附件（同 sha 只记重复）并回发抓华师目录。标题提醒：出现比库里更新年份的“招生简章 / 章程 / 专业目录”。`import_manual` 走手动导入（id `{school}-m{sha8}`）。站点探测：中大文章 ID 递增、华工目录系统是否可访问及年度下拉、暨南下一年目录栏目、华师目录年份下拉。`sites.json` 的规则键（adapter / lists_override / article_patterns / skip_url_patterns / probe）在重新生成时保留
- **结果：** 223 passed（196 + 27）。真实 dry-run probe：4 校 11 次请求、42.4 s，93 篇文章（79 新 / 14 已知），7 条提醒；真实非 dry-run probe：80 次请求、321.1 s，登记 67 篇（`documents` 97 → 164），华工 2 篇已知文章按 sha256 判为未变化，0 错误 0 blocked；补跑（每校上限 40）104 次请求、437.4 s，再登记 12 篇（→ 176），76 篇已知文章未变化，修复正文指纹后 0 误判。详见 `progress.md`、`docs/kaoyan_phase6_notes.md`
- **状态：** complete

### 阶段 K7：OCR / 视觉 + 前端 + 文档
- **修改 / 新增：** `ingest/ocr.py` 接 `rapidocr`（`requirements-ocr.txt`）和 `vision`（OpenAI 兼容多模态，`vision_*` 配置）；OCR 结果按 sha256 缓存到 `data/kaoyan/ocr_cache/`；6 张图片表格 OCR 产出 `verified=0`，与种子一致才标已核对；扫描名单只统计人数。前端：新增“专业筛选”页（调 `/v1/programs`，显示口径和来源链接），演示剧本换成第 6 节问题，`frontend/api_client.py` 新方法配测试。README / `data/README.md` / `docs/` 更新
- **可选：** 包改名（单独 PR，等用户决定）——未做
- **实际做法补充：** 表格不靠 OCR 猜结构：`ingest/ocr_table.py` 用长墨迹找线框，文字框按中心落格，缺线 = 合并格；vision 直接要 Markdown 表。OCR 结果按图片 sha256 缓存。名单文件在 `load_document` 里强制 `NoOCR`，人数统计走 `kaoyan/roster.py` + `scripts/roster_stats.py`（只打印，不写库）。新增华工两种图片表抽取器，中大细则抽取器同时匹配图片。前端展平逻辑放在不依赖 streamlit 的 `frontend/kaoyan_view.py`，便于单测
- **结果：** 250 passed（223 + 27）。6 张图片 61 条事实：17 条与种子一致、15 条新（`verified=0`）、29 条超出 37 个专业、0 冲突；评估报告种子复现 363 → 380。vision 只做了假传输测试（无 `VISION_*`）；scut-044 本机缺失，名单计数只有离线测试。详见 `docs/kaoyan_phase7_notes.md`
- **状态：** complete

## 开放问题
1. （无）Embedding 已定为本地 Ollama `qwen3-embedding:0.6b`；仍保留未配置时 BM25 兜底。
2. ~~【K4】中大 2026 目录 PDF 缺失~~ → 已解决（2026-09-27）：按 manifest `source_url` 下载 1 次，sha256 `497d86ba…b7b0` 一致，放在 `data/kaoyan/raw/sysu/`（被忽略，不入库）。
3. ~~提交方式~~ → 已确认：分支 `feat/kaoyan`，每阶段一个提交，提交前先给 diff 摘要；不 push。
4. ~~个人信息文件是否进索引~~ → 已确认：脱敏后可进索引（见决策表）。

## 已做决策
| 决策 | 理由 |
|------|------|
| 后端优先，Streamlit 后置 | 用户本次明确要后端落地方案 |
| Chroma 本地持久化到 `data/chroma` | 与 PRD 一致，零额外服务 |
| LangGraph 自定义 State，不用纯线性 AgentExecutor | PRD 核心亮点：循环/分支/迭代 |
| 工具模块独立于图节点 | 可单测、可扩展 |
| 回答严格 grounded 于检索片段 | 防幻觉，贴合企业私有文档场景 |
| 演示语料用公网年报 + 可控样例 | 已落在 `data/`，可直接 ingest |
| 解析优先 pypdf（一期不做 docx） | 用户确认一期 PDF+txt |
| LLM = DeepSeek（`deepseek-chat`） | 用户指定 |
| Embedding = 本地 Ollama `qwen3-embedding:0.6b` → Chroma；未配置时 BM25 兜底 | DeepSeek 无官方 Embedding；用户本机已有该模型 |
| 检索默认 hybrid（dense RRF + BM25）+ 年报章节查询扩展 | 人工验证暴露纯向量对长年报章节召回不足 |
| 二期记忆：进程内 Session + SQLite TaskStore | 零运维，可回放轨迹 |
| 二期图：act→reflect→条件重试 | 对齐 PRD 自我校验与 max 5 工具轮次 |
| 三期异步用 FastAPI BackgroundTasks + SQLite 状态 | 零额外中间件，够演示；多 worker 再上队列 |
| 统一 error 信封 `{error:{code,message,details}}` | 前端/脚本易解析 |
| API Key 仅存 `.env`，不入库 | 防泄露；聊天中已暴露建议轮换 |
| 阶段 5 后端优先，Streamlit 拆阶段 6 | 对齐 PRD 可视化但仍分阶段交付 |
| 【K】包名 `doc_agent`、仓库名暂不改；`__version__` 升 0.4.0 | tests / scripts / frontend / `PYTHONPATH=src` 都依赖包名；改名另开 PR 由用户决定 |
| 【K】结构化数据单独放 `data/kaoyan.db`，不动 `memory.db` 表 | 与聊天轨迹解耦；根 `.gitignore` 的 `*.db` 已覆盖 |
| 【K】考研索引独立：`data/chroma_kaoyan/` + `kaoyan_docs`；`get_store(profile)` | 企业演示索引、`ingest_demo.py`、`smoke_chat.py` 不受影响 |
| 【K】新接口放 `api/routes_kaoyan.py` / `schemas_kaoyan.py`；`/health` 只加可选字段 | 现有契约被 `frontend/api_client.py`、`test_api_errors.py` 依赖 |
| 【K】`load_file()` 返回 `ParsedDocument`（`LoadedDocument` 子类） | 旧调用方与 `test_docx_loader.py` 无需改动 |
| 【K】含个人信息的文件可进 RAG 索引，但入索引前脱敏：姓名 → “姓+某”（如 李某），考生编号整列删除 | 用户 2026-09-27 确认；约束 4：答案 / 日志 / 导出不出现可识别考生信息；统计抽取仍读原文件 |
| 【K】同一 (program, year, kind) 多来源全部保留，按口径并列返回 | 口径冲突是常态（目录 vs 细则 vs 统考可用计划），不能挑一个 |
| 【K】派生值（如 210−165=45）由工具显式输出 `derived{value, formula, inputs}` | 数字校验只认证据里出现的数；派生值不写出来会被误删 |
| 【K】数字校验豁免：年份、专业代码、科目代码、方向序号、页码 | 其余数字必须能在工具证据中找到 |
| 【K】种子 `verified=1`；`ocr` / `llm` 抽取默认 `verified=0` | 种子为人工核对；机器抽取需与种子对上才标已核对 |
| 【K】华工 `yanzhao.scut.edu.cn` 标 `blocked`，走手动导入 | 统一认证 302；不绕过登录 |
| 【K2】PDF 抽表（pdfplumber）只对 `data/kaoyan/` 下文件开启，默认仍用 pypdf 文本 | 企业索引文本不变；抽表慢（大名单 PDF 约 18 s） |
| 【K2】脱敏放在 `load_document`，切片 / 索引 / 工具只见脱敏版 | 策略一处实现；个人信息文件自动识别（姓名列 + 编号列）对任意目录生效 |
| 【K3】考研查询扩展拼接在原问题后，不单独成查询 | 单独查“复试分数线”会召回四校所有分数线，丢掉专业代码 |
| 【K3】`rag_search` 带任一考研过滤条件就查考研索引，否则按 `RAG_PROFILE` | 旧调用与企业演示不受影响；K5 可把默认切到 kaoyan |
| 【K3】名单类 chunk 只降权不过滤 | 统计类问题仍可能需要；名单内容已脱敏 |
| 【K4】机器抽取每条单独成行，不更新种子行；与同键种子逐字段相同才 `verified=1`，冲突写 `verified=0` 并进报告 | 冲突只记录不覆盖；多来源并列保留 |
| 【K4】事实只挂到库里已有的专业，37 个目标专业以外的记 `unresolved` 不写库 | 专业表由种子维护；避免抽取器凭表格随意建专业 |
| 【K4】验收只算文字类文档；图片来源（img / pdf-scan）留到 K7 | 需求原文“对文本文档…”；图片需 OCR |
| 【K4】名单表整张跳过，名单计数类统计仍由种子提供 | 规则抽取不读个人信息；证据文本不含姓名 / 编号 / 个人分数 |
| 【K4】LLM 兜底只处理无规则事实的非名单文字文档；证据片段必须在原文中且含该数值 | 不编数字；模型输出可核对 |
| 【K5】考研题的工具调用由意图规则决定，模型只在 finalize 组织答案 | 调用可预测、可单测；每题 1–2 次模型调用；避免模型漏查或乱查 |
| 【K5】统招阈值判断只看该专业能算出统招的最新一年，明确口径优先于派生值；其他年份 / 口径仍并列展示 | 约束“不混用 2026 / 2027”；与 golden #11 口径一致 |
| 【K5】数字校验证据 = 结构化工具原始输出 + 检索片段 + 提示 + 用户问题，不含会话历史；另豁免 0 开头的 4 位学科代码 | 历史回答可能含未经核对的数字；“0812”等代码不是数值 |
| 【K5】派生值以 `formula`（“210 − 165 = 45”）+ 两份来源输出，而不是单独的 `derived` 字段 | 模型可照抄公式，校验能在证据中找到每个数 |
| 【K5】名单题只调 `search_programs` 取统计、不做 RAG；答案缺“个人信息”说明时自动补在开头 | 约束 4；检索片段虽已脱敏也不必带入 |
| 【K6】robots.txt 按 RFC 9309：4xx（含 401 / 403）视为全部允许，5xx / 网络错误视为全部禁止 | 中大 robots.txt 被 WAF 返回 403 页面，列表页本身 200；按标准处理而不是放弃该校 |
| 【K6】列表解析靠文章 URL 正则 + 文章 key（华工 / 暨南 `a{ID}`，中大按学院，华师 `{子站}:{ID}`） | 四校模板不同、改版频繁；同一文章挂多个栏目 / 子域时能去重 |
| 【K6】`dry_run`（默认）只抓列表页和探测 URL，不写 `documents`；`crawl_runs` 照常记录 | 约束 3 礼貌抓取；先看会发现什么再决定是否落库 |
| 【K6】每校请求上限（默认 20，robots.txt 不计）；新文章先登记，已知文章后复查 | 首次运行新文章多时优先补库；复查留到预算剩余或下次运行 |
| 【K6】抓取文档 id `{school}-w{sha1(key)[:8]}`，版本 `{id}-v{n}`，手动导入 `{school}-m{sha256[:8]}`；doc_type / 年份 / 个人信息按标题猜，标题先脱敏 | 与种子 id（`jnu-001`）不冲突、可重复计算；猜错只影响排序，K7 可人工修正 |
| 【K6】栏目路径失效时在 `sites.json` 写 `lists_override`，不改 `sources.json` | `sources.json` 是种子包原文；覆盖项在重新生成时保留 |
| 【K6】`crawl_min_interval_sec` 低于 3 秒时强制改为 3 秒 | 约束 3：同一 host ≥3 秒，配置写错也不能更快 |
| 【K7】OCR 表格按线框还原（长墨迹 = 线，实心色带两边各算一条线，缺线 = 合并格），不让 OCR / 模型推断表结构 | 通知图片线框规整；合并格展开方式与 HTML `rowspan` 一致，抽取器可共用 |
| 【K7】OCR 事实 `extraction_method=ocr`，入库规则同 K4（同键同值才 `verified=1`） | 约束：OCR 产出 `verified=0`，和种子对上才能标已核对 |
| 【K7】华工校线图按学科门类出事实，不展开到专业；种子按专业展开的 5 条记为未复现 | 哪些专业适用哪条门类线是编辑口径，抽取器不替人决定 |
| 【K7】名单文件永不 OCR 入库；扫描名单计数只打印、不写库 | 约束 4；全校按专业代码计数混合学院 / 联培，口径要人工确认 |
| 【K7】OCR 依赖可选（`requirements-ocr.txt`），真实 OCR 测试 `importorskip` | 核心安装不变；CI / 别的机器没装也全绿 |
| 【K7】不改包名 | CURSOR_PROMPT 3.8：单独 PR，由用户决定 |
| 【K6】正文指纹只取 `content_selector`（中大 `article`、华工 / 暨南 `.wp_articlecontent`、华师 `.detail .article`）内的文字 + 链接 / 附件地址；选择器取不到时退回整页文字 | 边栏和上一篇 / 下一篇随新文章变化，整页比较会误建版本；正文只有 PDF 播放器时靠 `pdfsrc` 发现附件替换 |

## 遇到的错误
| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| Python 3.14 无法安装 pydantic | 1 | 改用 python3.12 创建 `.venv` |
| chromadb 安装过慢 | 1 | 拆到 `requirements-embedding.txt`；启用本地 Embedding 时再装 |
| BM25 中文整段成单 token | 1 | CJK unigram+bigram 分词 |
| plan 把制度问答判成 direct | 2 | 默认 tools + 寒暄白名单 |
| 年报章节召回偏审计页 | 1 | hybrid RRF + 意图扩展 + 文档过滤 |
| 查询扩展被主营意图占满 | 1 | 多意图 round-robin 扩展 |
| 短语加权跨意图误加分 | 1 | 按意图族分别加权 |
| 【K0】task_plan 阶段 6 标 pending 与代码不符 | 1 | 按代码核对后更正为 complete（代码），注明人工验收结果未落文档 |
| 【K0】`requirements-embedding.txt` 缺 `python-docx`、`openpyxl` | 1 | K1 已同步 |
| 【K1】同一页面 URL 对应多个文档，来源挑错（推免列指到分数线图片、华工 085404 复试名单指到 081200 名单） | 2 | 按事实类型设 doc_type 优先级打分；标题里写了别的专业代码 −50；只扣分不加分，避免把图片正文换成外壳 HTML |
| 【K1】暨南 0812 一级学科复试人数挂到每个二级学科上看不出是合计 | 1 | `admission_stats` 加 `pool_scope` 列 |
| 【K1】“统考拟录取13（普通）+2（退役）”被回溯抽成 1 | 1 | 正则加 `(?!\d)`；拆分口径不抽，留 notes |
| 【K2】sandbox 内 `pip install` 到 `.venv` 报 Read-only file system | 1 | 沙箱外执行安装 |
| 【K2】`git ls-files` 把中文路径转义，个人文件 / 大文件检查漏判 | 1 | 改用 `git -c core.quotepath=false ls-files -z` |
| 【K2】未标个人信息的华工公示正文含“拟录取X等2582人”首名 | 1 | 泄漏扫描发现；加首名打码规则，对所有考研文档生效 |
| 【K3】按单元格切块绕过了页面级脱敏兜底 | 1 | `redact_document` 把兜底落到每个单元格；本地泄漏测试同时查单元格 |
| 【K3】名单 chunk 每行重复专业代码，BM25 下挤占前几名 | 2 | 名单降权 + 文档类型 / 学院先验；候选池放大，否则先验够不到正确文档 |
| 【K4】华师复试方案计划表被当成考生表跳过（数据行含“立功表彰免初试考生”） | 1 | 只按表头“考生姓名 / 初试成绩”识别考生表 |
| 【K4】中大细则专项复试线落成普通学院线（“备注”只在双层表头的上一行） | 1 | 备注列向上查找表头行 |
| 【K4】华师 046 目录专业行无“(推免)”，推免 0 只写在备注“不招推免生” | 1 | 备注含“不招推免生”且专业行无推免数 → 推免 0，证据取备注 |
| 【K4】中大基本线“单独考试 公共卫生[1053]”与专业学位同代码，被判重复 | 1 | 只读学术学位 / 专业学位行 |
| 【K4】sandbox 内 `uvx ruff` 无法写 `~/.local/share/uv` | 1 | `UV_CACHE_DIR / UV_TOOL_DIR` 指到工作区临时目录，用完删除 |
| 【K5】暨南 2026 统招计划与 2027 派生下限同时参与阈值判断，筛选结果混了年份 | 1 | 阈值只看最新一年、明确口径优先（`public_plan_basis`） |
| 【K5】冒烟首轮 16/18：模型主动写用户没问的“2027 年复试线未取得”，写“考 408 / 不考 408”，边界项漏补复试线 | 3 | 提示词加规则 4 / 14 / 15，规则 5 要求原样写“官方资料中未取得”；规则 14 限定“用户问到 408 时”，no_exam 专业不提 408 |
| 【K5】数字校验把学科代码“0812”判为无依据数字 | 1 | 豁免 0 开头的 4 位学科代码；普通 4 位数（如 1200）仍校验 |
| 【K5】FastAPI 依赖写成参数默认值触发 ruff B008，改 `Annotated` 后无默认参数排在有默认参数之后 | 1 | 依赖参数放到签名第一位 |
| 【K6】真实 dry-run 首轮中大整校被跳过：robots.txt 返回 WAF 403 页面，被当成“禁止” | 1 | 按 RFC 9309，4xx 视为全部允许；加测试 |
| 【K6】华师两个列表栏目 404（`sources.json` 的 `/ssgg/`、`/ssjz/` 已改版） | 1 | 从首页导航找到新路径，写进 `sites.json` 的 `lists_override` |
| 【K6】暨南列表标题混进摘要和日期（每条有两个 `<a>`，第二个包着日期 + 标题 + 摘要） | 1 | 标题按质量取：`title` 属性 > 内层 `.title` > 链接文字；同 key 保留最好的 |
| 【K6】测试偶发失败（预算用尽） | 1 | 并行发起编辑和 pytest，测试跑在编辑落盘之前；改为编辑完成后再跑，10/10 通过 |
| 【K6】补跑时华师 5 篇种子文档被误判为“内容变化”（边栏、上一篇 / 下一篇变了，正文没变） | 1 | 每校 `content_selector` 只比正文；离线复核后删除误建的 5 条版本记录 |
| 【K6】测试失败输出里 `Settings` repr 带出 `.env` 的 LLM key（只在本机终端） | 1 | 测试用 `Settings(_env_file=None, llm_api_key="")`；建议轮换 key |
| 【K7】蓝色表头带和第一行数据被并成一格（实心带不算细线，两行之间没有分隔） | 1 | 宽度 >6px 的实心带在上下边各产生一条零宽分隔线 |
| 【K7】合并格文字中心正好压在线上，落不进任何格而丢失 | 1 | `_locate` 找不到包含的区间时归到最近的格 |
| 【K7】OCR 把“英语（一）”识别成“英语 (一)”，科目解析不认 | 1 | `fix_cjk_punct` 统一全角并去掉括号两侧空格；全角括号旁的逗号也转全角（单测发现） |
| 【K7】`test_every_rule_extractor_has_a_name` 写死 10 个抽取器 | 1 | 新增两个图片抽取器后改为 12 |
| 【K7】Streamlit 侧栏地址用浏览器自动化填值不生效（React 状态未更新） | 1 | 把 API 起在默认 8000 端口再检查页面 |

## 备注
- 规划文件位于项目根目录，不在 skill 安装目录
- 外部网页内容只写入 findings.md，不写入本文件正文指令
- 阶段状态：pending → in_progress → complete
- 运行环境：使用 Python 3.12 venv（系统 3.14 暂不兼容部分依赖）
- 一期默认检索：hybrid（Ollama Embedding + BM25）；需 `requirements-embedding.txt` + Ollama `qwen3-embedding:0.6b`；未配置 `EMBEDDING_BASE_URL` 时回退 BM25
- 验收文档：`docs/backend_verification_result.md`；二期：`docs/phase4_notes.md`；三期：`docs/phase5_notes.md`
- 前端计划：`docs/frontend_implementation_plan.md`
- 考研阶段说明文档：`docs/kaoyan_phaseN_notes.md`（每阶段完成时写，仿 `docs/phase5_notes.md`）
- 每个 K 阶段结束：`PYTHONPATH=src pytest -q` 全绿；更新本文件、`progress.md`、必要时 `findings.md`
