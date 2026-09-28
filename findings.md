# 发现与决策

## 需求
- 基于 LangGraph 的企业文档 Agent 后端
- 能力：任务规划、工具调用、状态记忆、RAG、自我校验
- 输入：自然语言复杂指令；数据：本地私有 PDF/Word 等
- 输出：自然语言总结、结构化表、Markdown/Excel 报告
- 对外：FastAPI；可视化 Streamlit 可选后置
- 性能目标（PRD）：100 页解析+向量化 ≤10s；普通问答 ≤3s；复杂任务 ≤15s；单次最多 5 次工具调用

## 研究发现

### DeepSeek Embedding 说明（2026-09-05）
- 官方 DeepSeek API 主要提供 chat（`deepseek-chat` 等），**无稳定官方 Embedding 端点**。
- 已切换为本地 Ollama：`qwen3-embedding:0.6b` via `http://127.0.0.1:11434/v1`，写入 Chroma。
- 未配置 `EMBEDDING_BASE_URL` 时回退 BM25。

### 年报召回优化（2026-09-05）
- **问题：** 纯稠密检索对「主营业务 / 主要风险」类问句易落到审计、财报页。
- **根因：** 语义近邻 ≠ 章节关键词命中；BM25 对「主营业务分行业」「可能面对的风险」更稳。
- **方案：** `hybrid(dense RRF + BM25)` + 意图查询扩展 + 文档名启发式过滤 + 同意图短语加权。
- **结果：** 复测可召回 p9/p15/p22/p56 等页，并产出带页码的业务与四类风险摘要。
- **实现：** `src/doc_agent/rag/query_expand.py`、`store.py`；工具 `rag_search(doc_name=...)`。

### 阶段 4 二期落地（2026-09-06）
- 双层记忆：`SessionMemory` + SQLite `TaskStore`（`MEMORY_DB=data/memory.db`）。
- 图增加 `reflect`；`should_retry` 且未达 `MAX_TOOL_CALLS` 时回 `act`。
- 新工具：`compare_docs`、`extract_fields`、`export_markdown`、`export_excel`（openpyxl）。
- API：`task_id` / `exports` / `reflection`；`GET /v1/tasks/{id}`、`GET /v1/sessions/{id}`。
- 说明：`docs/phase4_notes.md`。

### 阶段 5 工程化（2026-09-06）
- `POST /v1/chat/async` + BackgroundTasks；任务状态 queued/running/done/error。
- 统一错误模型；`ChatOptions.max_tool_calls` 经 contextvar 注入。
- `tests/` + `scripts/demo_repro.sh` + `scripts/perf_baseline.py`。
- Streamlit 明确后置。说明：`docs/phase5_notes.md`。

### 现有仓库资产
- PRD：`企业文档智能处理Agent 产品需求文档（PRD）.md`
- 演示数据：年报 PDF（本地，默认不入库）+ 可控 txt + `data/gold/sample_qa.json`
- 代码：`src/doc_agent/`（FastAPI + LangGraph + hybrid RAG + memory + async）
- 验收：`docs/backend_verification_result.md`、`docs/phase4_retest_result.md`、`docs/phase5_notes.md`
- 下载脚本：`scripts/download_demo_data.py`

### 后端职责边界
| 在范围内 | 不在一期后端范围 |
|----------|------------------|
| ingest / RAG / Agent / 记忆 / FastAPI | Streamlit UI |
| PDF、txt、docx 解析 | OCR 扫描件、图片解析 |
| Chroma 本地库 | 企业 OA/邮件对接 |
| 同步 chat + 可选后台任务 | 生产级多租户鉴权 |

### 推荐后端架构

```
client / curl / 未来 Streamlit
        │
   FastAPI (api/)
   · POST /v1/ingest
   · POST /v1/chat
   · GET  /v1/sessions/{id}
   · GET  /v1/tasks/{id}          # 二期+
   · GET  /health
        │
   Application services
   · IngestService
   · AgentService
   · MemoryService
        │
   LangGraph Runtime (agent/)
   plan → route → act(tools) → reflect → finalize
        │
   tools/     ingest/     rag/     memory/
   parse      chunk       chroma   session (短期)
   search     embed       retriever task_trace (SQLite)
   extract    store
   summarize
   export
        │
   data/raw  ·  data/chroma  ·  data/memory.db  ·  data/exports
```

### LangGraph 状态建议（AgentState）
```python
class AgentState(TypedDict):
    messages: list          # 对话消息
    user_goal: str          # 原始指令
    plan: list[str]         # 子任务队列
    current_step: int
    tool_results: list[dict]
    citations: list[dict]   # 检索片段引用
    reflection: str | None
    iteration: int          # 工具调用轮次，上限 5
    final_answer: str | None
    session_id: str
    status: str             # planning|acting|reflecting|done|error
```

### 节点与边
1. `plan`：LLM 拆解子任务；简单闲聊可直接 `finalize`
2. `route`：无工具需求 → finalize；否则 → act
3. `act`：绑定工具（search / parse / extract / summarize / export）
4. `reflect`（二期）：完整性检查；不足且 iteration<5 → act；否则 finalize
5. `finalize`：汇总答案 + 写记忆

一期可把 reflect 做成透传，边先写好以免二期改图。

### 工具清单（后端）
| 工具 | 一期 | 二期 | 说明 |
|------|------|------|------|
| `rag_search` | ✓ |  | Chroma 相似度检索，返回带 source 的 chunks |
| `list_documents` | ✓ |  | 列出已入库文档 |
| `parse_document` | ✓ |  | 按路径解析全文/分页（大文件按页） |
| `extract_fields` | 部分 | ✓ | LLM+检索抽取结构化 JSON |
| `compare_docs` | | ✓ | 多文档字段对比 |
| `summarize` | ✓ |  | 基于 citations 汇总 |
| `export_markdown` | | ✓ | 写 `data/exports/*.md` |
| `export_excel` | | ✓ | pandas → xlsx |

### FastAPI 契约（草案）

**POST /v1/ingest**
```json
{ "paths": ["data/raw/annual_reports"], "reindex": false }
```
→ `{ "docs_indexed": 3, "chunks": 1200, "collection": "enterprise_docs" }`

**POST /v1/chat**
```json
{
  "session_id": "optional-uuid",
  "message": "对比茅台和五粮液2024年报的营收与净利润",
  "options": { "max_tool_calls": 5, "temperature": 0.2 }
}
```
→ `{ "session_id", "answer", "citations", "trace": [...], "exports": [] }`

**GET /health** → `{ "status": "ok", "llm": "configured|missing", "chroma": "ok" }`

### 配置（环境变量）
```
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com/v1   # 或通义兼容地址
LLM_MODEL=deepseek-chat
EMBEDDING_MODEL=text-embedding-v3          # 随供应商调整
CHROMA_DIR=data/chroma
RAW_DIR=data/raw
MEMORY_DB=data/memory.db
MAX_TOOL_CALLS=5
CHUNK_SIZE=500
CHUNK_OVERLAP=80
TOP_K=5
```

### 建议包结构
```
src/doc_agent/
  __init__.py
  config.py
  api/
    app.py
    routes_ingest.py
    routes_chat.py
    schemas.py
  ingest/
    loaders.py      # pdf/docx/txt
    chunking.py
    pipeline.py
  rag/
    embeddings.py
    store.py
    retriever.py
  agent/
    state.py
    graph.py
    nodes.py
    prompts.py
  tools/
    registry.py
    rag_search.py
    parse.py
    extract.py
    summarize.py
    export.py
  memory/
    session.py
    trace.py
  llm/
    factory.py      # Chat/Embed 统一创建，可切换供应商
scripts/
  download_demo_data.py
  ingest_demo.py
  smoke_chat.py
tests/
  test_chunking.py
  test_retriever.py
  test_graph_smoke.py
data/
  raw/ chroma/ gold/ exports/
task_plan.md  findings.md  progress.md
requirements.txt  .env.example  README.md
```

### 一期验收标准（后端）
1. `ingest_demo.py` 能把 `data/raw` 写入 Chroma 且可查询
2. `POST /v1/chat` 对 gold 三条可控问答至少 2/3 命中关键事实
3. 年报类问题能返回带文件名/页或 chunk id 的 citations
4. 工具调用失败不导致进程崩溃（捕获并写入 trace）
5. 无 API Key 时 `/health` 明确报告，不静默挂死

### 已知风险
| 风险 | 缓解 |
|------|------|
| 年报 100–200+ 页，向量化可能 >10s | ingest 异步/CLI 预热；chat 不现场全量向量化 |
| 复杂任务 ≤15s 偏紧 | 限制 top_k、截断上下文、reflection 可关 |
| PDF 表格抽取差 | 一期接受纯文本；关键指标靠 RAG+LLM 抽取 |
| API 费用与限流 | 缓存 embedding；demo 集合固定 |
| 依赖版本漂移 | 锁 LangGraph/LangChain 小版本 |

## 技术决策
| 决策 | 理由 |
|------|------|
| Python 3.11+ + FastAPI + LangGraph + Chroma | 对齐 PRD，生态成熟 |
| LLM：DeepSeek `https://api.deepseek.com` + `deepseek-chat` | 用户指定 |
| Embedding：本地 Ollama `qwen3-embedding:0.6b` | DeepSeek 无官方 Embedding；本机已有模型 |
| 检索：hybrid（dense RRF + BM25）+ 年报章节扩展 | 人工验证暴露纯向量对长年报章节召回不足 |
| 未配置 Embedding 时用 BM25 词法检索 | 无向量服务时仍可跑通 |
| 一期只解析 PDF + txt | 用户确认；docx 二期再加 |
| API Key 写入 `.env` 并 gitignore | 防泄露 |
| 一期同步 `/chat`，重任务用预 ingest | 实现简单，演示稳定 |
| 记忆二期用 SQLite | 零运维，够用轨迹回溯 |
| 解析：pypdf | 一期够用 |
| 不把网页原文写进 task_plan | 遵循 skill 安全边界 |

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| 部分公网手册下载曾不完整 | 续传校验 `%%EOF`；年报主源巨潮稳定 |
| skill session-catchup 路径在 `.codex` | 规划文件仍写项目根，无影响 |
| 纯向量年报章节召回偏差 | hybrid + 查询扩展 + 文档过滤 |
| 验证清单粘贴完整 JSON 过大 | 结论写入 result；清单仅保留模板 |
## 资源
- PRD：项目根目录 md
- 数据清单：`data/SOURCES.md`
- 黄金问答：`data/gold/sample_qa.json`
- LangGraph 文档：https://langchain-ai.github.io/langgraph/
- Chroma：https://docs.trychroma.com/

## 考研改造发现（K0–K1）
- 种子包 `data/kaoyan/`：97 个文档（sources.json）、37 行 `majors.csv`；`来源URL` 只到页面级，一个页面可能对应多个文档（华师目录系统页 → 6 个学院查询结果；暨南复试方案页 → 通知 + 4 个学院 xlsx；中大 sse 页 → 细则 + 分数线图片）
- 中大 2026 硕士招生学科专业目录 PDF：从 graduate.sysu.edu.cn（article/493 的附件）下载成功，5,204,498 字节，sha256 `497d86ba…fb7b0` 与 manifest 一致；>3MB，只留本地
- 华工 `yanzhao.scut.edu.cn` 目录系统 302 到统一认证，2026 目录与 081200 / 085404 / 085405 初试科目无官方来源（非官方站说“考 408”不采信）
- 暨南 0812 按一级学科统筹：2027 目录只给合计 24（含推免），推免复试方案给“≤19”上限；2026 目录有分专业计划（081201 5 / 081202 3 / 081203 6 / 0812Z3 10），2026 复试统招计划 10、复试 19 人
- 备注里的拆分口径（“13（普通）+2（退役）”“66普通+4少干+3退役”）不做结构化，只留原文

## 考研改造发现（K2）
- 页面结构：华师目录是“布局表套数据表”，只能取叶子表；暨南 2027 目录是一张 1082 行的三级表（学院行 / 专业行 / 方向行）；中大校线 PDF 用竖排“学/术/学/位”合并格，pdfplumber 给 `None`，要按格子 bbox 补值
- 附件：华工博达站用 `div[pdfsrc]` 播放器，文件名只在 `sudyfile-attr` 的 title 里；暨南附件 URL 是 UUID，文件名只能取锚文本；中大 sece 用 `../../docs/` 相对路径
- 个人信息不只在名单文件里：华工推免公示正文“拟录取X等2582人”带首名；暨南目录的导师名单与考生姓名大量重名（公开信息，不处理）

## 考研改造发现（K3）
- 检索：名单类文档每行都有专业代码，BM25 下对“085404 复试线”这类问题排名很高；按 doc_type / 学院名加先验、名单降权后，中大计算机学院复试线细则从第 5 升到第 1
- 向量检索（qwen3-embedding:0.6b）对“中大 2027 年 085404”这类问题偏向语义相近的免试生目录，hybrid 的 golden hit@5（15/18）略低于纯 BM25（16/18）；数值类问题应在 K5 优先走结构化工具
- 表格结构：暨南目录的列名行在第 5 行（前面是标题行和学院行）；中大学院细则是双层表头（“复试分数线”下分总分 / 政治 / 外语 / 业务课）

## 视觉/浏览器发现
- 无（本轮为方案设计，未截图）

---
*每执行2次查看/浏览器/搜索操作后更新此文件*
