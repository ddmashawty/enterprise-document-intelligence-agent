# 企业文档智能处理 Agent

面向企业私有文档的问答与整理助手。把 PDF、Word、txt、Markdown 导入本地知识库后，用自然语言检索、对比、抽取，并导出 Markdown 或 Excel。回答带引用来源，不靠模型凭空编造。

作者：的懒

## 能做什么

- **导入**：PDF、`.docx`、txt、Markdown。按页或分页符切分，再切片入库。
- **检索**：Ollama `qwen3-embedding:0.6b`（Chroma）与 BM25 混合检索。未配置向量服务时退回 BM25。
- **Agent**：LangGraph 图 `plan → act → reflect`，最多 5 轮工具调用。工具包括检索、解析、对比、字段抽取、Markdown / Excel 导出。
- **记忆**：当前会话的近期对话，以及 SQLite 里的任务轨迹，可回放 plan、工具、反思和导出文件。
- **界面**：FastAPI 服务，外加 Streamlit 演示页（对话、知识库、任务中心、演示剧本）。

## 环境

- Python 3.12
- DeepSeek API Key（`deepseek-chat`）
- 可选：本机 Ollama，并已拉取 `qwen3-embedding:0.6b`

## 启动

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -r requirements-embedding.txt

cp .env.example .env
# 填写 LLM_API_KEY
# ollama pull qwen3-embedding:0.6b

bash scripts/demo_repro.sh

PYTHONPATH=src python -m uvicorn doc_agent.api:app --host 127.0.0.1 --port 8000
```

另开一个终端启动界面：

```bash
bash scripts/run_frontend.sh
```

- 接口文档：http://127.0.0.1:8000/docs
- 演示界面：http://127.0.0.1:8501

界面标题下会显示当前 API 地址，默认是 `http://127.0.0.1:8000`。若 8000 上不是本服务，而 8001 上是，界面会改连 8001 并提示。请求体里的 `message` 只写一层字符串。

本机演示没有登录。不要把 API 或 Streamlit 暴露到公网。

## 调用示例

```bash
curl -s localhost:8000/health | python3 -m json.tool

curl -s localhost:8000/v1/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","message":"演示产品手册里 TopK 是多少？"}'

curl -s localhost:8000/v1/chat/async -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","message":"保密等级分为哪几级？导出 Excel，文件名 demo_secrecy"}'
# 用返回的 task_id 轮询 GET /v1/tasks/<task_id>
```

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 状态、模型是否配置、检索后端、切片数 |
| POST | `/v1/ingest` | 按路径导入文档，`reindex` 可清空后重建 |
| POST | `/v1/chat` | 同步问答 |
| POST | `/v1/chat/async` | 异步排队，返回 `task_id` |
| GET | `/v1/tasks` | 任务列表，可用 `session_id` 过滤 |
| GET | `/v1/tasks/{task_id}` | 回答、plan、trace、引用、导出 |
| GET | `/v1/sessions/{session_id}` | 会话轮次与近期任务 |

错误格式：`{"error":{"code":"...","message":"...","details":...}}`。

## 目录

```
src/doc_agent/
  agent/     LangGraph 规划、执行、反思
  tools/     检索、解析、对比、导出
  ingest/    PDF / DOCX / 文本加载与切片
  rag/       混合检索
  memory/    会话记忆与 SQLite 轨迹
  api/       FastAPI
frontend/    Streamlit 演示界面
data/raw/    演示文档
```

旧版 `.doc` 不支持，请另存为 `.docx`。

## 测试

```bash
PYTHONPATH=src pytest -q
PYTHONPATH=src python scripts/smoke_chat.py
PYTHONPATH=src python scripts/smoke_phase4.py
```

人工验收清单：`docs/frontend_verification_checklist.md`、`docs/backend_verification_checklist.md`。

## 配置

密钥只放 `.env`，不要提交。常用项见 `.env.example`：`LLM_API_KEY`、`EMBEDDING_BASE_URL`、`CHUNK_SIZE`、`TOP_K`、`MAX_TOOL_CALLS`。

`data/chroma`、`data/memory.db`、`data/exports`、`data/uploads` 和大体积 PDF 不入库。
