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

### 现有仓库资产
- PRD：`企业文档智能处理Agent 产品需求文档（PRD）.md`
- 演示数据已就绪（约 30MB）：
  - 年报：茅台 / 五粮液 / 宁德时代 2024
  - 制度：OHCHR 世界人权宣言 + 可控制度 txt
  - 手册：PostgreSQL 16、C n1570、可控产品参数 txt
  - 黄金问答：`data/gold/sample_qa.json`
- 下载脚本：`scripts/download_demo_data.py`
- 尚无应用代码（无 `src/`、无 API、无依赖清单）

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
| Embedding：远程 OpenAI-compatible（独立 EMBEDDING_*） | 用户要远程；DeepSeek 官方无 Embedding |
| 未配置 Embedding 时用 BM25 词法检索 | 保证仅 DeepSeek Key 也能跑通一期 |
| 一期只解析 PDF + txt | 用户确认；docx 二期再加 |
| API Key 写入 `.env` 并 gitignore | 防泄露；聊天暴露后建议用户轮换 Key |
| 一期同步 `/chat`，重任务用预 ingest | 实现简单，演示稳定 |
| 记忆二期用 SQLite | 零运维，够用轨迹回溯 |
| 解析：pypdf | 一期够用 |
| 不把网页原文写进 task_plan | 遵循 skill 安全边界 |

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| 部分公网手册下载曾不完整 | 续传校验 `%%EOF`；年报主源巨潮稳定 |
| skill session-catchup 路径在 `.codex` | 规划文件仍写项目根，无影响 |

## 资源
- PRD：项目根目录 md
- 数据清单：`data/SOURCES.md`
- 黄金问答：`data/gold/sample_qa.json`
- LangGraph 文档：https://langchain-ai.github.io/langgraph/
- Chroma：https://docs.trychroma.com/

## 视觉/浏览器发现
- 无（本轮为方案设计，未截图）

---
*每执行2次查看/浏览器/搜索操作后更新此文件*
