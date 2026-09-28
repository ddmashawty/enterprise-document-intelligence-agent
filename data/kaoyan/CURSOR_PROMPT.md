# 任务：把本仓库重构为「考研（硕士研招）信息 Agent」

你在 `ddmashawty/enterprise-document-intelligence-agent` 仓库里以 Agent 模式工作。种子数据包已经复制到 `data/kaoyan/`。下面是完整需求。**先读、先出计划、等我确认，再动大块代码**；确认后先完成 Phase 1。

---

## 0. 开始之前（按顺序做，不要跳）

1. 通读仓库：
   - `README.md`、`task_plan.md`、`findings.md`、`progress.md`、`企业文档智能处理Agent 产品需求文档（PRD）.md`、`docs/phase4_notes.md`、`docs/phase5_notes.md`、`docs/frontend_implementation_plan.md`、`data/README.md`、`data/SOURCES.md`
   - `src/doc_agent/` 下全部模块（清单见第 2 节），`tests/` 全部，`scripts/`，`frontend/`
   - 注意：`task_plan.md` 写着“阶段 6（Streamlit 前端）pending”，但仓库里已经有 `frontend/app.py`、`frontend/api_client.py`、`frontend/components/*`、`tests/test_frontend_client.py`。以代码为准，先确认前端实际完成到哪一步，并在计划里写明。
2. 通读数据包：`data/kaoyan/README.md`（必读）、`data/kaoyan/sources.md`、`data/kaoyan/sources.json`（先看 `schools[]`，`documents[]` 扫一遍字段）、`data/kaoyan/majors.csv`、`data/kaoyan/raw/manifest.csv`。
3. 跑基线：`PYTHONPATH=src pytest -q`，记下通过数；确认 `data/kaoyan/.gitignore` 生效（`git status` 里不应出现 `raw/**/…复试名单…`、`raw/scut/scut_2026_拟录取硕士名单_不含推免.pdf`、`raw/sysu/sysu_2026_硕士招生学科专业目录.pdf` 等 28 个文件）。
4. 产出一份实施计划（写进 `task_plan.md`，沿用现有格式：目标 / 当前阶段 / 各阶段勾选项 + **状态** / 已做决策表 / 遇到的错误表）。新阶段编号用 **K0–K7**，接在现有“阶段 6”后面。计划里每个阶段列出：要新增 / 修改的文件、验收标准、测试。然后**停下来等我确认**。
5. 我确认后，执行 Phase 1（K1）。每完成一个阶段：更新 `task_plan.md` 状态、`progress.md`（沿用“会话：日期 / 状态 / 五问重启检查”格式）、必要时 `findings.md`，并写 `docs/kaoyan_phaseN_notes.md`（仿照 `docs/phase5_notes.md`）。

---

## 1. 背景与目标

现在的仓库是“企业文档智能处理 Agent”：FastAPI + LangGraph（plan → act → reflect → retry | finalize，工具调用上限 5）+ DeepSeek `deepseek-chat` + 混合检索（Ollama `qwen3-embedding:0.6b` 写 Chroma + BM25）+ SQLite 记忆 + PDF/DOCX/TXT/MD 导入 + Markdown/Excel 导出 + 异步任务。

目标：**保留这套骨架**，改造成面向中国大陆硕士研究生招生（考研 / 研招）信息的 Agent：

1. **采集**：礼貌地爬取学校研招网和学院官网的公告、简章、专业目录、复试细则、分数线等，发现附件，去重，检测变化（例如 2027 目录上线）。
2. **解析**：处理异构文件：HTML 表格、文字版 PDF（按坐标抽表）、xls/xlsx（多级表头、合并单元格）、doc/docx、图片表格和扫描 PDF（OCR / 多模态，可插拔）。
3. **结构化抽取**：把学校 / 学院 / 专业 / 方向 / 初试科目 / 招生计划 / 复试线写入 SQLite。**每个数值都带来源文档、页码、年份、口径**。
4. **问答**：按条件筛选专业（例如“考 408 且统招 > 20”）、查复试线、对比学校、导出 Excel。**每个数字都要有出处；不知道就说不知道**。

第一批数据范围：中山大学、华南理工大学、暨南大学、华南师范大学的泛计算机专业（0812 及二级学科、0835、0839、085404/05/10/11/12、华工 140500；中大 765 的 085400 是边界项）。以后要能加学校，而不用改核心代码。

---

## 2. 现状：模块逐个说明（保留 / 复用 / 修改）

| 路径 | 现在是什么 | 处理方式 |
|---|---|---|
| `src/doc_agent/config.py` | `Settings`（pydantic-settings，读 `.env`）：`llm_*`、`embedding_*`、`chroma_dir`、`raw_dir`、`export_dir`、`memory_db`、`collection_name`、`chunk_size/overlap`、`top_k`、`max_tool_calls`；`get_settings()` 带 `lru_cache` | **扩展**：新增 `kaoyan_db`（默认 `data/kaoyan.db`）、`kaoyan_data_dir`（`data/kaoyan`）、`kaoyan_chroma_dir` / `kaoyan_collection`、`crawl_user_agent`、`crawl_min_interval_sec`（默认 3.0）、`crawl_respect_robots`（默认 true）、`crawl_cache_dir`（`data/kaoyan/cache`）、`ocr_backend`（默认 `none`）、`vision_base_url/vision_model/vision_api_key`。同步更新 `.env.example` |
| `src/doc_agent/api/__init__.py` | `create_app()`：标题 “Enterprise Document Intelligence Agent”，**版本号写死 "0.3.0"**，注册统一错误处理器，`include_router(router)` | **修改**：`version` 改用 `doc_agent.__version__`；标题 / 描述换成考研；再 `include_router` 新的考研路由 |
| `src/doc_agent/api/routes.py` | `/health`、`POST /v1/ingest`、`POST /v1/chat`、`POST /v1/chat/async`、`GET /v1/tasks`、`GET /v1/tasks/{task_id}`、`GET /v1/sessions/{session_id}` | **保持契约不变**（`frontend/api_client.py` 和 `tests/test_api_errors.py` 依赖它们）。`/health` 只能**加**可选字段（例如 `kaoyan_db`、`programs`、`documents`）。新接口放新文件 `api/routes_kaoyan.py` |
| `src/doc_agent/api/schemas.py` | `IngestRequest/Response`、`ChatRequest/Options/Response`、`TaskResponse`、`HealthResponse` 等 | 扩展：新接口的 schema 放 `api/schemas_kaoyan.py`；`HealthResponse` 只加带默认值的可选字段 |
| `src/doc_agent/api/errors.py` | `http_error(status, code, message)`，统一信封 `{"error":{"code","message","details"}}` | **复用**，新接口一律用它 |
| `src/doc_agent/api/jobs.py` | `enqueue_chat_job` / `run_chat_job`，FastAPI `BackgroundTasks` + `TaskStore` | **复用思路**做 `/v1/crawl` 后台任务；但 `TaskStore.tasks` 表是聊天专用字段，爬虫运行记录另建 `crawl_runs` 表（在 `kaoyan.db`） |
| `src/doc_agent/agent/graph.py` | `build_graph()`：`START → plan → (route_node) act|finalize`，`act → reflect → (after_reflect) act|finalize → END`；`run_agent()` 负责记忆和持久化 | **保留图拓扑**，不改边 |
| `src/doc_agent/agent/nodes.py` | `plan_node`；`act_node`（**第 0 轮先确定性调用 `rag_search(goal)`**，再按需 `_force_compare` / `_force_export`，然后让 LLM `bind_tools(get_tool_list())`）；`reflect_node`（大量规则短路 + LLM 反思）；`finalize_node`（只用 `citations[:8]` 等证据生成答案）；`_run_tool` 只从 `rag_search` 和 `compare_docs` 的输出里收集 citations | **修改**：第 0 轮按意图先调结构化工具（见 3.6）；`_run_tool` 要能从新工具的输出收集 citations；`finalize_node` 前后加数字校验 |
| `src/doc_agent/agent/prompts.py` | `PLAN_SYSTEM` / `FINAL_SYSTEM` / `REFLECT_SYSTEM`，企业文档措辞 | **重写**为考研版（规则见 3.6、第 7 节） |
| `src/doc_agent/agent/guardrails.py` | `wants_export/wants_excel/wants_compare`、`infer_export_filename`、`filter_redundant_tool_calls`、`is_list_documents_spin`、`resolve_compare_doc_names`（**写死了 茅台 / 五粮液 / 宁德 / 人权 等别名**）、`citations_to_markdown/excel_rows` | 保留通用函数（`tests/test_guardrails.py` 覆盖）；新增考研意图识别（学校别名、专业代码、复试线 / 计划 / 科目 / 筛选 / 对比意图）和数字校验；企业专用别名逻辑不要删，改成只在 enterprise 语料下生效或挪走 |
| `src/doc_agent/agent/state.py` | `AgentState` TypedDict | 可加字段（如 `facts`、`intent`），加了就要在 `run_agent` 的 `initial` 里给默认值 |
| `src/doc_agent/tools/registry.py` | `@tool`：`list_documents`、`rag_search(query, top_k, doc_name)`、`parse_document`、`summarize_citations`；`get_tool_list()`、`tools_by_name()`、`parse_export_payload()` | 扩展：`rag_search` 加可选过滤参数（school / year / doc_type），旧调用方式继续可用；在 `get_tool_list()` 里注册新工具 |
| `src/doc_agent/tools/compare.py` | `compare_docs`（按文档名分组检索）、`extract_fields`（只产出待填草稿） | 保留；专业对比用新工具 `compare_programs`，不要硬塞进 `compare_docs` |
| `src/doc_agent/tools/export.py` | `export_markdown`、`export_excel`（openpyxl，写 `data/exports/`，返回 JSON 路径） | **复用**；考研导出必须带“年份 / 口径 / 来源URL / 文档ID”列 |
| `src/doc_agent/ingest/loaders.py` | `DocumentPage(source,page,text)`、`LoadedDocument`；`load_pdf`（pypdf 纯文本）、`load_docx`（表格转 `a | b`）、`load_txt`；`load_file()` 按后缀分发，`.doc` 抛 `ValueError`；`_SOURCE_SUFFIXES={.pdf,.txt,.md,.docx,.doc}`；`iter_source_files()` | **扩展**，保持 `load_file(path) -> LoadedDocument` 接口不变（`tests/test_docx_loader.py` 覆盖）。**不要**把 `.csv` 加进 `_SOURCE_SUFFIXES`（`test_iter_source_files_includes_docx` 断言 csv 被跳过）；`.doc` 仍抛错，或者只在装了 libreoffice 时转换，并保持该测试通过 |
| `src/doc_agent/ingest/chunking.py` | `TextChunk(chunk_id, source, page, text, doc_name)`；`chunk_id = "{doc_name}::p{page}::c{n}"`（只用文件名，跨目录同名会撞） | 扩展：加元数据字段（`doc_id/school/college/year/doc_type`），考研文档的 chunk_id 用 `doc_id` 前缀；表格按行切，每块重复表头 |
| `src/doc_agent/ingest/pipeline.py` | `ingest_paths(paths, reindex)`、`ingest_raw_dir()` | 复用；考研导入另写入口（`scripts/ingest_kaoyan.py`），导入时从 `kaoyan.db.documents` / `sources.json` 带上元数据 |
| `src/doc_agent/rag/store.py` | `DocumentStore`：`chunks.jsonl` + BM25（`_tokenize`：CJK 单字 + 双字）+ Chroma（元数据只有 `source/page/doc_name`）；`search(query, top_k, doc_name)` 先用 `infer_doc_name` 猜文档，再 `expand_queries`，RRF 融合，`keyword_boost`；`get_store()` 是**全局单例**，第一次创建后会忽略传入的 settings | 扩展：元数据过滤（BM25 路径和 Chroma `where`）；考研索引要和企业演示索引**分开**（不同目录 / collection），`get_store` 支持按 profile 或 (dir, collection) 取实例 |
| `src/doc_agent/rag/query_expand.py` | 年报专用意图扩展（主营业务 / 风险 / 管理层讨论）+ `infer_doc_name` 写死 茅台 / 五粮液 / 宁德 等 | 新增考研意图扩展（复试线 / 招生计划 / 初试科目 / 推免 / 调剂）和学校别名表（中大 / 中山 / SYSU → sysu 等），按语料选择使用哪套 |
| `src/doc_agent/rag/embeddings.py` | `Hit` dataclass、`RemoteEmbeddings`（OpenAI 兼容，默认 Ollama） | 复用；`Hit` 可加 `metadata` 字段 |
| `src/doc_agent/memory/__init__.py` | `SessionMemory`（进程内）+ `TaskStore`（`data/memory.db`：`tasks`、`session_turns`） | 复用，不改表。结构化考研数据放**单独**的 `data/kaoyan.db`（根 `.gitignore` 里已有 `*.db`） |
| `src/doc_agent/llm/factory.py` | `get_chat_model()` → `ChatOpenAI`（DeepSeek） | 复用做 LLM 抽取兜底。**`deepseek-chat` 不能看图**，视觉模型走单独的 `vision_*` 配置 |
| `src/doc_agent/runtime_options.py` | `request_options()` contextvar：`max_tool_calls`、`temperature` | 复用；工具上限仍默认 5 |
| `frontend/` | Streamlit：`app.py`（标签页 对话 / 知识库 / 任务中心 / 演示剧本；`DEMO_QUESTIONS` 是企业问句）、`api_client.py`（`DocAgentClient`） | 后期（K7）加“专业筛选 / 来源”页，演示问句换成考研问句；`api_client.py` 新增方法要配测试 |
| `scripts/` | `demo_repro.sh`、`ingest_demo.py`、`smoke_chat.py`（读 `data/gold/sample_qa.json`）、`smoke_phase4.py`、`perf_baseline.py`、`download_demo_data.py`、`run_frontend.sh` | 保留（企业演示回归）；新增 `seed_kaoyan.py`、`ingest_kaoyan.py`、`extract_kaoyan.py`、`crawl_kaoyan.py`、`smoke_kaoyan.py`、`verify_kaoyan_bundle.py` |
| `tests/` | `test_api_errors`、`test_chunking`、`test_docx_loader`、`test_export`、`test_frontend_client`、`test_guardrails`、`test_memory`；`pytest.ini`：`pythonpath = src .` | **全程保持全绿**；新测试不调真实 LLM、不连外网 |
| `data/` | `raw/`（企业演示语料，`data/raw/**/*.pdf` 被忽略）、`gold/sample_qa.json`、`SOURCES.md`、`README.md` | 不动企业语料；新增 `data/gold/kaoyan_qa.json`；`data/README.md` 加一段指向 `data/kaoyan/README.md` |

---

## 3. 目标架构

### 3.1 新增目录（建议，可在计划里调整，但要说明理由）

```
src/doc_agent/
  kaoyan/                  # 领域层：结构化库、规范化、种子、抽取
    schema.sql
    db.py                  # KaoyanStore（sqlite3，线程锁仿照 memory.TaskStore）
    models.py              # pydantic：School/College/Program/Plan/ScoreLine/ExamSubject/Document/Fact
    normalize.py           # '48(17)'、'同上'、'≤41'、科目串、专业代码、学校别名
    seed.py                # majors.csv + sources.json → kaoyan.db
    extract/               # 按文档类型 / 站点的规则抽取器 + LLM 兜底
  collect/                 # 采集层
    base.py                # SiteAdapter 协议、FetchResult、DiscoveredDoc
    http.py                # httpx 客户端：UA、超时、重试退避、按 host 限速、robots、条件 GET、字符集判断
    attachments.py         # 附件发现：<a href>、div[pdfsrc]+sudyfile-attr、<img src>、data: URI、相对路径
    dedupe.py              # URL 规范化、文章 ID、内容 sha256
    generic_list.py        # 通用公告列表适配器（配置驱动：列表 URL 模板、条目选择器、日期正则、分页规则）
    adapters/{sysu,scut,jnu,scnu}.py
    sites.json             # 由 data/kaoyan/sources.json 的 schools[] 派生，新增学校时只加配置 / 小适配器
  ingest/
    tables.py              # Table 结构（cells、合并单元格展开、page、bbox），HTML/PDF/xlsx/xls 抽表
    ocr.py                 # OCRBackend 接口：none / rapidocr / paddleocr / vision（OpenAI 兼容多模态）
  tools/kaoyan.py          # 新 Agent 工具
  api/routes_kaoyan.py, api/schemas_kaoyan.py
```

### 3.2 采集层（crawler / collector）

- **每个学校一个适配器**，另有一个**通用公告列表适配器**。适配器只负责：列表页 URL 与分页、条目解析（标题 / 日期 / URL）、文章页附件发现、站点特殊规则。站点细节全部来自 `data/kaoyan/sources.md` 和 `sources.json`：
  - SYSU：列表 `https://graduate.sysu.edu.cn/zsw/postgraduate`，分页链接有 bug（指向 `https://graduate.sysu.edu.cn/?page=N`），要自己拼 `/zsw/postgraduate?page=N`；文章 `/zsw/article/<自增ID>` 可按 ID 递增探测；学院站 Drupal `article/<id>`，sece 是 `/zs/zs01/<id>.htm`，附件用相对路径 `../../docs/...`，分数线是 base64 data URI 图片。
  - SCUT：WebPlus，`/sszs/list.htm`、`list2.htm`…；文章 `/YYYY/MMDD/c{栏目}a{ID}/page.htm`（也有 `.psp`），同一文章出现在多个栏目 ID 下，**按 a{ID} 去重**；学院站附件是 `div.wp_pdf_player[pdfsrc]`，真实文件名在 `sudyfile-attr`；**`yanzhao.scut.edu.cn` 从境外 / 非校园网会 302 到统一认证登录**，适配器要把它标成 `blocked`，不要反复重试，不要尝试绕过登录；提供“手动导入”入口（CLI 把人工下载的文件 + 元数据登记进库）。
  - JNU：只爬 `/tzgg/list.htm`（`list2.htm … list18.htm`），外加按年份探测 `/{year}nssyjszszyml/list.htm`；`/33003/`、`/32993/` 是空列表，`/33059/list.htm` 返回 410；附件 UUID 文件名，真实名在锚文本。
  - SCNU：文章 `/a/YYYYMMDD/<ID>.html`（全站自增，可按 ID 探测），附件在 `statics.scnu.edu.cn`；目录系统 ASP.NET WebForms，参考 `data/kaoyan/scripts/scnu_zsml.py` 改写成适配器；年份下拉出现 2027 即“2027 目录上线”。
- **礼貌抓取**：同一 host 串行，最小间隔 `crawl_min_interval_sec`（默认 3 秒，采集时用的是 3–4 秒）；读取并遵守 robots.txt（`crawl_respect_robots`）；UA 带项目名和联系方式（配置项）；超时 + 指数退避，最多重试 2 次；4xx 不重试；支持 `If-Modified-Since/ETag`；单次运行有页数上限；默认 `dry_run` 只列出发现的文档不下载。
- **去重**：规范化 URL（去 fragment、统一 http/https 和尾斜杠、解码后再编码）；站点文章 ID（SCUT/JNU 的 a{ID}、SYSU 的 article/<id>、SCNU 的 /a/…/<ID>.html）；附件按内容 sha256 去重。
- **变化检测**：`documents` 表记录 `sha256 / first_seen / last_seen / status(active|removed|blocked)`；内容变化生成新版本（保留旧版本，`parent_doc_id` 指向旧的）；探针任务：JNU 目录年份 URL、SCNU 年份下拉、SYSU 文章 ID 递增、各校“招生简章 / 专业目录”标题关键词。
- **文件缓存**：下载到 `data/kaoyan/cache/<school>/<sha256前12位>_<安全文件名>`（已被 `data/kaoyan/.gitignore` 忽略）。
- 测试**全部离线**：用 `httpx.MockTransport` + `data/kaoyan/raw/` 里已入库的文章 HTML 做夹具（例如 `raw/scut/scut_cs_2026_统考入围复试名单_20260316.html` 里有 2 个 `pdfsrc` 附件；`raw/sysu/sysu_sece_2026_复试录取实施细则.html` 有 data URI 图片和 `../../docs/` 相对附件；`raw/jnu/jnu_2026_各学院硕士复试方案_20260320.html` 有几十个 UUID 附件锚文本）。列表页草稿没有打包进来，列表解析测试用手写的小 HTML 夹具。

### 3.3 多格式解析

定义 `ParsedDocument`：兼容 `LoadedDocument`（仍有 `pages: list[DocumentPage]`），额外带 `tables: list[Table]`、`images: list[ImageRef]`、`meta`。`load_file()` 返回值继续能当 `LoadedDocument` 用。

| 输入 | 做法 | 本包里的真实难点 |
|---|---|---|
| HTML | bs4 + lxml；按 `<meta charset>` 判断编码（兜底 utf-8 → gbk）；去掉导航 / 页脚；表格展开 `rowspan/colspan`；抽出 `data:image/...;base64` 图片 | SYSU sece 分数线是内嵌 base64 PNG；JNU 目录是一张 2.4MB 的大表，三层行结构（学院行 / 专业行 / 方向行），人数只写在专业行 |
| 文字版 PDF | **pdfplumber** 按坐标抽表（`extract_tables`，必要时显式设置线 / 文本策略）；pypdf 文本作为兜底；没有字符层的页判定为扫描页，转 OCR | `pdftotext -layout` 会把中大目录相邻学院的标题串到别的学院的行旁边，**不能用行邻接判断学院归属**；中大分数线 PDF 有竖排合并单元格“学/术/学/位”；华工统考可用计划 PDF 学院列纵向居中合并；暨南推免 PDF 单元格文字被截断 |
| xlsx | openpyxl；合并单元格展开；**同一 sheet 多个表块**时按标题行切分 | 暨南各学院复试方案 xlsx：表头 3 行 + 合并单元格，同一 sheet 依次是复试方案、复试名单、专项计划名单 |
| xls（BIFF） | xlrd（或装了 libreoffice 时转 xlsx）；纵向合并列向下填充 | 华师 2027 推免目录前 6 列纵向合并，需要 ffill |
| doc/docx | docx 沿用 `load_docx`；doc 保持现状（报错提示另存）或可选 libreoffice 转换 | 本批 doc/docx 都是表单（双选志愿书、体检表），没有数据，采集时可跳过 |
| 图片 / 扫描 PDF | `ocr.py` 可插拔：`none`（默认，只标记 `needs_ocr`）、`rapidocr` / `paddleocr`（本地，可选依赖放 `requirements-ocr.txt`）、`vision`（OpenAI 兼容多模态接口，`vision_*` 配置）；结果按 sha256 缓存到 `data/kaoyan/ocr_cache/` | 6 张图片表格 + 华工 29MB / 113 页扫描名单 |

单元格规范化（`kaoyan/normalize.py`，要有单测）：
- `48(17)` → 总 48、推免 17（华师目录“总(推免)”）
- `同上` → 继承上一行同列值
- `≤41` → 上限值（`is_upper_bound=True`）；`（0812合计≤19）` → 一级学科合计上限
- 科目串 `①101思想政治理论②204英语（二）③302数学（二）④408计算机学科专业基础` 或单元格内换行 → 4 个科目（代码 + 名称）；“408计算机学科专业基础综合”和“408计算机学科专业基础”都是 408
- 专业代码在单元格内换行（华师汇总表）→ 合并
- 学校 / 学院别名：中大 / 中山 / SYSU；华工 / 华南理工 / SCUT；暨大 / 暨南 / JNU；华师 / 华南师范 / SCNU

### 3.4 结构化库（`data/kaoyan.db`，SQLite）

建议表（可调整，但“每个数值带来源、年份、口径、抽取方式、是否人工核对”不能少）：

- `schools(id TEXT PK, name, short_name, domains_json)`；`colleges(id PK, school_id, code, name, site)`
- `documents(id TEXT PK, school_id, college_id, title, publish_date, intake_year, doc_type, format, page_url, attachment_url, article_id, local_path, sha256, bytes, pages, has_table, contains_personal_data, status, first_seen, last_seen, parent_doc_id)`：首批直接从 `sources.json.documents[]` 导入，`id` 用其 `doc_id`
- `programs(id PK, school_id, college_id, code, name, degree_type, study_mode, pool_code, is_boundary, notes)`，唯一键 `(school_id, college_id, code, study_mode)`
- `directions(id, program_id, year, code, name, source_doc_id)`
- `exam_subjects(id, program_id, year, slot, code, name, status('known'|'unknown'|'no_exam'), unknown_reason, source_doc_id, page, extraction_method, verified)`
- `plans(id, program_id, year, kind, value, value_text, is_upper_bound, pool_scope, definition, source_doc_id, page, evidence_text, extraction_method, verified)`
  - `kind` 至少包括：`catalog_total`（目录总计划，含推免）、`tm`（推免数）、`rules_total`（学院复试细则总计划）、`public_exam`（公开招考 / 统招计划）、`available_exam`（学校统考可用计划）、`college_exam_plan`（学院通知的统考计划）、`special_veteran`、`special_minority`
- `score_lines(id, school_id, program_id NULL, year, scope('school_baseline'|'college'|'special_veteran'|'special_minority'), discipline_code, total, politics, foreign_lang, subject1, subject2, raw_text, definition, source_doc_id, page, evidence_text, extraction_method, verified)`
- `admission_stats(id, program_id, year, kind('retest_count'|'admit_count'|'score_min'|'score_max'), value, source_doc_id, extraction_method)`：**只存统计，不存任何考生个人信息**
- `crawl_runs(id, started_at, finished_at, school_ids, mode, status, stats_json, error)`
- 视图 `v_program_facts`：一个专业一行，汇总最新年份的各口径数值和来源
- 冲突处理：同一 `(program, year, kind)` 有多个来源时**全部保留**，不覆盖；查询时按口径分别返回。`extraction_method` 取值：`manual_seed` / `seed_note_regex` / `rule` / `llm` / `ocr`；`ocr` 和 `llm` 产出默认 `verified=0`

### 3.5 检索（RAG）

- 考研索引与企业演示索引分开（例如 `data/chroma_kaoyan/` + collection `kaoyan_docs`；新目录要加进根 `.gitignore`）。企业演示（`scripts/ingest_demo.py`、`scripts/smoke_chat.py`）必须照常可用。
- chunk 元数据：`doc_id, school, college, intake_year, doc_type, page, title, url`；BM25 路径和 Chroma `where` 都支持按 school / year / doc_type 过滤。
- 表格感知切块：表格按行切，每块重复表头和表名（例如“中大计算机学院 2026 复试分数线｜专业代码 085404｜总分 379｜政治 50…”），避免数字脱离列名。
- `rag_search` 增加可选参数 `school`、`year`、`doc_type`，不传时行为和现在一样。
- 叙述性问题（复试形式、同等学力加试、学费学制、推免办法）走 RAG；**数字类问题优先走结构化工具**，RAG 只作补充证据。

### 3.6 Agent：工具、流程、提示词

保留 `plan → act → reflect → retry|finalize` 和工具上限 5。新增工具（`src/doc_agent/tools/kaoyan.py`，在 `registry.get_tool_list()` 注册），全部返回 JSON，并且每条事实都带 `source`（doc_id、标题、URL、页码、年份、口径）：

- `search_programs(school?, college?, code?, name_kw?, degree_type?, study_mode?, exam_subject?, is_408?, min_public_plan?, year?)`：结构化筛选。自然语言（“考408且统招>20”）由 LLM 转成参数。**“统招”取值规则**：优先用明确的 `public_exam` / `college_exam_plan` / `available_exam`（逐条标口径）；没有时用 `catalog_total − tm`（两个都是精确值才算）；`tm` 是上限值时只能得出下限（如 “≥13”），不能当作满足 “>20”；取不到的放进返回结果的 `unknown` 列表并说明原因，**不要悄悄丢掉**。
- `get_score_lines(school, code?, college?, year=2026, include_special=True)`：返回学院线、学校基本线、专项线（退役 / 少干），每条标 `scope`。
- `get_exam_subjects(school, code, college?)`：返回科目；未知时返回 `status="unknown"` 和原因（例如华工目录被统一认证拦截）；仅招推免的返回 `no_exam`。
- `compare_programs(filters | program_ids, fields)`：多校 / 多专业对比表。
- `get_document(doc_id)` / `list_sources(school?, doc_type?, year?)`：引用元数据。
- 导出继续用 `export_excel` / `export_markdown`，考研行转换时带“年份 / 口径 / 来源URL / doc_id”列。

流程改动：
- `act_node` 第 0 轮：识别意图（学校别名、`\d{4}[0-9A-Z]{2}` 专业代码、“复试线 / 分数线”、“招多少 / 计划 / 统招 / 推免”、“考什么 / 408”、“对比”、“筛选 / 哪些”），先调对应结构化工具；叙述类问题才用现在的 `rag_search(goal)` 起步。
- `_run_tool`：把新工具输出转成 `citations`（`doc_name/title`、`page`、`url`、`doc_id`、一句证据文本），让 `finalize_node`、`citations_to_excel_rows`、`_force_export` 都能用。
- 数字校验（放在 `guardrails.py`，要有单测）：答案里出现的每个数字（年份、专业代码、科目代码除外）都必须能在证据里找到；找不到就重生成一次，还不行就删掉该数字并写“依据不足”。
- `reflect_node`：数字类问题如果还没有结构化工具证据，要求重试并提示调哪个工具；已经返回 `unknown` 的不要反复重试。
- 提示词（`prompts.py`）必须写进这些规则：只根据工具证据回答；每个数字标年份和口径；不同口径的数并列给出，不要挑一个；2026 和 2027 不能混；缺失就说“官方资料中未取得”，并说明原因和去哪里核实；华工目录缺失、暨南 0812 统筹这类情况要主动说明；边界项（中大 765 的 085400 考 884）要提示；**不输出任何考生个人信息**，涉及名单只给人数和分数区间；第三方聚合站的数据不采信。

### 3.7 API

现有接口全部保持可用。新增（`api/routes_kaoyan.py`，统一错误信封）：

- `GET /v1/programs`：查询参数与 `search_programs` 一致；返回专业及各口径事实和来源
- `GET /v1/programs/{program_id}`
- `GET /v1/score-lines?school=&code=&year=`
- `GET /v1/documents?school=&doc_type=&year=`、`GET /v1/documents/{doc_id}`：只返回元数据；`contains_personal_data=1` 的文档不提供内容下载
- `POST /v1/crawl`：`{schools, mode: "probe"|"list"|"full", dry_run: true, max_pages}` → `run_id`（BackgroundTasks）；`GET /v1/crawl/{run_id}`
- `/health`：加可选字段 `kaoyan_db`、`programs`、`documents`
- `POST /v1/ingest` 自动支持新格式，`paths` 可以是 `data/kaoyan/raw`
- 不做鉴权（沿用 README“仅本地演示，不要暴露到公网”），但 `/v1/crawl` 默认 `dry_run=true`

### 3.8 改名与品牌（风险最小的做法）

- **仓库名和包名 `doc_agent` 暂时不改**：`tests/`、`scripts/`、`frontend/`、`PYTHONPATH=src` 的启动命令都依赖它。
- 本次只改：FastAPI 标题 / 描述、`__version__` 升到 `0.4.0`（`api/__init__.py` 改为引用它）、README 顶部介绍和“接口”表、前端标题和演示问句、`.env.example` 新配置。企业演示当作“通用文档模式”保留。
- 包改名（例如 `kaoyan_agent`）放到最后单独一个 PR，是否做由我决定；要做就留兼容 shim。GitHub 仓库改名我自己在网页上操作，你不要做。

---

## 4. 数据与种子：怎么用 `data/kaoyan/`

- `majors.csv`（UTF-8 BOM，37 行，所有列都是字符串）是**人工核对过的 golden 数据**，字段含义见 `data/kaoyan/README.md` 第 4 节。注意：`拟招生人数(总)` 是目录口径（含推免）；`其中推免人数` 可能是 `≤N` 或 `（0812合计≤19）`；`是否408` 可能是 `未知（目录不可达）` / `否（仅招推免）`；`2026复试线总分` 华工是学校基本线；`来源URL` 多个用 ` ; ` 分隔，个别夹着中文括号说明；大量口径信息在 `备注`。
- `sources.json`：`schools[]`（域名、列表页、目录系统、URL 模式、访问问题）→ 生成 `collect/sites.json` 和 `schools/colleges`；`documents[]`（97 条，含 sha256、`contains_personal_data`、`commit_to_git`）→ 直接导入 `documents` 表。
- `raw/`：按学校分目录的原始文件；`raw/manifest.csv` 有 sha256。28 个本地专用文件（个人信息 / 超过 3MB）在别的机器上可能不存在，**测试遇到缺失文件要 `pytest.skip`，不能失败**。
- `scripts/build_majors.py`：只是 golden 数据的出处说明，别再手工维护；`scripts/scnu_zsml.py`：华师目录回发的参考实现。
- 种子规则（`kaoyan/seed.py` + `scripts/seed_kaoyan.py`，可重复执行，幂等）：
  - 列 → 事实：`拟招生人数(总)`→`plans.catalog_total`；`其中推免人数`→`plans.tm`（`≤`→上限，`（0812合计≤19）`→一级学科合计上限）；科目 1–4 → `exam_subjects`（空且 `是否408` 含“未知”→`unknown`，原因取自备注；中大 083900 → `no_exam`）；`2026复试线总分` + 单科 → `score_lines`（华工 → `school_baseline`，其余 → `college`）；年份取 `数据年份` 的前 4 位（复试线固定 2026）。
  - 推免数默认口径：中大 = 学院 2026 复试细则“已招推免”；华师 = 目录“总(推免)”；暨南 = 2027 推免复试方案（多为上限）。写进 `definition`。
  - 来源：`来源URL` 按 ` ; ` 切开，每段去掉第一个中文 / 英文括号之后的说明（华工那段带“（目录系统 … 未取得）”），再与 `sources.json` 的 `page_url` / `attachment_url` 精确匹配成 `source_doc_id`（已核对：现有 37 行全部能匹配上）。以后匹配不上的，新建一条只有 URL 的 document（`status='seed_only'`）。
  - `备注`：整段存进 `programs.notes`；再用**窄正则**抽出下面几类。写法很不统一，先把 37 行备注全部过一遍、列出所有变体，再写正则，每个变体都要有对真实字符串的单测：
    - 学院细则计划：“学院细则为总13/已招推免9/公开4”“学院2026复试细则为总15/已招推免7/公开8”“学院2026复试细则调整为总214/已招推免165/公开招考49”“学院细则（图片）为总53/已招推免30/公开23”“学院细则：总40/推免0/公开40”“学院细则总82/已招推免51/公开31”“推免数取自学院2026复试细则（总65/已招推免55/公开招考10）”
    - 专项线：“退役线288（30/30/48/48）”“另退役2（线296）”“退役大学生计划3名（线323）”“另有退役大学生计划2名，复试线339”“少数民族骨干计划4名（线303）”“少数民族骨干1名，线280（35/35/53/53）”“少干1名线375”
    - 华工计划：“统考计划35（含基地11、广东石油化工学院联培3）”“学校统考可用计划PDF写21”“统考可用计划PDF也写18”“统考可用计划22（2025-10-22）”“统考招生计划28”
    - 华师：“复试方案中计划为72（推免5，含联培专项）”“复试方案：拟招47、已招推免2”
    - `extraction_method='seed_note_regex'`；抽不到的留在 notes，不要猜。
  - 种子数据 `verified=1`（人工核对），但来源仍指向官方文档。
- Golden 问答：新建 `data/gold/kaoyan_qa.json`（格式参照 `data/gold/sample_qa.json`，每条加 `must_include`、`must_not_include`、`expect_unknown`、`sources`），内容来自第 6 节。`sample_qa.json` 不要动。

---

## 5. 分阶段实施计划（每阶段一个 PR 的大小）

每个阶段结束都要：`PYTHONPATH=src pytest -q` 全绿（旧测试 + 新测试）；更新 `task_plan.md` / `progress.md` / `docs/kaoyan_phaseN_notes.md`；新依赖写进 `requirements.txt`（`requirements-embedding.txt` 里的核心依赖列表也同步）。

**K0 计划**（不写代码）：第 0 节的阅读、基线、计划。验收：我确认计划。

**K1 种子库 + golden（不联网、不调 LLM）**
- 新增：`src/doc_agent/kaoyan/{__init__,schema.sql,db.py,models.py,normalize.py,seed.py}`、`scripts/seed_kaoyan.py`、`scripts/verify_kaoyan_bundle.py`（按 manifest 校验 sha256，缺失的本地专用文件只警告）、`data/gold/kaoyan_qa.json`、`tests/test_kaoyan_normalize.py`、`tests/test_kaoyan_seed.py`；`config.py` / `.env.example` 加 `KAOYAN_DB`、`KAOYAN_DATA_DIR`；`data/README.md` 加指向说明。
- 验收：种子后 37 个 program；`documents` 97 条（全部来自 `sources.json`，不应出现 `seed_only`）；以下断言成立：中大 670 085404 → college 线 379（50/50/60/60），`source_doc_id` 指向 `https://cse.sysu.edu.cn/article/3475`；暨大 052 085412 → 348、`catalog_total` 62（2027）、`tm` 25；华师 019 085404 → 348 + `special_veteran` 288（30/30/48/48）；华工 085404 → `exam_subjects.status='unknown'`、线 `scope='school_baseline'` 305、`college_exam_plan` 35 和 `available_exam` 21 同时存在；暨大 010 的 081201–081203、0812Z3 → `catalog_total` 为空、`tm` 为一级学科合计上限 19；中大 757 083900 → `no_exam`；`normalize` 覆盖 `48(17)`、`同上`、`≤41`、科目串拆分。

**K2 多格式解析层**
- 新增 / 修改：`ingest/tables.py`、`ingest/ocr.py`（先实现 `none`）、`ingest/loaders.py`（html / xlsx / xls / 图片分发，扫描 PDF 识别）、`collect/attachments.py`（附件发现可以先在这里实现，K6 复用）；依赖：`pdfplumber`、`beautifulsoup4`、`lxml`、`xlrd`。
- 测试（夹具用 `data/kaoyan/raw/` 里已入库的文件；每个断言值都要先打开文件确认，并和 `majors.csv` 对照）：
  - `raw/sysu/sysu_cse_2026_复试录取实施细则.html` → 表格里有 `085404 | 计算机技术（全日制） | 69 | 不分方向 | 379 | 50 | 50 | 60 | 60`
  - `raw/jnu/jnu_2027_硕士招生专业目录_202607.html` → 专业行 `085412网络与信息安全(专业学位)` 人数 62；学院行 `052网络空间安全学院` 拟招生总人数 116；010 学院备注里有“计算机科学与技术指标为24个”
  - `raw/scnu/scnu_2026_招生专业目录_Zsml_View_019_p1.html` → 081200 的 `48(17)` 解析为 48 / 17，085404 的 `50(4)` 解析为 50 / 4
  - `raw/scnu/scnu_2027_推免硕士招生专业目录.xls` → ffill 之后，019 计算机学院下有 085410 人工智能、推免 3；041 下 085410 推免 8
  - `raw/sysu/sysu_2026_复试基本分数线.pdf` → pdfplumber 能抽出“工学[08] 280 45 60”这一行
  - `raw/sysu/sysu_sece_2026_复试录取实施细则.html` → 解出 1 张 data URI PNG，sha256 等于 `raw/sysu/sysu_sece_2026_复试分数线_内嵌base64图1.png` 的 sha256（`19cedf27…6209`）
  - `raw/scut/scut_cs_2026_统考入围复试名单_20260316.html` → 发现 2 个 `pdfsrc` 附件，文件名分别是“2026学硕.pdf”“2026专硕.pdf”
  - `iter_source_files` 覆盖新后缀，但仍跳过 `.csv`；旧的 `tests/test_docx_loader.py` 不改也要通过
- 验收：`POST /v1/ingest` 能导入 `data/kaoyan/raw`，失败文件出现在 `docs_failed` 里且有原因；图片 / 扫描件在 `ocr_backend=none` 时标记为 `needs_ocr`，不报错。

**K3 检索元数据 + 考研索引**
- 修改：`ingest/chunking.py`、`rag/store.py`、`rag/query_expand.py`、`tools/registry.py`（`rag_search` 加过滤参数）；新增 `scripts/ingest_kaoyan.py`。
- 测试（纯 BM25，不需要 Ollama）：按 `school='jnu'` 过滤只返回暨南文档；按 `year=2027` + `doc_type='catalog'` 能命中 2027 目录；表格块里保留表头；企业语料的旧行为不变（`scripts/smoke_chat.py` 在有 key 时仍 3/3）。

**K4 结构化抽取**
- 新增：`kaoyan/extract/`（每类文档一个规则抽取器：JNU 目录 HTML、SCNU 目录系统 HTML、SCNU 推免 xls、SYSU 学院细则 HTML 表、SYSU 校线 PDF、SCUT 学院计划 HTML 表；以及 LLM 兜底：JSON 输出，必须给出证据原文片段，否则丢弃）、`scripts/extract_kaoyan.py`、`scripts/eval_extraction.py`（抽取结果 vs 种子，输出 `docs/kaoyan_extraction_report.md`）。
- 验收：已入库文字类文档里、`majors.csv` 覆盖到的事实，规则抽取与种子**完全一致**（例如中大各学院复试线、暨南 2027 目录计划、华师目录总(推免)、华师 2027 推免数）；每条抽取事实都有 `source_doc_id` + `evidence_text`；冲突只记录不覆盖；单测不调真实 LLM（用假模型）。

**K5 Agent 工具、提示词、API**
- 新增 / 修改：`tools/kaoyan.py`、`tools/registry.py`、`agent/prompts.py`、`agent/nodes.py`、`agent/guardrails.py`（意图识别 + 数字校验）、`api/routes_kaoyan.py`、`api/schemas_kaoyan.py`、`api/__init__.py`、`scripts/smoke_kaoyan.py`（读 `data/gold/kaoyan_qa.json`，判分方式参考 `scripts/smoke_chat.py` 的归一化）。
- 测试：工具函数单测（直接查 `kaoyan.db`，不调 LLM）；数字校验单测；新接口的 TestClient 测试（含 404 / 422 错误信封）；`tests/test_api_errors.py` 不改仍通过。
- 验收：`smoke_kaoyan.py` 在配置 `LLM_API_KEY` 时：数值类用例 ≥ 90% 通过；**“必须回答未知”的用例 100% 通过**（不能编）；PII 用例 100% 拒绝；每个答案都有引用。

**K6 采集层**
- 新增：`collect/*`、`scripts/crawl_kaoyan.py`（`--school jnu --mode probe --dry-run`）、`POST /v1/crawl`、`GET /v1/crawl/{run_id}`。
- 测试：全部用 `httpx.MockTransport`（限速、robots、重试、去重、SCUT 多栏目 ID 去重、SYSU 分页 URL 修正、SCNU WebForms 回发参数、JNU 年份探测、`yanzhao.scut.edu.cn` 302 → 标 `blocked` 且不重试）。
- 验收：我手动跑一次真实 `probe`（每校只看列表第 1 页，间隔 ≥3 秒），把结果和耗时写进 `progress.md`；新发现的文档进入 `documents`，已有的按 sha256 识别为未变化。

**K7 OCR / 视觉 + 前端 + 文档**
- `ingest/ocr.py` 接 `rapidocr`（可选依赖 `requirements-ocr.txt`）和 `vision`（OpenAI 兼容多模态）；处理 6 张图片表格（扫描名单只统计人数，不入库个人信息）；OCR 产出 `verified=0`，和种子对上才能标为已核对。
- 前端：新增“专业筛选”页（调 `/v1/programs`，表格显示口径和来源链接），演示剧本换成第 6 节的问题；`frontend/api_client.py` 新方法配测试。
- README / `data/README.md` / `docs/` 更新；可选：包改名（单独 PR，等我决定）。

---

## 6. 验收用例（期望值都已对照 `data/kaoyan/majors.csv` 核对过）

写进 `data/gold/kaoyan_qa.json`。每条答案都必须带来源（文档标题或 URL）和数据年份。

| # | 问题 | 期望（必须包含） | 不得出现 / 注意 |
|---|---|---|---|
| 1 | 中大计算机学院 085404 的 2026 复试线是多少？ | 379；单科 政治50 / 外语50 / 业务课一60 / 业务课二60；学院线；来源 cse.sysu.edu.cn/article/3475；可补充学校电子信息[0854]基本线 300/50/60 | 不能把 300 当成学院线 |
| 2 | 暨大网络空间安全学院 085412 的 2026 复试线？ | 348（35/35/53/53），学院线（暨南不设统一校线）；来源 2026 各学院复试方案（yz.jnu.edu.cn/2026/0320/c33059a852118）；可补充 2027 目录计划 62、推免 25 | 年份不能写成 2027 复试线 |
| 3 | 华师计算机学院 085404 复试线多少？ | 348；另有退役大学生士兵计划线 288（30/30/48/48） | 不能说复试线是 288（第三方摘要犯过这个错） |
| 4 | 中大网络空间安全学院 083900 考什么、复试线多少？ | 仅招收推免生，没有统考科目和复试线（2026：总 15 / 推免 15） | 不能编科目或分数线 |
| 5 | 华工计算机学院 085404 初试考什么？考不考 408？ | **未知**：官方目录系统 yanzhao.scut.edu.cn 需统一认证，未取得；可补充 2026 复试线为学校基本线 305（08 工学）、学院统考计划 35（含基地 11、联培 3）与学校统考可用计划 21 两种口径 | 不能回答“考 408”或任何具体科目（非官方聚合站说法不采信） |
| 6 | 华工 140500 智能科学与技术考 408 吗？复试线？ | 考（101 / 201 / 301 / 408），来源是未来技术学院 2025-06 调整招生专业的通知图片，通知注明以正式目录为准；复试线为学校 14 交叉学科基本线 320（单科 50 / 75） | 不能把 320 说成学院线 |
| 7 | 暨大 081203 计算机应用技术 2027 招多少人？ | 不单独列人数：0812 按一级学科统筹，2027 目录合计 24 人（含推免），推免 ≤19；可补充 2026 目录里 081203 为 6 | 不能编出 081203 的 2027 人数 |
| 8 | 中大人工智能学院 081200 招多少人？ | 两个口径都列：2026 目录 9；学院 2026 复试细则 总 15 / 已招推免 7 / 公开 8 | 不能只给一个数 |
| 9 | 华师人工智能学院 085410 计划多少？ | 目录 66（推免 5）；复试方案 72（推免 5，含联培专项） | 不能只给一个数 |
| 10 | 中大软件工程学院 085405 推免多少、公开招考多少？ | 学院细则：总 53 / 已招推免 30 / 公开 23；目录计划 37 | 不能把 30 / 23 写反（第三方站点写反过） |
| 11 | 哪些专业考 408、全日制、统招 > 20？ | 必须包含（标年份和口径）：中大 670 085404（2026 目录 210 − 推免 165 = 45；细则公开招考 49）；暨大 052 085412（2027 目录 62 − 推免 25 = 37）；华师 019 081200（48 − 17 = 31）；华师 019 085404（50 − 4 = 46）；华师 041 085405（50 − 5 = 45）；华师 041 085410（66 − 5 = 61）。华工单独列出并标口径：085404 学院统考计划 35 / 学校统考可用计划 21，085405 统考可用计划 21，140500 统考可用计划 22 / 学院统考计划 28；华工 081200 / 085404 / 085405 的初试科目未知，要说明 | 暨大推免是“≤N”上限的专业（如 010 085404：54 − ≤41 → 统招 ≥13）不能算作“>20”；不能漏掉华工而不解释 |
| 12 | 对比四校 085404 的 2026 复试线 | 表格：中大 670 379、中大 771 335、华工计算机学院 305（学校基本线）、暨大 010 318、华师 019 348、华师 046 340 | 华工必须标注是校线 |
| 13 | 中大 2027 年 085404 招多少人？ | 2027 简章 / 目录截至 2026-09-25 未发布（2026 版是 2025-09-26 发布的）；给出 2026 目录 210（学院细则调整为总 214 / 已招推免 165 / 公开招考 49）并标明是 2026 | 不能把 2026 的数说成 2027 的 |
| 14 | 华师有没有网络空间安全学硕（0839）？ | 当前数据范围内华师没有 0839；019 计算机学院 085404 下有“02 网络空间安全”方向 | — |
| 15 | 暨大智能科学与工程学院 0812Z3 统考招几个？ | 2027 目录 10，推免 ≤10（上限），推免招满的话统考可能为 0；2026 统招计划 5 | 不能说“统考 10 人” |
| 16 | 中大电子与通信工程学院 085400 的人工智能方向考 408 吗？ | 不考，初试考 884 信号与系统；这是边界项（只有“10 人工智能”方向和计算机相关）；2026 复试线 382（60/60/85/85） | — |
| 17 | 帮我查华工计算机学院拟录取名单里有没有某某某 | 拒绝提供个人信息；只能给统计：2026 统考拟录取 085404 36 人、081200 23 人（含南特 5） | 不输出任何姓名、考生编号、个人成绩 |
| 18 | 把四校 085404 的复试线和计划导出 Excel | `data/exports/` 下生成 xlsx；列至少有 学校、学院、专业代码、年份、复试线、线的口径、计划、计划口径、来源URL；华工计划 / 科目为空的格子写“未取得”并在备注说明 | 空格子不能填猜测值 |

---

## 7. 约束（全程遵守）

1. **不编数字**。每个数字都要有官方来源（文档 + URL，能给页码就给页码）、年份和口径。取不到就明确说未知 / 未取得，并说明原因。第三方聚合站、搜索摘要只能当线索，不能当答案。
2. **总是引用**：答案、导出、API 返回的事实都带来源。
3. **礼貌抓取**：遵守 robots.txt；同 host 最小间隔 ≥3 秒、串行；有页数上限；不绕过登录或验证码（华工 yanzhao 被拦就标 `blocked`，走手动导入）；研招网 yz.chsi.com.cn 的签名接口不要硬爬。
4. **个人信息**：名单类文件只做统计；不在答案、日志、导出、测试快照里输出姓名 / 考生编号 / 个人分数；这类文件不入库（`data/kaoyan/.gitignore` 已列出），新下载的同类文件也要进忽略规则或 cache 目录。
5. **密钥只放 `.env`**，不要提交；新配置写进 `.env.example`（值留空或示例值）。
6. **不提交大文件**：单文件 >3MB、数据库、索引、缓存、OCR 缓存都不入库（根 `.gitignore` 已忽略 `data/chroma/`、`data/memory.db`、`data/exports/`、`*.db`；新目录记得补）。
7. **测试保持全绿**；新测试不连外网、不调真实 LLM（用假模型 / MockTransport）；本地专用夹具缺失时 skip。
8. **兼容**：现有 API 契约、`load_file` 接口、企业演示流程（`scripts/demo_repro.sh`）不能坏。
9. **记录**：按仓库现有习惯更新 `task_plan.md`、`progress.md`、`findings.md`（外部网页内容只写 findings，不写进 task_plan 的指令部分）和 `docs/kaoyan_phaseN_notes.md`。
10. 大改动之前先说明方案；不确定的数据问题问我，不要自己编。不要 push、不要改 GitHub 仓库设置，提交前给我看 diff 摘要。

---

## 8. 已知难点速查（详见 `data/kaoyan/sources.md` 第 5 节）

1. 扫描 PDF：华工 2026 拟录取名单（不含推免）29MB / 113 页，没有文字层。
2. 图片表格：华工校线（jpg）、华工 140500 初试科目（jpg）、华工 2027 科目调整（png）、中大软件工程学院分数线和计划（png）、中大电子与通信学院分数线（HTML 内嵌 base64）。
3. 合并单元格：华工统考可用计划 PDF 学院列、中大分数线 PDF 竖排“学/术/学/位”、暨南复试方案 xlsx 多行表头 + 一个 sheet 里 3 张表、华师 2027 推免 xls 前 6 列。
4. 一格多值：中大目录科目同格换行；华师“48(17)”和“同上”；华师汇总表专业代码格内换行；暨南推免 PDF 文字被截断。
5. 口径不一致：中大目录 vs 学院细则；华工统考可用计划 vs 学院统考计划；华师复试方案 vs 目录；暨南 0812 一级学科统筹、推免“≤N”。
6. 版面串行：`pdftotext -layout` 下中大目录学院归属错位，必须按坐标抽表。
7. 附件发现：WebPlus `pdfsrc` 播放器、UUID 文件名、中大分页链接错误、暨南空栏目 / 410、同一文章多个栏目 ID。
8. 访问受限：yanzhao.scut.edu.cn 统一认证；研招网接口签名。
9. 格式杂：html、pdf、xlsx、xls（BIFF）、doc/docx 表单、jpg/png。
10. 第三方错误：iqihang 写反中大 085405 推免 / 公开数；搜索摘要把华师 085404 线写成 288；华工 081200 考 408 只见于非官方来源。

---

现在开始：执行第 0 节，给出 K0–K7 的计划（写进 `task_plan.md`，并在回复里列出每阶段的文件清单和验收标准），然后停下来等我确认。
