# Enterprise Document Intelligence Agent

基于 DeepSeek + LangGraph 的企业文档智能处理 Agent（三期工程化后端）。

## 已确认配置

- LLM：DeepSeek（`deepseek-chat`）
- 文档：PDF、Word（.docx）、txt、Markdown
- 检索：**Hybrid** = Ollama `qwen3-embedding:0.6b`（Chroma）+ BM25
- 记忆：会话短期 + SQLite（`data/memory.db`）
- 图：`plan → act → reflect → (重试|finalize)`，工具上限默认 5（请求可覆盖）
- 异步：`POST /v1/chat/async` + `GET /v1/tasks/{id}` 轮询

## 快速开始

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -r requirements-embedding.txt

cp .env.example .env
# 填写 LLM_API_KEY；Embedding 默认指向本地 Ollama
# ollama pull qwen3-embedding:0.6b

# 一键复现（ingest + pytest + 可选 smoke）
bash scripts/demo_repro.sh

PYTHONPATH=src python -m uvicorn doc_agent.api:app --host 0.0.0.0 --port 8000
```

打开 http://127.0.0.1:8000/docs 。注意 Request body 里 `message` 只要一层字符串，不要写成 `"message": "message": "..."`。

## 启动前端

另开一个终端（后端保持在 8000）：

```bash
bash scripts/run_frontend.sh
```

打开 http://127.0.0.1:8501 。这是本地演示界面，没有鉴权，不要暴露到公网。验证步骤见 `docs/frontend_verification_checklist.md`。

```bash
curl -s localhost:8000/health | python3 -m json.tool

# 同步问答
curl -s localhost:8000/v1/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","message":"演示产品手册里 TopK 是多少？"}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["answer"][:500]); print(d["task_id"])'

# 异步问答
curl -s localhost:8000/v1/chat/async -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","message":"保密等级分为哪几级？导出 Excel，文件名 demo_secrecy"}'
# 用返回的 task_id 轮询：
# curl -s localhost:8000/v1/tasks/<task_id> | python3 -m json.tool
```

## 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康与配置 |
| POST | `/v1/ingest` | 导入文档 |
| POST | `/v1/chat` | 同步 Agent 问答 |
| POST | `/v1/chat/async` | 异步排队，立即返回 `task_id` |
| GET | `/v1/tasks` | 任务列表（可选 `session_id`） |
| GET | `/v1/tasks/{task_id}` | 任务轨迹 / 异步结果 |
| GET | `/v1/sessions/{session_id}` | 会话历史 |

错误响应统一为：`{"error":{"code":"...","message":"...","details":...}}`。

## 测试与性能

```bash
PYTHONPATH=src pytest -q
PYTHONPATH=src python scripts/perf_baseline.py   # 写出 docs/perf_baseline.json
PYTHONPATH=src python scripts/smoke_chat.py
PYTHONPATH=src python scripts/smoke_phase4.py
```

## 文档

| 文件 | 说明 |
|------|------|
| `docs/phase5_notes.md` | 三期工程化说明 |
| `docs/phase5_verification_checklist.md` | 三期人工验证清单 |
| `docs/frontend_implementation_plan.md` | Streamlit 前端实现计划（阶段 6） |
| `docs/phase4_retest_result.md` | 二期复测通过 |
| `docs/backend_verification_checklist.md` | 一/二期功能验证清单 |
| `task_plan.md` | 阶段计划 |

## 安全

- API Key 只放 `.env`
- 大 PDF / `data/chroma` / `data/memory.db` / `data/exports` 不入库
