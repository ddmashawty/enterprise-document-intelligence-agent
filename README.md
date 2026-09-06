# Enterprise Document Intelligence Agent

基于 DeepSeek + LangGraph 的企业文档智能处理 Agent（二期后端：记忆 / 反思 / 导出 / 对比）。

## 已确认配置

- LLM：DeepSeek（`deepseek-chat`）
- 文档：一期/二期仅 PDF + txt
- 检索：**Hybrid** = Ollama `qwen3-embedding:0.6b`（Chroma）+ BM25；含年报章节查询扩展
- 记忆：会话短期（进程内）+ SQLite 任务轨迹（`data/memory.db`）
- 图：`plan → act → reflect → (重试 act | finalize)`，工具上限 5

## 快速开始

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-embedding.txt   # Chroma

cp .env.example .env
# 填写 LLM_API_KEY；Embedding 默认指向本地 Ollama
# ollama pull qwen3-embedding:0.6b

PYTHONPATH=src python scripts/ingest_demo.py --reindex
PYTHONPATH=src python scripts/smoke_chat.py
PYTHONPATH=src python scripts/smoke_phase4.py

PYTHONPATH=src python -m uvicorn doc_agent.api:app --host 0.0.0.0 --port 8000
```

```bash
curl -s localhost:8000/health | python3 -m json.tool

curl -s localhost:8000/v1/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","message":"演示产品手册里 TopK 是多少？导出为 Markdown"}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["answer"][:800]); print("exports", d.get("exports")); print("task", d.get("task_id"))'
```

## 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康与配置 |
| POST | `/v1/ingest` | 导入文档 |
| POST | `/v1/chat` | Agent 问答（含 plan/citations/trace/exports/reflection） |
| GET | `/v1/tasks/{task_id}` | 查询任务轨迹 |
| GET | `/v1/sessions/{session_id}` | 会话历史与近期任务 |

## 二期工具

`list_documents` · `rag_search` · `parse_document` · `summarize_citations` · `compare_docs` · `extract_fields` · `export_markdown` · `export_excel`

导出文件写入 `data/exports/`（默认 gitignore）。

## 文档

| 文件 | 说明 |
|------|------|
| `docs/backend_verification_result.md` | 一期验收 |
| `docs/phase4_notes.md` | 二期能力说明 |
| `task_plan.md` / `findings.md` / `progress.md` | 规划与进度 |

## 安全

- API Key 只放 `.env`
- 大 PDF / `data/chroma` / `data/memory.db` / `data/exports` 不入库
